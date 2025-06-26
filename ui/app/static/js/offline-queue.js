// Offline Queue Manager for Context Hub
// Provides resilient saving with automatic retry when connection is restored

class OfflineQueue {
    constructor(options = {}) {
        this.options = {
            storageKey: 'context-hub-offline-queue',
            maxRetries: 3,
            retryDelay: 5000, // 5 seconds
            onSync: () => {},
            onError: () => {},
            ...options
        };
        
        this.queue = [];
        this.isOnline = navigator.onLine;
        this.isSyncing = false;
        
        // Load queue from localStorage
        this.loadQueue();
        
        // Set up event listeners
        window.addEventListener('online', () => this.handleOnline());
        window.addEventListener('offline', () => this.handleOffline());
        
        // Periodic sync check (every 30 seconds)
        setInterval(() => {
            if (this.isOnline && this.queue.length > 0) {
                this.sync();
            }
        }, 30000);
        
        // Initial sync if online
        if (this.isOnline && this.queue.length > 0) {
            setTimeout(() => this.sync(), 1000);
        }
    }
    
    // Load queue from localStorage
    loadQueue() {
        try {
            const stored = localStorage.getItem(this.options.storageKey);
            if (stored) {
                this.queue = JSON.parse(stored);
                console.log(`Loaded ${this.queue.length} items from offline queue`);
            }
        } catch (error) {
            console.error('Failed to load offline queue:', error);
            this.queue = [];
        }
    }
    
    // Save queue to localStorage
    saveQueue() {
        try {
            localStorage.setItem(this.options.storageKey, JSON.stringify(this.queue));
        } catch (error) {
            console.error('Failed to save offline queue:', error);
        }
    }
    
    // Add operation to queue
    add(operation) {
        const queueItem = {
            id: `op-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
            timestamp: Date.now(),
            retries: 0,
            ...operation
        };
        
        this.queue.push(queueItem);
        this.saveQueue();
        
        console.log('Added to offline queue:', queueItem);
        
        // Try to sync immediately if online
        if (this.isOnline) {
            this.sync();
        }
        
        return queueItem.id;
    }
    
    // Remove operation from queue
    remove(operationId) {
        this.queue = this.queue.filter(item => item.id !== operationId);
        this.saveQueue();
    }
    
    // Handle coming online
    handleOnline() {
        console.log('Connection restored');
        this.isOnline = true;
        
        if (this.queue.length > 0) {
            // Show notification
            this.showNotification('Connection restored. Syncing changes...', 'info');
            this.sync();
        }
    }
    
    // Handle going offline
    handleOffline() {
        console.log('Connection lost');
        this.isOnline = false;
        this.showNotification('Working offline. Changes will sync when connection is restored.', 'warning');
    }
    
    // Sync queued operations
    async sync() {
        if (this.isSyncing || this.queue.length === 0) {
            return;
        }
        
        this.isSyncing = true;
        console.log(`Starting sync of ${this.queue.length} operations`);
        
        const completed = [];
        const failed = [];
        
        for (const operation of this.queue) {
            try {
                await this.executeOperation(operation);
                completed.push(operation.id);
            } catch (error) {
                console.error('Failed to sync operation:', operation, error);
                operation.retries++;
                
                if (operation.retries >= this.options.maxRetries) {
                    failed.push(operation);
                    completed.push(operation.id); // Remove from queue
                    this.options.onError(operation, error);
                }
            }
        }
        
        // Remove completed operations
        if (completed.length > 0) {
            this.queue = this.queue.filter(item => !completed.includes(item.id));
            this.saveQueue();
        }
        
        // Notify about results
        if (completed.length > 0) {
            const successCount = completed.length - failed.length;
            if (successCount > 0) {
                this.showNotification(`Synced ${successCount} changes successfully`, 'success');
            }
            
            if (failed.length > 0) {
                this.showNotification(`Failed to sync ${failed.length} changes`, 'error');
            }
            
            this.options.onSync(completed, failed);
        }
        
        this.isSyncing = false;
        
        // Schedule retry if there are still items
        if (this.queue.length > 0) {
            setTimeout(() => this.sync(), this.options.retryDelay);
        }
    }
    
    // Execute a single operation
    async executeOperation(operation) {
        switch (operation.type) {
            case 'updateDocument':
                return await this.updateDocument(operation);
            case 'createDocument':
                return await this.createDocument(operation);
            case 'deleteDocument':
                return await this.deleteDocument(operation);
            case 'createFolder':
                return await this.createFolder(operation);
            default:
                throw new Error(`Unknown operation type: ${operation.type}`);
        }
    }
    
    // Update document operation
    async updateDocument(operation) {
        const response = await fetch(`/api/context/documents/${operation.documentId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: operation.name,
                content: operation.content
            })
        });
        
        if (!response.ok) {
            throw new Error(`Failed to update document: ${response.status}`);
        }
        
        return await response.json();
    }
    
    // Create document operation
    async createDocument(operation) {
        const response = await fetch('/api/context/documents', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: operation.name,
                content: operation.content,
                folder_id: operation.folderId
            })
        });
        
        if (!response.ok) {
            throw new Error(`Failed to create document: ${response.status}`);
        }
        
        return await response.json();
    }
    
    // Delete document operation
    async deleteDocument(operation) {
        const response = await fetch(`/api/context/documents/${operation.documentId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            throw new Error(`Failed to delete document: ${response.status}`);
        }
        
        return { success: true };
    }
    
    // Create folder operation
    async createFolder(operation) {
        const response = await fetch('/api/context/folders', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: operation.name,
                parent_id: operation.parentId
            })
        });
        
        if (!response.ok) {
            throw new Error(`Failed to create folder: ${response.status}`);
        }
        
        return await response.json();
    }
    
    // Show notification
    showNotification(message, type = 'info') {
        // You can replace this with a better notification system
        const notification = document.createElement('div');
        notification.className = `offline-queue-notification ${type}`;
        notification.textContent = message;
        
        // Style the notification
        notification.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 4px;
            font-size: 14px;
            z-index: 10000;
            animation: slideIn 0.3s ease;
        `;
        
        // Set color based on type
        switch (type) {
            case 'success':
                notification.style.background = '#10b981';
                notification.style.color = 'white';
                break;
            case 'error':
                notification.style.background = '#ef4444';
                notification.style.color = 'white';
                break;
            case 'warning':
                notification.style.background = '#f59e0b';
                notification.style.color = 'white';
                break;
            default:
                notification.style.background = '#3b82f6';
                notification.style.color = 'white';
        }
        
        document.body.appendChild(notification);
        
        // Remove after 5 seconds
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => notification.remove(), 300);
        }, 5000);
    }
    
    // Get queue status
    getStatus() {
        return {
            isOnline: this.isOnline,
            isSyncing: this.isSyncing,
            queueLength: this.queue.length,
            oldestOperation: this.queue.length > 0 ? new Date(this.queue[0].timestamp) : null
        };
    }
    
    // Clear queue (use with caution)
    clear() {
        this.queue = [];
        this.saveQueue();
    }
}

// Add CSS for notifications
const style = document.createElement('style');
style.textContent = `
@keyframes slideIn {
    from {
        transform: translateX(100%);
        opacity: 0;
    }
    to {
        transform: translateX(0);
        opacity: 1;
    }
}

@keyframes slideOut {
    from {
        transform: translateX(0);
        opacity: 1;
    }
    to {
        transform: translateX(100%);
        opacity: 0;
    }
}
`;
document.head.appendChild(style);

// Export for use
window.OfflineQueue = OfflineQueue;