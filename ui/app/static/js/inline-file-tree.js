// Enhanced File Tree with Inline Editing for Context Hub
// Provides VS Code-style inline file/folder creation and editing

class InlineFileTree {
    constructor(options = {}) {
        this.options = {
            onCreateFile: () => {},
            onCreateFolder: () => {},
            onRename: () => {},
            onDelete: () => {},
            onSelect: () => {},
            ...options
        };
        
        this.tempNodes = new Map(); // Track temporary nodes
        this.editingNodeId = null;
        this.selectedNodeId = null;
    }
    
    // Create a new file inline
    async createFileInline(parentFolderId) {
        const tempId = `temp-file-${Date.now()}`;
        const tempNode = {
            id: tempId,
            text: this.createInlineEditNode('', tempId, 'file'),
            icon: 'fas fa-file-alt',
            type: 'file',
            data: {
                id: tempId,
                name: '',
                isTemp: true,
                parentId: parentFolderId
            }
        };
        
        // Add to JSTree
        const tree = $('#folder-browser').jstree(true);
        const parentNode = parentFolderId ? tree.get_node(parentFolderId) : '#';
        const newNodeId = tree.create_node(parentNode, tempNode);
        
        // Store temp node reference
        this.tempNodes.set(tempId, { jsTreeId: newNodeId, data: tempNode.data });
        
        // Focus the input
        setTimeout(() => {
            this.focusInlineEdit(tempId);
        }, 50);
        
        return tempId;
    }
    
    // Create a new folder inline
    async createFolderInline(parentFolderId) {
        const tempId = `temp-folder-${Date.now()}`;
        const tempNode = {
            id: tempId,
            text: this.createInlineEditNode('New Folder', tempId, 'folder'),
            icon: 'fas fa-folder',
            type: 'folder',
            data: {
                id: tempId,
                name: 'New Folder',
                isTemp: true,
                parentId: parentFolderId
            },
            children: []
        };
        
        // Add to JSTree
        const tree = $('#folder-browser').jstree(true);
        const parentNode = parentFolderId ? tree.get_node(parentFolderId) : '#';
        const newNodeId = tree.create_node(parentNode, tempNode);
        
        // Store temp node reference
        this.tempNodes.set(tempId, { jsTreeId: newNodeId, data: tempNode.data });
        
        // Focus and select the input text
        setTimeout(() => {
            const input = this.focusInlineEdit(tempId);
            if (input) {
                input.select();
            }
        }, 50);
        
        return tempId;
    }
    
    // Create inline edit HTML
    createInlineEditNode(defaultName, nodeId, type) {
        const icon = type === 'folder' ? 'fa-folder' : 'fa-file-alt';
        return `
            <span class="inline-edit-container">
                <i class="fas ${icon} mr-1 text-gray-600"></i>
                <input 
                    type="text" 
                    class="inline-edit-input" 
                    id="edit-${nodeId}"
                    value="${defaultName}"
                    placeholder="${type === 'folder' ? 'Folder name' : 'File name'}"
                    data-node-id="${nodeId}"
                    data-node-type="${type}"
                />
            </span>
        `;
    }
    
    // Focus inline edit input
    focusInlineEdit(nodeId) {
        const input = document.getElementById(`edit-${nodeId}`);
        if (input) {
            input.focus();
            
            // Bind events
            input.addEventListener('keydown', (e) => this.handleInlineEditKeydown(e));
            input.addEventListener('blur', (e) => this.handleInlineEditBlur(e));
            
            this.editingNodeId = nodeId;
        }
        return input;
    }
    
    // Handle keydown in inline edit
    handleInlineEditKeydown(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            this.confirmInlineEdit(event.target);
        } else if (event.key === 'Escape') {
            event.preventDefault();
            this.cancelInlineEdit(event.target);
        }
    }
    
    // Handle blur in inline edit
    handleInlineEditBlur(event) {
        // Small delay to allow for click events on other elements
        setTimeout(() => {
            if (this.editingNodeId === event.target.dataset.nodeId) {
                this.confirmInlineEdit(event.target);
            }
        }, 200);
    }
    
    // Confirm inline edit
    async confirmInlineEdit(input) {
        const nodeId = input.dataset.nodeId;
        const nodeType = input.dataset.nodeType;
        const name = input.value.trim();
        
        if (!name) {
            this.cancelInlineEdit(input);
            return;
        }
        
        const tempNode = this.tempNodes.get(nodeId);
        if (tempNode) {
            // This is a new node
            try {
                let result;
                if (nodeType === 'folder') {
                    result = await this.options.onCreateFolder(name, tempNode.data.parentId);
                } else {
                    result = await this.options.onCreateFile(name, '', tempNode.data.parentId);
                }
                
                if (result && result.id) {
                    // Update the tree with the real node
                    const tree = $('#folder-browser').jstree(true);
                    const node = tree.get_node(tempNode.jsTreeId);
                    if (node) {
                        // Update node properties
                        tree.set_id(node, result.id);
                        tree.set_text(node, this.createNodeText(result.name, nodeType, result.id));
                        
                        // Update node data
                        node.data = {
                            id: result.id,
                            name: result.name,
                            isTemp: false
                        };
                    }
                }
            } catch (error) {
                console.error('Failed to create:', error);
                this.cancelInlineEdit(input);
                return;
            }
            
            // Clean up temp node
            this.tempNodes.delete(nodeId);
        } else {
            // This is a rename operation
            try {
                await this.options.onRename(nodeId, name, nodeType);
                
                // Update the tree
                const tree = $('#folder-browser').jstree(true);
                const node = tree.get_node(nodeId);
                if (node) {
                    tree.set_text(node, this.createNodeText(name, nodeType, nodeId));
                    if (node.data) {
                        node.data.name = name;
                    }
                }
            } catch (error) {
                console.error('Failed to rename:', error);
            }
        }
        
        this.editingNodeId = null;
    }
    
    // Cancel inline edit
    cancelInlineEdit(input) {
        const nodeId = input.dataset.nodeId;
        const tempNode = this.tempNodes.get(nodeId);
        
        if (tempNode) {
            // Remove temporary node
            const tree = $('#folder-browser').jstree(true);
            tree.delete_node(tempNode.jsTreeId);
            this.tempNodes.delete(nodeId);
        } else {
            // Restore original text for rename
            const tree = $('#folder-browser').jstree(true);
            const node = tree.get_node(nodeId);
            if (node && node.data && node.data.name) {
                const nodeType = node.type || (node.children && node.children.length >= 0 ? 'folder' : 'file');
                tree.set_text(node, this.createNodeText(node.data.name, nodeType, nodeId));
            }
        }
        
        this.editingNodeId = null;
    }
    
    // Create node text with action buttons
    createNodeText(name, type, nodeId) {
        const isFolder = type === 'folder';
        const actions = `
            <span class="tree-actions" style="float: right; margin-left: 20px;">
                ${isFolder ? `<i class="fas fa-plus text-green-500 hover:text-green-700 cursor-pointer mr-1" 
                   onclick="event.stopPropagation(); window.fileTree.showQuickCreate('${nodeId}')" 
                   title="Add to folder"></i>` : ''}
                <i class="fas fa-edit text-blue-500 hover:text-blue-700 cursor-pointer mr-1" 
                   onclick="event.stopPropagation(); window.fileTree.startRename('${nodeId}')" 
                   title="Rename"></i>
                <i class="fas fa-trash text-red-500 hover:text-red-700 cursor-pointer" 
                   onclick="event.stopPropagation(); window.fileTree.deleteNode('${nodeId}', '${type}')" 
                   title="Delete"></i>
            </span>
        `;
        
        return name + actions;
    }
    
    // Start rename operation
    startRename(nodeId) {
        const tree = $('#folder-browser').jstree(true);
        const node = tree.get_node(nodeId);
        
        if (node && node.data) {
            const nodeType = node.type || (node.children && node.children.length >= 0 ? 'folder' : 'file');
            const editHtml = this.createInlineEditNode(node.data.name, nodeId, nodeType);
            tree.set_text(node, editHtml);
            
            setTimeout(() => {
                const input = this.focusInlineEdit(nodeId);
                if (input) {
                    input.select();
                }
            }, 50);
        }
    }
    
    // Delete node
    async deleteNode(nodeId, nodeType) {
        if (confirm(`Are you sure you want to delete this ${nodeType}?`)) {
            try {
                await this.options.onDelete(nodeId, nodeType);
                
                // Remove from tree
                const tree = $('#folder-browser').jstree(true);
                tree.delete_node(nodeId);
            } catch (error) {
                console.error('Failed to delete:', error);
            }
        }
    }
    
    // Show quick create menu
    showQuickCreate(folderId) {
        // For now, default to creating a file
        // Could show a small menu to choose between file/folder
        this.createFileInline(folderId);
    }
    
    // Setup keyboard shortcuts
    setupKeyboardShortcuts() {
        $(document).on('keydown', (e) => {
            const tree = $('#folder-browser').jstree(true);
            const selected = tree.get_selected();
            
            if (selected.length === 0 || this.editingNodeId) return;
            
            const selectedId = selected[0];
            const node = tree.get_node(selectedId);
            
            // Ctrl/Cmd + N: New file
            if ((e.ctrlKey || e.metaKey) && e.key === 'n' && !e.shiftKey) {
                e.preventDefault();
                const parentId = node.type === 'folder' ? selectedId : node.parent;
                this.createFileInline(parentId !== '#' ? parentId : null);
            }
            
            // Ctrl/Cmd + Shift + N: New folder
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'N') {
                e.preventDefault();
                const parentId = node.type === 'folder' ? selectedId : node.parent;
                this.createFolderInline(parentId !== '#' ? parentId : null);
            }
            
            // F2: Rename
            if (e.key === 'F2') {
                e.preventDefault();
                this.startRename(selectedId);
            }
            
            // Delete: Delete
            if (e.key === 'Delete') {
                e.preventDefault();
                const nodeType = node.type || (node.children && node.children.length >= 0 ? 'folder' : 'file');
                this.deleteNode(selectedId, nodeType);
            }
        });
    }
}

// Export for use
window.InlineFileTree = InlineFileTree;