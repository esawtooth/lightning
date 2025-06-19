/**
 * Lightning Core Adapter for Voice Agent
 * 
 * This adapter allows the voice agent to use Lightning Core's
 * Realtime API proxy instead of connecting directly to OpenAI.
 */

const WebSocket = require('ws');
const EventEmitter = require('events');

class LightningRealtimeAdapter extends EventEmitter {
    constructor(config = {}) {
        super();
        
        // Configuration
        this.lightningUrl = config.lightningUrl || process.env.LIGHTNING_REALTIME_URL || 'ws://localhost:8001/realtime';
        this.userId = config.userId || 'voice_agent';
        this.model = config.model || 'gpt-4o-realtime-preview-2024-12-17';
        this.voice = config.voice || 'ash';
        this.instructions = config.instructions || 'You are a helpful voice assistant.';
        
        // State
        this.ws = null;
        this.sessionId = null;
        this.connected = false;
    }
    
    /**
     * Connect to Lightning Core Realtime API
     */
    async connect(sessionConfig = {}) {
        if (this.connected) {
            throw new Error('Already connected');
        }
        
        return new Promise((resolve, reject) => {
            this.ws = new WebSocket(this.lightningUrl);
            
            this.ws.on('open', () => {
                console.log('Connected to Lightning Realtime API');
                
                // Send configuration
                const config = {
                    user_id: this.userId,
                    model: this.model,
                    voice: sessionConfig.voice || this.voice,
                    instructions: sessionConfig.instructions || this.instructions,
                    input_audio_format: sessionConfig.input_audio_format || 'g711_ulaw',
                    output_audio_format: sessionConfig.output_audio_format || 'g711_ulaw',
                    turn_detection: sessionConfig.turn_detection || { type: 'server_vad' },
                    tools: sessionConfig.tools || [],
                    ...sessionConfig
                };
                
                this.ws.send(JSON.stringify(config));
            });
            
            this.ws.on('message', (data) => {
                try {
                    const message = JSON.parse(data);
                    
                    if (message.type === 'session.created') {
                        this.sessionId = message.session_id;
                        this.connected = true;
                        this.emit('connected', { sessionId: this.sessionId });
                        resolve({ sessionId: this.sessionId });
                    } else if (message.type === 'error') {
                        this.emit('error', new Error(message.error));
                        reject(new Error(message.error));
                    } else {
                        // Forward all other messages
                        this.emit('message', message);
                        
                        // Emit specific events
                        if (message.type === 'response.audio.delta') {
                            this.emit('audio', message);
                        } else if (message.type === 'response.audio_transcript.done') {
                            this.emit('transcript', {
                                role: 'assistant',
                                content: message.transcript
                            });
                        } else if (message.type === 'conversation.item.input_audio_transcription.completed') {
                            this.emit('transcript', {
                                role: 'user',
                                content: message.transcript
                            });
                        } else if (message.type === 'response.function_call_arguments.done') {
                            this.emit('function_call', {
                                call_id: message.call_id,
                                name: message.name,
                                arguments: message.arguments
                            });
                        }
                    }
                } catch (err) {
                    console.error('Error parsing message:', err);
                }
            });
            
            this.ws.on('error', (error) => {
                console.error('WebSocket error:', error);
                this.emit('error', error);
                if (!this.connected) {
                    reject(error);
                }
            });
            
            this.ws.on('close', () => {
                console.log('Disconnected from Lightning Realtime API');
                this.connected = false;
                this.sessionId = null;
                this.emit('disconnected');
            });
        });
    }
    
    /**
     * Send a message to the Realtime API
     */
    send(message) {
        if (!this.connected || !this.ws) {
            throw new Error('Not connected');
        }
        
        if (typeof message === 'object') {
            this.ws.send(JSON.stringify(message));
        } else {
            this.ws.send(message);
        }
    }
    
    /**
     * Send audio data
     */
    sendAudio(audioData) {
        this.send({
            type: 'input_audio_buffer.append',
            audio: audioData
        });
    }
    
    /**
     * Create a response
     */
    createResponse(config = {}) {
        this.send({
            type: 'response.create',
            response: config
        });
    }
    
    /**
     * Send a text message
     */
    sendText(text, role = 'user') {
        this.send({
            type: 'conversation.item.create',
            item: {
                type: 'message',
                role: role,
                content: [{
                    type: 'input_text',
                    text: text
                }]
            }
        });
        
        // Automatically create response
        this.createResponse();
    }
    
    /**
     * Update session configuration
     */
    updateSession(config) {
        this.send({
            type: 'session.update',
            session: config
        });
    }
    
    /**
     * Clear conversation
     */
    clearConversation() {
        this.send({
            type: 'conversation.item.truncate',
            item_id: 'root',
            audio_end_ms: 0
        });
    }
    
    /**
     * Disconnect from the API
     */
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.connected = false;
        this.sessionId = null;
    }
}

/**
 * Create adapter compatible with existing OpenAI Realtime client usage
 */
function createOpenAICompatibleAdapter(config = {}) {
    const adapter = new LightningRealtimeAdapter(config);
    
    // Add OpenAI-compatible methods
    adapter.realtime = {
        connect: async (options) => {
            await adapter.connect(options);
            return adapter;
        },
        
        send: (eventName, data) => {
            if (eventName === 'input_audio_buffer.append') {
                adapter.sendAudio(data.audio);
            } else if (eventName === 'conversation.item.create') {
                adapter.send({ type: eventName, ...data });
            } else if (eventName === 'response.create') {
                adapter.createResponse(data);
            } else {
                adapter.send({ type: eventName, ...data });
            }
        },
        
        on: (event, handler) => {
            adapter.on(event, handler);
        },
        
        off: (event, handler) => {
            adapter.off(event, handler);
        },
        
        disconnect: () => {
            adapter.disconnect();
        },
        
        isConnected: () => adapter.connected,
        
        sessionId: () => adapter.sessionId
    };
    
    return adapter;
}

module.exports = {
    LightningRealtimeAdapter,
    createOpenAICompatibleAdapter
};