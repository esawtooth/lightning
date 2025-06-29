import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Crepe } from '@milkdown/crepe'
import '@milkdown/crepe/theme/common/style.css'
import '@milkdown/crepe/theme/frame.css'

// Debounce utility
const debounce = (func, wait) => {
  let timeout
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout)
      func(...args)
    }
    clearTimeout(timeout)
    timeout = setTimeout(later, wait)
  }
}

const Context = () => {
  const [contextStatus, setContextStatus] = useState(null)
  const [folders, setFolders] = useState(null)
  const [selectedDocument, setSelectedDocument] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [contextMenu, setContextMenu] = useState(null)
  const [editingItem, setEditingItem] = useState(null)
  const [draggedItem, setDraggedItem] = useState(null)
  const [expandedFolders, setExpandedFolders] = useState(new Set())
  const [selectedFolder, setSelectedFolder] = useState(null)
  const [creatingItem, setCreatingItem] = useState(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [saveStatus, setSaveStatus] = useState(null) // 'saving', 'saved', 'error'
  const [isLoadingDocument, setIsLoadingDocument] = useState(false)
  const [undoNotification, setUndoNotification] = useState(null)
  const [actionHistory, setActionHistory] = useState([]) // Store recent actions for undo
  const [redoStack, setRedoStack] = useState([]) // Store undone actions for redo
  const editorRef = useRef(null)
  const crepeEditor = useRef(null)
  const autoSaveTimer = useRef(null)
  const mutationObserver = useRef(null)
  const undoTimeoutRef = useRef(null)

  useEffect(() => {
    loadContextStatus()
  }, [])

  useEffect(() => {
    if (selectedDocument && editorRef.current && !isLoadingDocument) {
      // Clean up previous editor
      if (crepeEditor.current) {
        cleanupEditor()
      }
      initializeCrepeEditor()
    }
    
    // Cleanup on unmount or document change
    return () => {
      // Save any pending changes before cleanup
      if (crepeEditor.current && selectedDocument?.id && autoSaveTimer.current) {
        clearTimeout(autoSaveTimer.current)
        // Force immediate save on unmount
        handleSaveDocument(true)
      }
      cleanupEditor()
    }
  }, [selectedDocument, isLoadingDocument])

  useEffect(() => {
    const handleClickOutside = () => {
      if (contextMenu) {
        closeContextMenu()
      }
    }

    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [contextMenu])

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isFullscreen])

  useEffect(() => {
    // Auto-expand folders that have documents or are root level
    if (folders?.tree) {
      const autoExpandFolders = new Set(expandedFolders)
      const findFoldersToExpand = (tree, isRoot = true) => {
        tree.forEach(folder => {
          // Auto-expand root level folders and folders with content
          if (isRoot || (folder.documents && folder.documents.length > 0) || (folder.subfolders && folder.subfolders.length > 0)) {
            autoExpandFolders.add(folder.id)
          }
          if (folder.subfolders && folder.subfolders.length > 0) {
            findFoldersToExpand(folder.subfolders, false)
          }
        })
      }
      findFoldersToExpand(folders.tree)
      setExpandedFolders(autoExpandFolders)
    }
  }, [folders])

  const showUndoNotification = (message, undoAction) => {
    // Clear any existing timeout
    if (undoTimeoutRef.current) {
      clearTimeout(undoTimeoutRef.current)
    }
    
    // Show notification
    setUndoNotification({ message, undoAction })
    
    // Auto-hide after 5 seconds
    undoTimeoutRef.current = setTimeout(() => {
      setUndoNotification(null)
    }, 5000)
  }

  const performUndo = async () => {
    if (actionHistory.length === 0) return
    
    const lastAction = actionHistory[actionHistory.length - 1]
    setActionHistory(prev => prev.slice(0, -1))
    
    try {
      switch (lastAction.type) {
        case 'delete':
          // Restore deleted item
          const item = lastAction.item
          
          if (item.doc_type === 'Folder') {
            // Restore folder
            const response = await fetch('/api/context/folders', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                name: item.name,
                description: item.description || '',
                parent_folder_id: item.parent_folder_id || null
              })
            })
            
            if (!response.ok) {
              throw new Error('Failed to restore folder')
            }
          } else {
            // Restore document
            const response = await fetch('/api/context/documents', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                name: item.name,
                content: item.content || `# ${item.name}\n\nRestored document`,
                folder_id: item.folder_id || null
              })
            })
            
            if (!response.ok) {
              throw new Error('Failed to restore document')
            }
            
            const restoredDoc = await response.json()
            // If this was the selected document, select the restored one
            if (selectedDocument?.id === item.id) {
              setSelectedDocument(restoredDoc)
            }
          }
          
          showUndoNotification(`Restored "${item.name}"`, null)
          break
          
        case 'create':
          // Delete the created item
          await handleDelete(lastAction.item, false) // false = no undo for this delete
          break
          
        case 'rename':
          // Rename back to original name
          // TODO: Implement rename functionality
          break
      }
      
      // Add to redo stack
      setRedoStack(prev => [...prev, lastAction])
      
      // Reload folders to refresh UI
      await loadFolders()
    } catch (error) {
      console.error('Undo failed:', error)
      showUndoNotification('Undo failed', null)
    }
    
    // Hide notification
    setUndoNotification(null)
  }

  const performRedo = async () => {
    if (redoStack.length === 0) return
    
    const action = redoStack[redoStack.length - 1]
    setRedoStack(prev => prev.slice(0, -1))
    
    // Re-perform the action
    // Implementation would be similar to undo but in reverse
    
    // Add back to history
    setActionHistory(prev => [...prev, action])
  }

  const loadContextStatus = async () => {
    try {
      const response = await fetch('/api/context/status')
      if (response.ok) {
        const data = await response.json()
        setContextStatus(data)
        if (data.initialized) {
          loadFolders()
        }
      } else {
        setContextStatus({ initialized: false })
      }
    } catch (error) {
      console.error('Failed to load context status:', error)
      setContextStatus({ initialized: false })
    }
  }

  const loadFolders = async () => {
    try {
      const response = await fetch('/api/context/folders')
      if (response.ok) {
        const data = await response.json()
        
        // If no folders exist, create a default structure
        if (!data.tree || data.tree.length === 0) {
          await createDefaultFolders()
          // Reload after creating defaults
          const retryResponse = await fetch('/api/context/folders')
          if (retryResponse.ok) {
            const retryData = await retryResponse.json()
            setFolders(retryData)
          }
        } else {
          setFolders(data)
        }
      }
    } catch (error) {
      console.error('Failed to load folders:', error)
    }
  }

  const createDefaultFolders = async () => {
    try {
      // Create default folders
      const defaultFolders = [
        { name: 'Documents', description: 'General documents and notes' },
        { name: 'Projects', description: 'Project-specific content' },
        { name: 'Archive', description: 'Archived content' }
      ]
      
      for (const folder of defaultFolders) {
        await fetch('/api/context/folders', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(folder)
        })
      }
    } catch (error) {
      console.error('Error creating default folders:', error)
    }
  }

  const initializeContext = async () => {
    try {
      const response = await fetch('/api/context/initialize', { method: 'POST' })
      if (response.ok) {
        loadContextStatus()
      }
    } catch (error) {
      console.error('Error initializing context:', error)
    }
  }

  const cleanupEditor = () => {
    // Cancel any pending auto-saves
    if (autoSaveTimer.current) {
      clearTimeout(autoSaveTimer.current)
      autoSaveTimer.current = null
    }
    
    // Clear periodic save interval
    if (editorRef.current?.periodicSaveInterval) {
      clearInterval(editorRef.current.periodicSaveInterval)
      editorRef.current.periodicSaveInterval = null
    }
    
    // Disconnect mutation observer
    if (mutationObserver.current) {
      mutationObserver.current.disconnect()
      mutationObserver.current = null
    }
    
    // Remove event listeners
    const editorElement = editorRef.current?.querySelector('.ProseMirror')
    if (editorElement) {
      editorElement.removeEventListener('input', () => {})
    }
    
    // Clear editor instance
    if (crepeEditor.current) {
      crepeEditor.current = null
    }
  }

  const initializeCrepeEditor = async () => {
    if (!editorRef.current || !selectedDocument || !selectedDocument.id) {
      console.warn('Cannot initialize editor: missing requirements')
      return
    }

    try {
      // Clear the container
      editorRef.current.innerHTML = ''

      // Create the Crepe editor instance
      crepeEditor.current = new Crepe({
        root: editorRef.current,
        defaultValue: selectedDocument.content || '# Start writing...\n\nYour content here.',
        features: {
          [Crepe.Feature.CodeMirror]: true,
          [Crepe.Feature.ListItem]: true,
          [Crepe.Feature.BlockEdit]: true,
          [Crepe.Feature.Cursor]: true,
          [Crepe.Feature.Diagram]: true,
          [Crepe.Feature.Emoji]: true,
          [Crepe.Feature.Image]: true,
          [Crepe.Feature.Indent]: true,
          [Crepe.Feature.Link]: true,
          [Crepe.Feature.Math]: true,
          [Crepe.Feature.Table]: true,
          [Crepe.Feature.Tooltip]: true,
          [Crepe.Feature.Upload]: true,
        }
      })

      // Initialize the editor
      await crepeEditor.current.create()

      // Get the Milkdown editor instance to listen for changes
      const editor = crepeEditor.current.editor
      
      // Function to handle content changes
      const handleContentChange = () => {
        // Clear any existing timer
        if (autoSaveTimer.current) {
          clearTimeout(autoSaveTimer.current)
        }
        
        // Set a new timer to save after 1 second of inactivity (reduced from 2)
        autoSaveTimer.current = setTimeout(() => {
          handleSaveDocument(true) // true = auto-save
        }, 1000)
      }

      // Set up auto-save using multiple methods for better reliability
      
      // Method 1: Listen to editor transactions (most reliable)
      if (editor) {
        editor.onTransaction = () => {
          handleContentChange()
        }
      }
      
      // Method 2: MutationObserver as fallback
      mutationObserver.current = new MutationObserver(handleContentChange)
      
      // Observe changes in the editor DOM
      const editorElement = editorRef.current.querySelector('.ProseMirror')
      if (editorElement) {
        mutationObserver.current.observe(editorElement, {
          childList: true,
          subtree: true,
          characterData: true,
          attributes: true
        })
        
        // Method 3: Input event listener
        editorElement.addEventListener('input', handleContentChange)
        
        // Method 4: Periodic save every 5 seconds if content has changed
        let lastContent = selectedDocument.content || ''
        const periodicSaveInterval = setInterval(() => {
          if (crepeEditor.current && selectedDocument?.id) {
            const currentContent = crepeEditor.current.getMarkdown()
            if (currentContent !== lastContent) {
              lastContent = currentContent
              handleSaveDocument(true)
            }
          }
        }, 5000)
        
        // Store interval ID for cleanup
        editorRef.current.periodicSaveInterval = periodicSaveInterval
      }

      console.log('Crepe editor initialized successfully!')
    } catch (error) {
      console.error('Failed to initialize Crepe editor:', error)
    }
  }

  const loadDocument = async (doc) => {
    // Prevent loading if already loading
    if (isLoadingDocument) return
    
    // Cancel any pending auto-saves from previous document
    if (autoSaveTimer.current) {
      clearTimeout(autoSaveTimer.current)
      autoSaveTimer.current = null
    }
    
    try {
      setIsLoadingDocument(true)
      cleanupEditor() // Clean up previous editor
      
      const response = await fetch(`/api/context/documents/${doc.id}`)
      if (response.ok) {
        const docData = await response.json()
        setSelectedDocument(docData)
        setSaveStatus('saved') // Reset save status
      }
    } catch (error) {
      console.error('Error loading document:', error)
      setSaveStatus('error')
    } finally {
      setIsLoadingDocument(false)
    }
  }

  const handleSaveDocument = async (isAutoSave = false) => {
    // Validate prerequisites
    if (!selectedDocument || !crepeEditor.current || !selectedDocument.id) {
      console.warn('Cannot save: document not properly loaded', {
        hasDocument: !!selectedDocument,
        hasEditor: !!crepeEditor.current,
        hasId: selectedDocument?.id
      })
      return
    }
    
    // Don't save while loading
    if (isLoadingDocument) {
      console.warn('Cannot save: document is loading')
      return
    }

    try {
      setSaveStatus('saving')
      
      // Get the current content from the editor
      const content = crepeEditor.current.getMarkdown()
      
      // Update the document
      const response = await fetch(`/api/context/documents/${selectedDocument.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...selectedDocument,
          content
        })
      })

      if (response.ok) {
        const updatedDoc = await response.json()
        setSelectedDocument(updatedDoc)
        setSaveStatus('saved')
        
        if (!isAutoSave) {
          // Show save confirmation for manual saves
          console.log('Document saved successfully!')
          // Clear save status after 3 seconds
          setTimeout(() => setSaveStatus(null), 3000)
        } else {
          // For auto-save, clear status after 1 second
          setTimeout(() => setSaveStatus(null), 1000)
        }
      } else {
        console.error('Failed to save document:', response.status, response.statusText)
        setSaveStatus('error')
      }
    } catch (error) {
      console.error('Error saving document:', error)
      setSaveStatus('error')
    }
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) return

    try {
      const response = await fetch(`/api/context/search?q=${encodeURIComponent(searchQuery)}&limit=10`)
      if (response.ok) {
        const data = await response.json()
        setSearchResults(data)
      }
    } catch (error) {
      console.error('Search error:', error)
    }
  }

  const handleCreateFolder = async (parentFolder = null) => {
    const tempId = `creating-folder-${Date.now()}`
    const targetFolder = parentFolder || selectedFolder
    setCreatingItem({
      id: tempId,
      type: 'folder',
      parentId: targetFolder?.id || null,
      name: ''
    })
    // Expand the target folder if it exists
    if (targetFolder) {
      setExpandedFolders(prev => new Set([...prev, targetFolder.id]))
    }
  }

  const handleCreateDocument = async (folder = null) => {
    const tempId = `creating-document-${Date.now()}`
    const targetFolder = folder || selectedFolder
    setCreatingItem({
      id: tempId,
      type: 'document',
      parentId: targetFolder?.id || null,
      name: ''
    })
    // Expand the target folder if it exists
    if (targetFolder) {
      setExpandedFolders(prev => new Set([...prev, targetFolder.id]))
    }
  }

  // Context menu handlers
  const handleContextMenu = (e, item, type) => {
    e.preventDefault()
    e.stopPropagation()
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      item,
      type
    })
  }

  const closeContextMenu = () => {
    setContextMenu(null)
  }

  const handleRename = (item) => {
    setEditingItem(item)
    closeContextMenu()
  }

  const handleDelete = async (item, trackForUndo = true) => {
    try {
      // If it's a document, fetch its content before deletion for undo
      let documentContent = null
      if (item.doc_type !== 'Folder' && trackForUndo) {
        try {
          const docResponse = await fetch(`/api/context/documents/${item.id}`)
          if (docResponse.ok) {
            const docData = await docResponse.json()
            documentContent = docData.content
          }
        } catch (err) {
          console.error('Failed to fetch document content for undo:', err)
        }
      }
      
      const endpoint = item.doc_type === 'Folder' ? 'folders' : 'documents'
      const response = await fetch(`/api/context/${endpoint}/${item.id}`, {
        method: 'DELETE'
      })
      
      if (response.ok) {
        await loadFolders()
        
        if (trackForUndo) {
          // Add to action history with content for restoration
          setActionHistory(prev => [...prev, {
            type: 'delete',
            item: {
              ...item,
              content: documentContent // Store content for documents
            },
            timestamp: new Date()
          }])
          
          // Clear redo stack when new action is performed
          setRedoStack([])
          
          // Show undo notification
          showUndoNotification(`Deleted "${item.name}"`, performUndo)
        }
      } else {
        console.error('Failed to delete item')
      }
    } catch (error) {
      console.error('Error deleting item:', error)
    }
    closeContextMenu()
  }

  const handleCreateSubFolder = async (parentFolder) => {
    const tempId = `creating-folder-${Date.now()}`
    setCreatingItem({
      id: tempId,
      type: 'folder',
      parentId: parentFolder.id,
      name: ''
    })
    setExpandedFolders(prev => new Set([...prev, parentFolder.id]))
    closeContextMenu()
  }

  const handleCreateDocumentInFolder = async (folder) => {
    const tempId = `creating-document-${Date.now()}`
    setCreatingItem({
      id: tempId,
      type: 'document',
      parentId: folder.id,
      name: ''
    })
    setExpandedFolders(prev => new Set([...prev, folder.id]))
    closeContextMenu()
  }

  const toggleFolder = (folderId) => {
    setExpandedFolders(prev => {
      const newSet = new Set(prev)
      if (newSet.has(folderId)) {
        newSet.delete(folderId)
      } else {
        newSet.add(folderId)
      }
      return newSet
    })
  }

  const selectFolder = (folder) => {
    setSelectedFolder(folder)
  }

  const handleCreateItemSubmit = async (name) => {
    if (!name?.trim() || !creatingItem) return

    try {
      if (creatingItem.type === 'folder') {
        const response = await fetch('/api/context/folders', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: name.trim(),
            description: '',
            parent_folder_id: creatingItem.parentId
          })
        })
        
        if (response.ok) {
          await loadFolders()
          if (creatingItem.parentId) {
            setExpandedFolders(prev => new Set([...prev, creatingItem.parentId]))
          }
        }
      } else if (creatingItem.type === 'document') {
        const response = await fetch('/api/context/documents', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: name.trim(),
            content: `# ${name.trim()}\n\nStart writing your content here...`,
            folder_id: creatingItem.parentId
          })
        })
        
        if (response.ok) {
          const newDoc = await response.json()
          await loadFolders()
          if (creatingItem.parentId) {
            setExpandedFolders(prev => new Set([...prev, creatingItem.parentId]))
          }
          setSelectedDocument(newDoc)
        }
      }
    } catch (error) {
      console.error('Error creating item:', error)
    }
    
    setCreatingItem(null)
  }

  const handleCreateItemCancel = () => {
    setCreatingItem(null)
  }

  const renderFolderTree = (folders) => {
    if (!folders?.tree) return null

    const treeItems = []
    
    // Add root-level creation items
    if (creatingItem && !creatingItem.parentId) {
      if (creatingItem.type === 'folder') {
        treeItems.push(
          <div key={creatingItem.id} className="mb-1">
            <div className="flex items-center p-2 bg-blue-50 rounded">
              <div className="w-4 h-4 mr-1"></div>
              <i className="fas fa-folder text-blue-500 mr-2"></i>
              <input
                type="text"
                placeholder="Folder name"
                className="flex-1 bg-white border-2 border-blue-500 rounded px-2 py-1 text-sm font-medium"
                autoFocus
                onBlur={handleCreateItemCancel}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleCreateItemSubmit(e.target.value)
                  } else if (e.key === 'Escape') {
                    e.preventDefault()
                    handleCreateItemCancel()
                  }
                }}
                onClick={(e) => e.stopPropagation()}
              />
            </div>
          </div>
        )
      } else if (creatingItem.type === 'document') {
        treeItems.push(
          <div key={creatingItem.id} className="mb-1">
            <div className="flex items-center p-2 bg-blue-50 rounded">
              <i className="fas fa-file-alt text-blue-500 mr-2"></i>
              <input
                type="text"
                placeholder="Document name"
                className="flex-1 bg-white border-2 border-blue-500 rounded px-2 py-1 text-sm"
                autoFocus
                onBlur={handleCreateItemCancel}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleCreateItemSubmit(e.target.value)
                  } else if (e.key === 'Escape') {
                    e.preventDefault()
                    handleCreateItemCancel()
                  }
                }}
                onClick={(e) => e.stopPropagation()}
              />
            </div>
          </div>
        )
      }
    }
    
    // Add folder trees
    treeItems.push(...folders.tree.map((folder) => {
      const isExpanded = expandedFolders.has(folder.id)
      const hasSubfolders = folder.subfolders && folder.subfolders.length > 0

      return (
        <div key={folder.id} className="mb-1">
          {/* Folder Row */}
          <div 
            className={`flex items-center p-2 hover:bg-gray-100 rounded cursor-pointer tree-item ${
              selectedFolder?.id === folder.id ? 'bg-blue-50 border-l-4 border-blue-500' : ''
            }`}
            onContextMenu={(e) => handleContextMenu(e, folder, 'folder')}
            onClick={(e) => {
              e.stopPropagation()
              selectFolder(folder)
            }}
          >
            {/* Expand/Collapse Icon */}
            <div 
              className="w-4 h-4 flex items-center justify-center mr-1 hover:bg-gray-200 rounded cursor-pointer"
              onClick={(e) => {
                e.stopPropagation()
                if (hasSubfolders || folder.documents?.length > 0) {
                  toggleFolder(folder.id)
                }
              }}
            >
              {(hasSubfolders || folder.documents?.length > 0) && (
                <i className={`fas fa-chevron-${isExpanded ? 'down' : 'right'} text-xs text-gray-400`}></i>
              )}
            </div>
            
            {/* Folder Icon */}
            <i className={`fas fa-folder${isExpanded ? '-open' : ''} text-blue-500 mr-2`}></i>
            
            {/* Folder Name */}
            {editingItem?.id === folder.id ? (
              <input
                type="text"
                defaultValue={folder.name}
                className="flex-1 bg-white border rounded px-1 py-0.5 text-sm"
                autoFocus
                onBlur={(e) => {
                  // Handle rename
                  setEditingItem(null)
                }}
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    // Handle rename
                    setEditingItem(null)
                  }
                }}
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <span className="font-medium flex-1">{folder.name}</span>
            )}
            
            {/* Document Count */}
            <span className="text-xs text-gray-500 mr-2">
              {folder.document_count || 0} docs
            </span>
            
            {/* Quick Action Icons */}
            <div className="action-buttons flex items-center gap-1 mr-2">
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  handleCreateDocumentInFolder(folder)
                }}
                className="p-1 text-gray-400 hover:text-blue-500 hover:bg-blue-50 rounded transition-all"
                title="Add Document"
              >
                <i className="fas fa-file-plus text-xs"></i>
                <span className="sr-only">Add Document</span>
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  handleCreateSubFolder(folder)
                }}
                className="p-1 text-gray-400 hover:text-blue-500 hover:bg-blue-50 rounded transition-all"
                title="Add Folder"
              >
                <i className="fas fa-folder-plus text-xs"></i>
                <span className="sr-only">Add Folder</span>
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  handleDelete(folder)
                }}
                className="p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-all"
                title="Delete"
              >
                <i className="fas fa-trash text-xs"></i>
                <span className="sr-only">Delete</span>
              </button>
            </div>
          </div>
          
          {/* Documents in this folder */}
          {isExpanded && folder.documents?.map((doc) => (
            <div
              key={doc.id}
              className="ml-8 flex items-center p-2 hover:bg-gray-50 rounded cursor-pointer tree-item"
              onClick={() => loadDocument(doc)}
              onContextMenu={(e) => handleContextMenu(e, doc, 'document')}
            >
              <i className="fas fa-file-alt text-gray-400 mr-2"></i>
              
              {editingItem?.id === doc.id ? (
                <input
                  type="text"
                  defaultValue={doc.name}
                  className="flex-1 bg-white border rounded px-1 py-0.5 text-sm"
                  autoFocus
                  onBlur={() => setEditingItem(null)}
                  onKeyPress={(e) => {
                    if (e.key === 'Enter') {
                      setEditingItem(null)
                    }
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span className="text-sm flex-1">{doc.name}</span>
              )}
              
              {/* Action buttons for documents */}
              <div className="action-buttons flex items-center gap-1 mr-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    handleRename(doc)
                  }}
                  className="p-1 text-gray-400 hover:text-blue-500 hover:bg-blue-50 rounded transition-all"
                  title="Rename"
                >
                  <i className="fas fa-edit text-xs"></i>
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    handleDelete(doc)
                  }}
                  className="p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-all"
                  title="Delete"
                >
                  <i className="fas fa-trash text-xs"></i>
                </button>
              </div>
              
            </div>
          ))}
          
          {/* Inline creation for documents in this folder */}
          {isExpanded && creatingItem && creatingItem.parentId === folder.id && creatingItem.type === 'document' && (
            <div className="ml-8 flex items-center p-2 bg-blue-50 rounded">
              <i className="fas fa-file-alt text-blue-500 mr-2"></i>
              <input
                type="text"
                placeholder="Document name"
                className="flex-1 bg-white border-2 border-blue-500 rounded px-2 py-1 text-sm"
                autoFocus
                onBlur={handleCreateItemCancel}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleCreateItemSubmit(e.target.value)
                  } else if (e.key === 'Escape') {
                    e.preventDefault()
                    handleCreateItemCancel()
                  }
                }}
                onClick={(e) => e.stopPropagation()}
              />
            </div>
          )}
          
          {/* Inline creation for subfolders */}
          {isExpanded && creatingItem && creatingItem.parentId === folder.id && creatingItem.type === 'folder' && (
            <div className="ml-4 mb-1">
              <div className="flex items-center p-2 bg-blue-50 rounded">
                <div className="w-4 h-4 mr-1"></div>
                <i className="fas fa-folder text-blue-500 mr-2"></i>
                <input
                  type="text"
                  placeholder="Folder name"
                  className="flex-1 bg-white border-2 border-blue-500 rounded px-2 py-1 text-sm font-medium"
                  autoFocus
                  onBlur={handleCreateItemCancel}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      handleCreateItemSubmit(e.target.value)
                    } else if (e.key === 'Escape') {
                      handleCreateItemCancel()
                    }
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
            </div>
          )}
          
          {/* Subfolders */}
          {isExpanded && hasSubfolders && (
            <div className="ml-4">
              {renderFolderTree({ tree: folder.subfolders })}
            </div>
          )}
        </div>
      )
    }))
    
    return treeItems
  }

  return (
    <div className={`${isFullscreen ? 'fixed inset-0 z-50 bg-white flex flex-col' : 'p-6 max-w-7xl mx-auto h-[calc(100vh-48px)] flex flex-col'}`}>
      {/* Header */}
      <div className={`${isFullscreen ? 'hidden' : 'mb-6'}`}>
        <h1 className="text-3xl font-bold text-gray-900 mb-4">My Context Hub</h1>
        
        {/* Control Bar */}
        <div className="bg-white rounded-lg shadow p-4">
          <div className="flex items-center gap-4 flex-wrap">
            {/* Status */}
            <div className="flex items-center gap-2">
              <div className={`px-3 py-1 text-sm rounded-full ${
                contextStatus?.initialized 
                  ? 'bg-green-100 text-green-800' 
                  : 'bg-yellow-100 text-yellow-800'
              }`}>
                <i className={`fas ${
                  contextStatus?.initialized ? 'fa-check-circle' : 'fa-exclamation-circle'
                } mr-1`}></i>
                {contextStatus?.initialized ? 'Ready' : 'Not Ready'}
              </div>
              
              {!contextStatus?.initialized && (
                <button
                  onClick={initializeContext}
                  className="btn-primary text-sm"
                >
                  <i className="fas fa-plus mr-1"></i>
                  Initialize
                </button>
              )}
            </div>

            {/* Search */}
            <div className="flex items-center gap-2 flex-1 max-w-md">
              <input
                type="text"
                placeholder="Search..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button onClick={handleSearch} className="btn-primary text-sm">
                <i className="fas fa-search"></i>
              </button>
            </div>

            {/* Actions */}
            <button 
              onClick={() => handleCreateFolder()}
              className="btn-primary text-sm"
            >
              <i className="fas fa-folder-plus mr-1"></i>
              New Folder
            </button>
            <button 
              onClick={() => handleCreateDocument()}
              className="btn-primary text-sm"
            >
              <i className="fas fa-file-plus mr-1"></i>
              New Document
            </button>
            
            {/* Undo/Redo */}
            <div className="flex items-center gap-1 border-l pl-4 ml-2">
              <button 
                onClick={performUndo}
                disabled={actionHistory.length === 0}
                className="btn-secondary text-sm disabled:opacity-50"
                title="Undo"
              >
                <i className="fas fa-undo"></i>
              </button>
              <button 
                onClick={performRedo}
                disabled={redoStack.length === 0}
                className="btn-secondary text-sm disabled:opacity-50"
                title="Redo"
              >
                <i className="fas fa-redo"></i>
              </button>
            </div>
            
            <button className="btn-secondary text-sm">
              <i className="fas fa-upload mr-1"></i>
              Upload
            </button>
            <button className="btn-secondary text-sm">
              <i className="fas fa-download mr-1"></i>
              Export
            </button>
            <button 
              onClick={loadContextStatus}
              className="btn-secondary text-sm"
            >
              <i className="fas fa-sync-alt"></i>
            </button>
          </div>

          {/* Search Results */}
          {searchResults && (
            <div className="mt-4 border-t pt-4">
              <h4 className="font-medium text-gray-900 mb-2 text-sm">Search Results</h4>
              <div className="space-y-2">
                {searchResults.results?.length > 0 ? (
                  searchResults.results.map((result) => (
                    <div
                      key={result.id}
                      className="border border-gray-200 rounded-lg p-3 cursor-pointer hover:bg-gray-50"
                      onClick={() => loadDocument(result)}
                    >
                      <div className="font-medium text-gray-900">{result.name}</div>
                      <div className="text-sm text-gray-600 mt-1">
                        {result.content ? result.content.substring(0, 200) + '...' : 'No content preview'}
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-gray-500 text-sm">No results found</p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className={`grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 min-h-0`}>
        {/* File Browser */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-lg shadow h-full flex flex-col">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-medium text-gray-900">Files & Folders</h3>
            </div>
            <div className="p-4 flex-1 overflow-y-auto">
              {contextStatus?.initialized ? (
                folders ? (
                  <div>
                    {renderFolderTree(folders)}
                    {(!folders.tree || folders.tree.length === 0) && !creatingItem && (
                      <div className="text-center py-8 text-gray-500">
                        <i className="fas fa-folder-open text-4xl mb-4"></i>
                        <p className="mb-2">No folders yet</p>
                        <p className="text-sm mb-4">Create your first folder or document to get started.</p>
                        <div className="flex gap-2 justify-center">
                          <button 
                            onClick={() => handleCreateFolder()}
                            className="btn-primary text-sm"
                          >
                            <i className="fas fa-folder-plus mr-1"></i>
                            New Folder
                          </button>
                          <button 
                            onClick={() => handleCreateDocument()}
                            className="btn-primary text-sm"
                          >
                            <i className="fas fa-file-plus mr-1"></i>
                            New Document
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500">
                    <i className="fas fa-spinner fa-spin text-2xl mb-2"></i>
                    <p>Loading folders...</p>
                  </div>
                )
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <i className="fas fa-folder-open text-4xl mb-4"></i>
                  <p>Your context hub is not initialized yet.</p>
                  <p className="text-sm">Click "Initialize" to get started.</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Document Editor */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-lg shadow h-full flex flex-col">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <i className="fas fa-file-alt text-gray-500"></i>
                <h3 className="text-lg font-medium text-gray-900">
                  {selectedDocument ? selectedDocument.name : 'Select a Document'}
                </h3>
              </div>
              <div className="flex items-center gap-2">
                {selectedDocument && (
                  <>
                    <button 
                      onClick={() => handleSaveDocument(false)}
                      className="btn-primary text-sm"
                      disabled={isLoadingDocument || saveStatus === 'saving'}
                    >
                      <i className="fas fa-save mr-2"></i>
                      Save
                    </button>
                    {saveStatus && (
                      <span className={`text-sm ${
                        saveStatus === 'saving' ? 'text-blue-600' : 
                        saveStatus === 'saved' ? 'text-green-600' : 
                        'text-red-600'
                      }`}>
                        {saveStatus === 'saving' && <i className="fas fa-spinner fa-spin mr-1"></i>}
                        {saveStatus === 'saved' && <i className="fas fa-check mr-1"></i>}
                        {saveStatus === 'error' && <i className="fas fa-exclamation-triangle mr-1"></i>}
                        {saveStatus === 'saving' ? 'Saving...' : 
                         saveStatus === 'saved' ? 'Saved' : 
                         'Save failed'}
                      </span>
                    )}
                  </>
                )}
                <button 
                  onClick={() => setIsFullscreen(!isFullscreen)}
                  className="btn-secondary text-sm"
                  title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
                >
                  <i className={`fas fa-${isFullscreen ? 'compress' : 'expand'}`}></i>
                </button>
              </div>
            </div>
            
            <div className="flex-1 overflow-hidden">
              {isLoadingDocument ? (
                <div className="flex items-center justify-center h-full text-gray-500">
                  <div className="text-center">
                    <i className="fas fa-spinner fa-spin text-4xl mb-4"></i>
                    <p className="text-lg">Loading document...</p>
                  </div>
                </div>
              ) : selectedDocument ? (
                <div 
                  ref={editorRef} 
                  className="h-full"
                />
              ) : (
                <div className="flex items-center justify-center h-full text-gray-500">
                  <div className="text-center">
                    <i className="fas fa-file-alt text-6xl mb-4"></i>
                    <p className="text-lg">Select a document to view or edit</p>
                    <p className="text-sm mt-2">Click on any file in the tree to open it</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Undo Notification */}
      {undoNotification && (
        <div className="fixed bottom-4 left-1/2 transform -translate-x-1/2 z-50">
          <div className="bg-gray-900 text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3">
            <span>{undoNotification.message}</span>
            <button
              onClick={() => {
                undoNotification.undoAction()
                setUndoNotification(null)
              }}
              className="px-3 py-1 bg-white text-gray-900 rounded hover:bg-gray-100 transition-colors font-medium"
            >
              Undo
            </button>
          </div>
        </div>
      )}

      {/* Context Menu */}
      {contextMenu && (
        <>
          <div 
            className="fixed inset-0 z-40"
            onClick={closeContextMenu}
          />
          <div 
            className="fixed z-50 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-48"
            style={{
              left: contextMenu.x,
              top: contextMenu.y
            }}
          >
            {contextMenu.type === 'folder' ? (
              <>
                <button
                  onClick={() => handleCreateDocumentInFolder(contextMenu.item)}
                  className="w-full text-left px-4 py-2 text-sm hover:bg-gray-100 flex items-center gap-3"
                >
                  <i className="fas fa-file-plus text-blue-500"></i>
                  New Document
                </button>
                <button
                  onClick={() => handleCreateSubFolder(contextMenu.item)}
                  className="w-full text-left px-4 py-2 text-sm hover:bg-gray-100 flex items-center gap-3"
                >
                  <i className="fas fa-folder-plus text-blue-500"></i>
                  New Folder
                </button>
                <hr className="my-1" />
                <button
                  onClick={() => handleRename(contextMenu.item)}
                  className="w-full text-left px-4 py-2 text-sm hover:bg-gray-100 flex items-center gap-3"
                >
                  <i className="fas fa-edit text-gray-500"></i>
                  Rename
                </button>
                <button
                  onClick={() => handleDelete(contextMenu.item)}
                  className="w-full text-left px-4 py-2 text-sm hover:bg-gray-100 flex items-center gap-3 text-red-600"
                >
                  <i className="fas fa-trash text-red-500"></i>
                  Delete
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => handleRename(contextMenu.item)}
                  className="w-full text-left px-4 py-2 text-sm hover:bg-gray-100 flex items-center gap-3"
                >
                  <i className="fas fa-edit text-gray-500"></i>
                  Rename
                </button>
                <button
                  onClick={() => navigator.clipboard.writeText(contextMenu.item.content || '')}
                  className="w-full text-left px-4 py-2 text-sm hover:bg-gray-100 flex items-center gap-3"
                >
                  <i className="fas fa-copy text-gray-500"></i>
                  Copy Content
                </button>
                <hr className="my-1" />
                <button
                  onClick={() => handleDelete(contextMenu.item)}
                  className="w-full text-left px-4 py-2 text-sm hover:bg-gray-100 flex items-center gap-3 text-red-600"
                >
                  <i className="fas fa-trash text-red-500"></i>
                  Delete
                </button>
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default Context