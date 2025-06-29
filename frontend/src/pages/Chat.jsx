import React, { useState, useEffect, useRef, useCallback } from 'react'
import { AssistantRuntimeProvider, ThreadPrimitive, ComposerPrimitive } from '@assistant-ui/react'
import { useLocalRuntime } from '@assistant-ui/react'

const Chat = () => {
  const [userId] = useState(() => `user-${Math.random().toString(36).substr(2, 9)}`)
  const [threadId, setThreadId] = useState('new')
  const [connectionStatus, setConnectionStatus] = useState('disconnected')
  const wsRef = useRef(null)
  const pendingRequestsRef = useRef(new Map())

  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return wsRef.current
    }

    const ws = new WebSocket(`ws://${window.location.hostname}:8000/ws/chat/${userId}`)
    
    ws.onopen = () => {
      console.log('WebSocket connected')
      setConnectionStatus('connected')
      
      // Initialize chat thread
      ws.send(JSON.stringify({
        type: 'init_chat',
        thread_id: threadId
      }))
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
      setConnectionStatus('disconnected')
      wsRef.current = null
      
      // Attempt to reconnect after 3 seconds
      setTimeout(() => {
        if (wsRef.current?.readyState !== WebSocket.OPEN) {
          connectWebSocket()
        }
      }, 3000)
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      setConnectionStatus('error')
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        console.log('Received WebSocket message:', data)
        
        if (data.type === 'chat_response' && data.request_id) {
          const pendingRequest = pendingRequestsRef.current.get(data.request_id)
          if (pendingRequest) {
            pendingRequest.onChunk(data.content || '')
            if (data.finished) {
              pendingRequest.onComplete()
              pendingRequestsRef.current.delete(data.request_id)
            }
          }
        } else if (data.type === 'thread_initialized') {
          setThreadId(data.thread_id)
        } else if (data.type === 'error') {
          const pendingRequest = Array.from(pendingRequestsRef.current.values())[0]
          if (pendingRequest) {
            pendingRequest.onError(new Error(data.message || 'Unknown error'))
          }
        }
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error)
      }
    }

    wsRef.current = ws
    return ws
  }, [userId, threadId])

  useEffect(() => {
    connectWebSocket()
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [connectWebSocket])

  const runtime = useLocalRuntime({
    async *chatApi({ messages, abortSignal }) {
      try {
        const ws = wsRef.current
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          throw new Error('WebSocket not connected')
        }

        const requestId = `req-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
        
        // Convert messages to Lightning format
        const lightningMessages = messages.map(msg => ({
          role: msg.role,
          content: typeof msg.content === 'string' ? msg.content : msg.content[0]?.text || ''
        }))

        // Send message via WebSocket
        ws.send(JSON.stringify({
          type: 'chat_message',
          message: lightningMessages[lightningMessages.length - 1]?.content || '',
          messages: lightningMessages,
          request_id: requestId
        }))

        // Set up response handling with Promise-based approach
        let isComplete = false
        const chunks = []
        let resolveNextChunk
        let rejectRequest

        const responsePromise = new Promise((resolve, reject) => {
          rejectRequest = reject
          
          pendingRequestsRef.current.set(requestId, {
            onChunk: (chunk) => {
              chunks.push(chunk)
              if (resolveNextChunk) {
                resolveNextChunk(chunk)
                resolveNextChunk = null
              }
            },
            onComplete: () => {
              isComplete = true
              if (resolveNextChunk) {
                resolveNextChunk(null) // Signal completion
                resolveNextChunk = null
              }
              resolve()
            },
            onError: (error) => {
              isComplete = true
              reject(error)
            }
          })
        })

        // Handle abort signal
        if (abortSignal) {
          abortSignal.addEventListener('abort', () => {
            isComplete = true
            pendingRequestsRef.current.delete(requestId)
            if (rejectRequest) {
              rejectRequest(new Error('Request aborted'))
            }
          })
        }

        // Yield chunks as they arrive
        let chunkIndex = 0
        while (!isComplete && !abortSignal?.aborted) {
          if (chunkIndex < chunks.length) {
            // Yield available chunks
            const chunk = chunks[chunkIndex++]
            yield {
              type: 'text-delta',
              textDelta: chunk,
            }
          } else {
            // Wait for next chunk
            try {
              const nextChunk = await new Promise((resolve) => {
                resolveNextChunk = resolve
                // Timeout to check for completion
                setTimeout(() => {
                  if (resolveNextChunk) {
                    resolveNextChunk(null)
                    resolveNextChunk = null
                  }
                }, 100)
              })
              
              if (nextChunk) {
                yield {
                  type: 'text-delta',
                  textDelta: nextChunk,
                }
                chunkIndex++
              }
            } catch (error) {
              console.error('Error waiting for chunk:', error)
              break
            }
          }
        }

        // Clean up
        pendingRequestsRef.current.delete(requestId)
        
      } catch (error) {
        console.error('Chat WebSocket error:', error)
        yield {
          type: 'text-delta',
          textDelta: `Error: ${error.message}`,
        }
      }
    },
  })

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="p-6 h-full">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Chat</h1>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${
              connectionStatus === 'connected' ? 'bg-green-500' : 
              connectionStatus === 'error' ? 'bg-red-500' : 
              'bg-yellow-500'
            }`}></div>
            <span className="text-sm text-gray-600 capitalize">{connectionStatus}</span>
          </div>
        </div>
        <div className="bg-white rounded-lg shadow h-[calc(100vh-200px)] flex flex-col overflow-hidden">
          <ThreadPrimitive.Root className="h-full flex flex-col">
            <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto px-6 py-4">
              <ThreadPrimitive.Empty>
                <div className="flex items-center justify-center h-64 text-gray-500">
                  <div className="text-center">
                    <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                    <p className="mt-2 text-sm text-gray-600">
                      {connectionStatus === 'connected' 
                        ? 'Start a conversation with Vex' 
                        : connectionStatus === 'disconnected'
                        ? 'Connecting to chat service...'
                        : 'Connection error - retrying...'}
                    </p>
                    {connectionStatus === 'connected' && (
                      <p className="mt-1 text-xs text-gray-400">
                        Connected to Lightning • Thread ID: {threadId}
                      </p>
                    )}
                  </div>
                </div>
              </ThreadPrimitive.Empty>
              
              <ThreadPrimitive.Messages 
                components={{
                  UserMessage: ({ message }) => (
                    <div className="flex justify-end mb-4">
                      <div className="bg-blue-600 text-white rounded-lg px-4 py-2 max-w-xs lg:max-w-md">
                        {typeof message.content === 'string' ? message.content : message.content[0]?.text || ''}
                      </div>
                    </div>
                  ),
                  AssistantMessage: ({ message }) => (
                    <div className="flex justify-start mb-4">
                      <div className="bg-gray-100 text-gray-900 rounded-lg px-4 py-2 max-w-xs lg:max-w-md">
                        {typeof message.content === 'string' ? message.content : message.content[0]?.text || ''}
                      </div>
                    </div>
                  ),
                }}
              />
            </ThreadPrimitive.Viewport>
            
            <div className="border-t bg-white px-6 py-4">
              <ComposerPrimitive.Root>
                <div className="flex gap-2">
                  <ComposerPrimitive.Input
                    placeholder="Type your message..."
                    className="flex-1 resize-none border border-gray-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent min-h-[44px] max-h-32"
                    rows={1}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        const form = e.target.closest('form')
                        if (form) {
                          const submitEvent = new Event('submit', { bubbles: true, cancelable: true })
                          form.dispatchEvent(submitEvent)
                        }
                      }
                    }}
                  />
                  <ComposerPrimitive.Send className="bg-blue-600 text-white rounded-lg px-4 py-2 hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                    Send
                  </ComposerPrimitive.Send>
                </div>
              </ComposerPrimitive.Root>
            </div>
          </ThreadPrimitive.Root>
        </div>
      </div>
    </AssistantRuntimeProvider>
  )
}

export default Chat