-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- For text search
CREATE EXTENSION IF NOT EXISTS "btree_gin"; -- For compound indexes

-- Users table with sharding info
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    roles TEXT[] DEFAULT '{}',
    shard INTEGER NOT NULL,
    encryption_enabled BOOLEAN DEFAULT true,
    mfa_enabled BOOLEAN DEFAULT false,
    mfa_secret VARCHAR(255),
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_shard ON users(shard);

-- Documents table (sharded by user)
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    owner VARCHAR(255) NOT NULL,
    name VARCHAR(1024) NOT NULL,
    parent_folder_id UUID,
    doc_type VARCHAR(50) NOT NULL,
    size_bytes BIGINT NOT NULL,
    version BIGINT DEFAULT 1,
    shard_id INTEGER NOT NULL,
    encrypted BOOLEAN DEFAULT false,
    wal_sequence BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'
);

-- Indexes for efficient queries
CREATE INDEX idx_documents_owner_shard ON documents(owner, shard_id);
CREATE INDEX idx_documents_parent ON documents(parent_folder_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_documents_name_trgm ON documents USING gin(name gin_trgm_ops);
CREATE INDEX idx_documents_deleted ON documents(deleted_at) WHERE deleted_at IS NOT NULL;
CREATE INDEX idx_documents_metadata ON documents USING gin(metadata);

-- ACL table for document permissions
CREATE TABLE document_acl (
    document_id UUID NOT NULL,
    principal VARCHAR(255) NOT NULL,
    access_level VARCHAR(10) NOT NULL CHECK (access_level IN ('read', 'write')),
    granted_by VARCHAR(255) NOT NULL,
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (document_id, principal)
);

CREATE INDEX idx_acl_principal ON document_acl(principal);
CREATE INDEX idx_acl_document ON document_acl(document_id);

-- Agent scopes for restricting agent access
CREATE TABLE agent_scopes (
    user_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    allowed_folders UUID[] NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, agent_id)
);

-- WAL checkpoint tracking
CREATE TABLE wal_checkpoints (
    shard_id INTEGER NOT NULL,
    segment_id BIGINT NOT NULL,
    last_sequence BIGINT NOT NULL,
    checkpointed_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (shard_id, segment_id)
);

-- Shared documents tracking (for cross-shard replication)
CREATE TABLE shared_documents (
    document_id UUID NOT NULL,
    shard_id INTEGER NOT NULL,
    is_primary BOOLEAN DEFAULT false,
    last_sync_version BIGINT,
    last_sync_at TIMESTAMPTZ,
    PRIMARY KEY (document_id, shard_id)
);

CREATE INDEX idx_shared_docs_shard ON shared_documents(shard_id);

-- Search index metadata
CREATE TABLE search_index_status (
    document_id UUID PRIMARY KEY,
    indexed_version BIGINT NOT NULL,
    indexed_at TIMESTAMPTZ DEFAULT NOW(),
    index_shard INTEGER NOT NULL
);

-- Audit log for compliance
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    user_id VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL,
    document_id UUID,
    ip_address INET,
    user_agent TEXT,
    details JSONB,
    shard_id INTEGER NOT NULL
);

-- Partition audit log by month
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_user ON audit_log(user_id);
CREATE INDEX idx_audit_document ON audit_log(document_id);

-- Blob storage references
CREATE TABLE blob_references (
    document_id UUID NOT NULL,
    version BIGINT NOT NULL,
    storage_key VARCHAR(1024) NOT NULL,
    size_bytes BIGINT NOT NULL,
    content_hash VARCHAR(64),
    stored_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (document_id, version)
);

-- User quotas and usage
CREATE TABLE user_quotas (
    user_id VARCHAR(255) PRIMARY KEY,
    max_storage_bytes BIGINT DEFAULT 10737418240, -- 10GB default
    max_documents INTEGER DEFAULT 10000,
    used_storage_bytes BIGINT DEFAULT 0,
    document_count INTEGER DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW()
);

-- Rate limit tracking (could also be in Redis)
CREATE TABLE rate_limit_violations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255),
    ip_address INET,
    endpoint VARCHAR(255),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    requests_count INTEGER
);

CREATE INDEX idx_rate_limit_user ON rate_limit_violations(user_id, timestamp);
CREATE INDEX idx_rate_limit_ip ON rate_limit_violations(ip_address, timestamp);

-- Functions for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to update user quotas
CREATE OR REPLACE FUNCTION update_user_quota()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE user_quotas 
        SET used_storage_bytes = used_storage_bytes + NEW.size_bytes,
            document_count = document_count + 1,
            last_updated = NOW()
        WHERE user_id = NEW.owner;
    ELSIF TG_OP = 'UPDATE' AND NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
        UPDATE user_quotas 
        SET used_storage_bytes = used_storage_bytes - OLD.size_bytes,
            document_count = document_count - 1,
            last_updated = NOW()
        WHERE user_id = OLD.owner;
    ELSIF TG_OP = 'UPDATE' AND NEW.size_bytes != OLD.size_bytes THEN
        UPDATE user_quotas 
        SET used_storage_bytes = used_storage_bytes + (NEW.size_bytes - OLD.size_bytes),
            last_updated = NOW()
        WHERE user_id = NEW.owner;
    END IF;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_quota_on_document_change
    AFTER INSERT OR UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_user_quota();

-- Create partitions for audit_log (example for current year)
CREATE TABLE audit_log_2024_01 PARTITION OF audit_log
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
    
CREATE TABLE audit_log_2024_02 PARTITION OF audit_log
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');

-- Add more partitions as needed...