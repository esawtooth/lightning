//! Enhanced authentication and encryption for distributed system

use anyhow::{anyhow, Result};
use argon2::{Argon2, PasswordHash, PasswordHasher, PasswordVerifier};
use async_trait::async_trait;
use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use jsonwebtoken::{decode, encode, Algorithm, DecodingKey, EncodingKey, Header, Validation};
use rand::{RngCore, SeedableRng};
use redis::AsyncCommands;
use ring::aead::{Aad, LessSafeKey, Nonce, UnboundKey, AES_256_GCM};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::sync::RwLock;
use uuid::Uuid;

const ACCESS_TOKEN_DURATION: Duration = Duration::from_secs(15 * 60); // 15 minutes
const REFRESH_TOKEN_DURATION: Duration = Duration::from_secs(7 * 24 * 60 * 60); // 7 days
const KEY_ROTATION_INTERVAL: Duration = Duration::from_secs(24 * 60 * 60); // 24 hours

/// Enhanced claims with additional security fields
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Claims {
    pub sub: String,           // User ID
    pub agent: Option<String>, // Agent ID if applicable
    pub sid: String,           // Session ID
    pub shard: u32,           // User's primary shard
    pub roles: Vec<String>,    // User roles
    pub exp: u64,             // Expiration
    pub iat: u64,             // Issued at
    pub jti: String,          // JWT ID for revocation
}

/// Token pair returned on authentication
#[derive(Debug, Serialize, Deserialize)]
pub struct TokenPair {
    pub access_token: String,
    pub refresh_token: String,
    pub expires_in: u64,
    pub token_type: String,
}

/// User profile with security settings
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserProfile {
    pub id: String,
    pub email: String,
    pub password_hash: String,
    pub roles: Vec<String>,
    pub shard: u32,
    pub encryption_enabled: bool,
    pub mfa_enabled: bool,
    pub mfa_secret: Option<String>,
    pub created_at: chrono::DateTime<chrono::Utc>,
    pub last_login: Option<chrono::DateTime<chrono::Utc>>,
}

/// Session information stored in Redis
#[derive(Debug, Serialize, Deserialize)]
pub struct Session {
    pub id: String,
    pub user_id: String,
    pub created_at: u64,
    pub last_activity: u64,
    pub ip_address: String,
    pub user_agent: String,
    pub revoked: bool,
}

/// Enhanced authentication service
pub struct AuthService {
    jwt_keys: Arc<RwLock<JwtKeyPair>>,
    redis: Arc<redis::Client>,
    db: Arc<sqlx::PgPool>,
    password_hasher: Arc<Argon2<'static>>,
}

struct JwtKeyPair {
    encoding: EncodingKey,
    decoding: DecodingKey,
    kid: String,
    created_at: SystemTime,
}

impl AuthService {
    pub async fn new(redis_url: &str, db_url: &str) -> Result<Self> {
        let redis = Arc::new(redis::Client::open(redis_url)?);
        let db = Arc::new(sqlx::PgPool::connect(db_url).await?);
        
        // Generate initial JWT keys
        let keys = JwtKeyPair::generate()?;
        
        Ok(Self {
            jwt_keys: Arc::new(RwLock::new(keys)),
            redis,
            db,
            password_hasher: Arc::new(Argon2::default()),
        })
    }
    
    /// Authenticate user with email and password
    pub async fn authenticate(
        &self,
        email: &str,
        password: &str,
        ip_address: &str,
        user_agent: &str,
    ) -> Result<TokenPair> {
        // Load user profile
        let user = self.get_user_by_email(email).await?;
        
        // Verify password
        let parsed_hash = PasswordHash::new(&user.password_hash)?;
        self.password_hasher
            .verify_password(password.as_bytes(), &parsed_hash)
            .map_err(|_| anyhow!("Invalid credentials"))?;
        
        // Check if MFA is required
        if user.mfa_enabled {
            // Would implement MFA verification here
            // For now, we'll skip it
        }
        
        // Create session
        let session_id = Uuid::new_v4().to_string();
        let session = Session {
            id: session_id.clone(),
            user_id: user.id.clone(),
            created_at: SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs(),
            last_activity: SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs(),
            ip_address: ip_address.to_string(),
            user_agent: user_agent.to_string(),
            revoked: false,
        };
        
        self.store_session(&session).await?;
        
        // Update last login
        self.update_last_login(&user.id).await?;
        
        // Generate tokens
        self.generate_token_pair(&user, &session_id).await
    }
    
    /// Generate new token pair
    async fn generate_token_pair(&self, user: &UserProfile, session_id: &str) -> Result<TokenPair> {
        let now = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
        
        // Access token claims
        let access_claims = Claims {
            sub: user.id.clone(),
            agent: None,
            sid: session_id.to_string(),
            shard: user.shard,
            roles: user.roles.clone(),
            exp: now + ACCESS_TOKEN_DURATION.as_secs(),
            iat: now,
            jti: Uuid::new_v4().to_string(),
        };
        
        // Refresh token claims
        let refresh_claims = Claims {
            sub: user.id.clone(),
            agent: None,
            sid: session_id.to_string(),
            shard: user.shard,
            roles: vec!["refresh".to_string()],
            exp: now + REFRESH_TOKEN_DURATION.as_secs(),
            iat: now,
            jti: Uuid::new_v4().to_string(),
        };
        
        // Encode tokens
        let keys = self.jwt_keys.read().await;
        let mut header = Header::new(Algorithm::RS256);
        header.kid = Some(keys.kid.clone());
        
        let access_token = encode(&header, &access_claims, &keys.encoding)?;
        let refresh_token = encode(&header, &refresh_claims, &keys.encoding)?;
        
        // Store token IDs for revocation
        self.store_token_id(&access_claims.jti, access_claims.exp).await?;
        self.store_token_id(&refresh_claims.jti, refresh_claims.exp).await?;
        
        Ok(TokenPair {
            access_token,
            refresh_token,
            expires_in: ACCESS_TOKEN_DURATION.as_secs(),
            token_type: "Bearer".to_string(),
        })
    }
    
    /// Verify and decode a token
    pub async fn verify_token(&self, token: &str) -> Result<Claims> {
        let keys = self.jwt_keys.read().await;
        let mut validation = Validation::new(Algorithm::RS256);
        validation.set_required_spec_claims(&["exp", "sub", "jti"]);
        
        let token_data = decode::<Claims>(token, &keys.decoding, &validation)?;
        let claims = token_data.claims;
        
        // Check if token is revoked
        if self.is_token_revoked(&claims.jti).await? {
            return Err(anyhow!("Token has been revoked"));
        }
        
        // Check if session is valid
        if !self.is_session_valid(&claims.sid).await? {
            return Err(anyhow!("Session is invalid"));
        }
        
        Ok(claims)
    }
    
    /// Refresh access token using refresh token
    pub async fn refresh_token(&self, refresh_token: &str) -> Result<TokenPair> {
        let claims = self.verify_token(refresh_token).await?;
        
        // Verify it's a refresh token
        if !claims.roles.contains(&"refresh".to_string()) {
            return Err(anyhow!("Not a refresh token"));
        }
        
        // Load user profile
        let user = self.get_user_by_id(&claims.sub).await?;
        
        // Generate new token pair
        self.generate_token_pair(&user, &claims.sid).await
    }
    
    /// Revoke a token
    pub async fn revoke_token(&self, token: &str) -> Result<()> {
        if let Ok(claims) = self.verify_token(token).await {
            self.revoke_token_id(&claims.jti).await?;
        }
        Ok(())
    }
    
    /// Logout and revoke all tokens for a session
    pub async fn logout(&self, session_id: &str) -> Result<()> {
        let mut conn = self.redis.get_async_connection().await?;
        
        // Mark session as revoked
        let key = format!("session:{}", session_id);
        if let Ok(data) = conn.get::<_, String>(&key).await {
            if let Ok(mut session) = serde_json::from_str::<Session>(&data) {
                session.revoked = true;
                let data = serde_json::to_string(&session)?;
                conn.set_ex(&key, data, 86400).await?; // Keep for 24h
            }
        }
        
        Ok(())
    }
    
    // Helper methods
    
    async fn get_user_by_email(&self, email: &str) -> Result<UserProfile> {
        let row = sqlx::query!(
            r#"
            SELECT id, email, password_hash, roles, shard, 
                   encryption_enabled, mfa_enabled, mfa_secret,
                   created_at, last_login
            FROM users
            WHERE email = $1 AND active = true
            "#,
            email,
        )
        .fetch_one(&*self.db)
        .await?;
        
        Ok(UserProfile {
            id: row.id,
            email: row.email,
            password_hash: row.password_hash,
            roles: row.roles,
            shard: row.shard as u32,
            encryption_enabled: row.encryption_enabled,
            mfa_enabled: row.mfa_enabled,
            mfa_secret: row.mfa_secret,
            created_at: row.created_at,
            last_login: row.last_login,
        })
    }
    
    async fn get_user_by_id(&self, id: &str) -> Result<UserProfile> {
        let row = sqlx::query!(
            r#"
            SELECT id, email, password_hash, roles, shard, 
                   encryption_enabled, mfa_enabled, mfa_secret,
                   created_at, last_login
            FROM users
            WHERE id = $1 AND active = true
            "#,
            id,
        )
        .fetch_one(&*self.db)
        .await?;
        
        Ok(UserProfile {
            id: row.id,
            email: row.email,
            password_hash: row.password_hash,
            roles: row.roles,
            shard: row.shard as u32,
            encryption_enabled: row.encryption_enabled,
            mfa_enabled: row.mfa_enabled,
            mfa_secret: row.mfa_secret,
            created_at: row.created_at,
            last_login: row.last_login,
        })
    }
    
    async fn update_last_login(&self, user_id: &str) -> Result<()> {
        sqlx::query!(
            "UPDATE users SET last_login = NOW() WHERE id = $1",
            user_id,
        )
        .execute(&*self.db)
        .await?;
        Ok(())
    }
    
    async fn store_session(&self, session: &Session) -> Result<()> {
        let mut conn = self.redis.get_async_connection().await?;
        let key = format!("session:{}", session.id);
        let data = serde_json::to_string(session)?;
        
        // Store for session duration
        conn.set_ex(&key, data, REFRESH_TOKEN_DURATION.as_secs() as usize).await?;
        Ok(())
    }
    
    async fn is_session_valid(&self, session_id: &str) -> Result<bool> {
        let mut conn = self.redis.get_async_connection().await?;
        let key = format!("session:{}", session_id);
        
        if let Ok(data) = conn.get::<_, String>(&key).await {
            if let Ok(session) = serde_json::from_str::<Session>(&data) {
                return Ok(!session.revoked);
            }
        }
        
        Ok(false)
    }
    
    async fn store_token_id(&self, jti: &str, exp: u64) -> Result<()> {
        let mut conn = self.redis.get_async_connection().await?;
        let key = format!("token:{}", jti);
        let ttl = exp.saturating_sub(SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs());
        
        if ttl > 0 {
            conn.set_ex(&key, "1", ttl as usize).await?;
        }
        
        Ok(())
    }
    
    async fn is_token_revoked(&self, jti: &str) -> Result<bool> {
        let mut conn = self.redis.get_async_connection().await?;
        let key = format!("token:{}", jti);
        let revoked_key = format!("revoked:{}", jti);
        
        // Check if token is revoked
        if conn.exists(&revoked_key).await? {
            return Ok(true);
        }
        
        // Check if token still exists (not expired)
        Ok(!conn.exists(&key).await?)
    }
    
    async fn revoke_token_id(&self, jti: &str) -> Result<()> {
        let mut conn = self.redis.get_async_connection().await?;
        let key = format!("token:{}", jti);
        let revoked_key = format!("revoked:{}", jti);
        
        // Mark as revoked
        conn.set_ex(&revoked_key, "1", 86400).await?; // Keep for 24h
        conn.del(&key).await?;
        
        Ok(())
    }
}

impl JwtKeyPair {
    fn generate() -> Result<Self> {
        use ring::signature::{Ed25519KeyPair, KeyPair};
        
        let rng = ring::rand::SystemRandom::new();
        let pkcs8_bytes = Ed25519KeyPair::generate_pkcs8(&rng)?;
        let key_pair = Ed25519KeyPair::from_pkcs8(pkcs8_bytes.as_ref())?;
        
        let encoding = EncodingKey::from_ed_der(pkcs8_bytes.as_ref());
        let decoding = DecodingKey::from_ed_der(key_pair.public_key().as_ref());
        
        Ok(Self {
            encoding,
            decoding,
            kid: Uuid::new_v4().to_string(),
            created_at: SystemTime::now(),
        })
    }
}

/// Encryption provider using AES-256-GCM
pub struct AesEncryptionProvider {
    user_keys: Arc<RwLock<HashMap<String, LessSafeKey>>>,
    master_key: Vec<u8>,
}

impl AesEncryptionProvider {
    pub fn new(master_key: &[u8]) -> Result<Self> {
        if master_key.len() != 32 {
            return Err(anyhow!("Master key must be 32 bytes"));
        }
        
        Ok(Self {
            user_keys: Arc::new(RwLock::new(HashMap::new())),
            master_key: master_key.to_vec(),
        })
    }
    
    async fn get_user_key(&self, user_id: &str) -> Result<LessSafeKey> {
        let mut cache = self.user_keys.write().await;
        
        if let Some(key) = cache.get(user_id) {
            return Ok(key.clone());
        }
        
        // Derive user key from master key
        let mut hasher = ring::digest::Context::new(&ring::digest::SHA256);
        hasher.update(&self.master_key);
        hasher.update(user_id.as_bytes());
        let key_material = hasher.finish();
        
        let unbound_key = UnboundKey::new(&AES_256_GCM, key_material.as_ref())?;
        let key = LessSafeKey::new(unbound_key);
        
        cache.insert(user_id.to_string(), key.clone());
        Ok(key)
    }
}

#[async_trait]
impl crate::storage::distributed::EncryptionProvider for AesEncryptionProvider {
    async fn encrypt(&self, user_id: &str, data: &[u8]) -> Result<Vec<u8>> {
        let key = self.get_user_key(user_id).await?;
        
        // Generate nonce
        let mut nonce_bytes = [0u8; 12];
        rand::thread_rng().fill_bytes(&mut nonce_bytes);
        let nonce = Nonce::assume_unique_for_key(nonce_bytes);
        
        // Encrypt
        let mut ciphertext = data.to_vec();
        key.seal_in_place_append_tag(nonce, Aad::empty(), &mut ciphertext)?;
        
        // Prepend nonce
        let mut result = nonce_bytes.to_vec();
        result.extend_from_slice(&ciphertext);
        
        Ok(result)
    }
    
    async fn decrypt(&self, user_id: &str, data: &[u8]) -> Result<Vec<u8>> {
        if data.len() < 12 {
            return Err(anyhow!("Invalid ciphertext"));
        }
        
        let key = self.get_user_key(user_id).await?;
        
        // Extract nonce
        let (nonce_bytes, ciphertext) = data.split_at(12);
        let nonce = Nonce::assume_unique_for_key(
            nonce_bytes.try_into().map_err(|_| anyhow!("Invalid nonce"))?
        );
        
        // Decrypt
        let mut plaintext = ciphertext.to_vec();
        key.open_in_place(nonce, Aad::empty(), &mut plaintext)?;
        
        // Remove tag
        let text_len = plaintext.len() - AES_256_GCM.tag_len();
        plaintext.truncate(text_len);
        
        Ok(plaintext)
    }
}

/// Rate limiter using token bucket algorithm
pub struct RateLimiter {
    redis: Arc<redis::Client>,
    limits: RateLimits,
}

#[derive(Debug, Clone)]
pub struct RateLimits {
    pub requests_per_minute: u32,
    pub requests_per_hour: u32,
    pub burst_size: u32,
}

impl Default for RateLimits {
    fn default() -> Self {
        Self {
            requests_per_minute: 60,
            requests_per_hour: 1000,
            burst_size: 10,
        }
    }
}

impl RateLimiter {
    pub fn new(redis: Arc<redis::Client>, limits: RateLimits) -> Self {
        Self { redis, limits }
    }
    
    pub async fn check_rate_limit(&self, key: &str) -> Result<bool> {
        let mut conn = self.redis.get_async_connection().await?;
        
        // Use Redis Lua script for atomic rate limiting
        let script = r#"
            local key = KEYS[1]
            local limit = tonumber(ARGV[1])
            local window = tonumber(ARGV[2])
            local current = redis.call('INCR', key)
            
            if current == 1 then
                redis.call('EXPIRE', key, window)
            end
            
            return current <= limit
        "#;
        
        let allowed: bool = redis::Script::new(script)
            .key(format!("rate:min:{}", key))
            .arg(self.limits.requests_per_minute)
            .arg(60)
            .invoke_async(&mut conn)
            .await?;
        
        if !allowed {
            return Ok(false);
        }
        
        // Check hourly limit
        let allowed: bool = redis::Script::new(script)
            .key(format!("rate:hour:{}", key))
            .arg(self.limits.requests_per_hour)
            .arg(3600)
            .invoke_async(&mut conn)
            .await?;
        
        Ok(allowed)
    }
}