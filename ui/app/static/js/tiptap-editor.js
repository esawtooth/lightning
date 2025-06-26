// TipTap Editor Component for Context Hub
// Uses TipTap via CDN for rich text editing with CRDT-aware auto-save

class ContextHubEditor {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = {
            onUpdate: () => {},
            onSave: () => {},
            content: '',
            readOnly: false,
            ...options
        };
        
        this.editor = null;
        this.saveTimeout = null;
        this.saveStatus = 'saved';
        this.isInitialized = false;
        this.offlineQueue = null;
        
        // Initialize when TipTap is loaded
        this.waitForTipTap().then(() => this.initialize());
    }
    
    async waitForTipTap() {
        // Wait for TipTap to be available from CDN
        while (!window.TipTap || !window.TipTapStarterKit) {
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    }
    
    initialize() {
        const { Editor } = window.TipTap;
        const StarterKit = window.TipTapStarterKit;
        
        // Create editor container structure
        this.container.innerHTML = `
            <div class="tiptap-editor-container">
                <div class="tiptap-toolbar" id="${this.container.id}-toolbar"></div>
                <div class="tiptap-editor" id="${this.container.id}-editor"></div>
                <div class="tiptap-status">
                    <span class="save-status">
                        <span class="status-icon" id="${this.container.id}-status-icon">✓</span>
                        <span class="status-text" id="${this.container.id}-status-text">Saved</span>
                    </span>
                    <span class="word-count" id="${this.container.id}-word-count">0 words</span>
                </div>
            </div>
        `;
        
        // Initialize TipTap editor
        this.editor = new Editor({
            element: document.getElementById(`${this.container.id}-editor`),
            extensions: [
                StarterKit.configure({
                    heading: {
                        levels: [1, 2, 3]
                    }
                })
            ],
            content: this.options.content,
            editable: !this.options.readOnly,
            onUpdate: ({ editor }) => {
                this.handleUpdate(editor);
            }
        });
        
        // Create toolbar
        this.createToolbar();
        
        // Update initial word count
        this.updateWordCount();
        
        this.isInitialized = true;
    }
    
    createToolbar() {
        const toolbar = document.getElementById(`${this.container.id}-toolbar`);
        
        const buttons = [
            {
                icon: 'B',
                title: 'Bold',
                action: () => this.editor.chain().focus().toggleBold().run(),
                isActive: () => this.editor.isActive('bold')
            },
            {
                icon: 'I',
                title: 'Italic',
                action: () => this.editor.chain().focus().toggleItalic().run(),
                isActive: () => this.editor.isActive('italic')
            },
            {
                icon: 'S',
                title: 'Strike',
                action: () => this.editor.chain().focus().toggleStrike().run(),
                isActive: () => this.editor.isActive('strike')
            },
            { type: 'separator' },
            {
                icon: 'H1',
                title: 'Heading 1',
                action: () => this.editor.chain().focus().toggleHeading({ level: 1 }).run(),
                isActive: () => this.editor.isActive('heading', { level: 1 })
            },
            {
                icon: 'H2',
                title: 'Heading 2',
                action: () => this.editor.chain().focus().toggleHeading({ level: 2 }).run(),
                isActive: () => this.editor.isActive('heading', { level: 2 })
            },
            {
                icon: 'H3',
                title: 'Heading 3',
                action: () => this.editor.chain().focus().toggleHeading({ level: 3 }).run(),
                isActive: () => this.editor.isActive('heading', { level: 3 })
            },
            { type: 'separator' },
            {
                icon: '•',
                title: 'Bullet List',
                action: () => this.editor.chain().focus().toggleBulletList().run(),
                isActive: () => this.editor.isActive('bulletList')
            },
            {
                icon: '1.',
                title: 'Numbered List',
                action: () => this.editor.chain().focus().toggleOrderedList().run(),
                isActive: () => this.editor.isActive('orderedList')
            },
            { type: 'separator' },
            {
                icon: '"',
                title: 'Blockquote',
                action: () => this.editor.chain().focus().toggleBlockquote().run(),
                isActive: () => this.editor.isActive('blockquote')
            },
            {
                icon: '</> ',
                title: 'Code Block',
                action: () => this.editor.chain().focus().toggleCodeBlock().run(),
                isActive: () => this.editor.isActive('codeBlock')
            },
            { type: 'separator' },
            {
                icon: '↶',
                title: 'Undo',
                action: () => this.editor.chain().focus().undo().run(),
                isActive: () => false
            },
            {
                icon: '↷',
                title: 'Redo',
                action: () => this.editor.chain().focus().redo().run(),
                isActive: () => false
            }
        ];
        
        // Create toolbar buttons
        buttons.forEach(btn => {
            if (btn.type === 'separator') {
                const sep = document.createElement('span');
                sep.className = 'toolbar-separator';
                sep.textContent = '|';
                toolbar.appendChild(sep);
            } else {
                const button = document.createElement('button');
                button.className = 'toolbar-btn';
                button.innerHTML = btn.icon;
                button.title = btn.title;
                button.onclick = (e) => {
                    e.preventDefault();
                    btn.action();
                };
                
                // Update active state
                if (btn.isActive) {
                    this.editor.on('update', () => {
                        button.classList.toggle('active', btn.isActive());
                    });
                    // Set initial state
                    button.classList.toggle('active', btn.isActive());
                }
                
                toolbar.appendChild(button);
            }
        });
    }
    
    handleUpdate(editor) {
        // Update word count
        this.updateWordCount();
        
        // Clear existing timeout
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }
        
        // Set save status to saving
        this.setSaveStatus('saving');
        
        // Debounce save (2 seconds)
        this.saveTimeout = setTimeout(() => {
            this.save();
        }, 2000);
        
        // Call update callback
        this.options.onUpdate(editor);
    }
    
    async save() {
        try {
            const content = this.editor.getHTML();
            await this.options.onSave(content);
            this.setSaveStatus('saved');
        } catch (error) {
            console.error('Save failed:', error);
            this.setSaveStatus('offline');
            
            // Add to offline queue if available
            if (window.offlineQueue && this.options.documentId) {
                window.offlineQueue.add({
                    type: 'updateDocument',
                    documentId: this.options.documentId,
                    name: this.options.documentName || 'Untitled',
                    content: content
                });
            }
        }
    }
    
    setSaveStatus(status) {
        this.saveStatus = status;
        const icon = document.getElementById(`${this.container.id}-status-icon`);
        const text = document.getElementById(`${this.container.id}-status-text`);
        
        switch (status) {
            case 'saving':
                icon.textContent = '⟳';
                icon.className = 'status-icon saving';
                text.textContent = 'Saving...';
                break;
            case 'saved':
                icon.textContent = '✓';
                icon.className = 'status-icon saved';
                text.textContent = 'Saved';
                break;
            case 'offline':
                icon.textContent = '○';
                icon.className = 'status-icon offline';
                text.textContent = 'Offline (will sync)';
                break;
        }
    }
    
    updateWordCount() {
        if (!this.editor) return;
        
        const text = this.editor.state.doc.textContent;
        const words = text.trim().split(/\s+/).filter(word => word.length > 0).length;
        const wordCountEl = document.getElementById(`${this.container.id}-word-count`);
        if (wordCountEl) {
            wordCountEl.textContent = `${words} ${words === 1 ? 'word' : 'words'}`;
        }
    }
    
    setContent(content) {
        if (this.editor) {
            this.editor.commands.setContent(content);
        }
    }
    
    getContent() {
        return this.editor ? this.editor.getHTML() : '';
    }
    
    setReadOnly(readOnly) {
        if (this.editor) {
            this.editor.setEditable(!readOnly);
        }
    }
    
    focus() {
        if (this.editor) {
            this.editor.chain().focus().run();
        }
    }
    
    destroy() {
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }
        if (this.editor) {
            this.editor.destroy();
        }
    }
}

// Export for use in context.html
window.ContextHubEditor = ContextHubEditor;