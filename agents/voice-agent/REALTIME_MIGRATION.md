# Voice Agent Migration Guide: Using Lightning Core Realtime API

This guide helps migrate the voice agent from direct OpenAI Realtime API usage to Lightning Core's Realtime proxy.

## Overview

Lightning Core now provides a Realtime API proxy that:
- Tracks usage and costs for voice interactions
- Provides centralized API key management
- Enables monitoring and debugging across all voice sessions
- Maintains full compatibility with OpenAI's Realtime API

## Benefits

1. **Usage Tracking**: Automatic tracking of audio duration and costs
2. **Centralized Management**: Single place to manage API keys and access
3. **Enhanced Security**: No need to expose OpenAI API keys to edge services
4. **Monitoring**: Built-in session tracking and analytics
5. **Multi-tenant Support**: Proper user isolation and billing

## Migration Steps

### 1. Update Environment Variables

```bash
# Old configuration
OPENAI_API_KEY=sk-...

# New configuration
LIGHTNING_REALTIME_URL=ws://localhost:8001/realtime
# Remove OPENAI_API_KEY from voice agent environment
```

### 2. Update WebSocket Connection

#### Before (Direct OpenAI)
```javascript
const ws = new WebSocket(
    'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17',
    {
        headers: {
            'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`,
            'OpenAI-Beta': 'realtime=v1'
        }
    }
);
```

#### After (Lightning Core)
```javascript
const { LightningRealtimeAdapter } = require('./lightning-adapter');

const adapter = new LightningRealtimeAdapter({
    lightningUrl: process.env.LIGHTNING_REALTIME_URL,
    userId: callSid, // Use call ID as user ID for tracking
    voice: 'ash',
    instructions: 'You are a helpful voice assistant.'
});

await adapter.connect({
    tools: [...], // Your function tools
    turn_detection: { type: 'server_vad' }
});
```

### 3. Update Event Handling

The Lightning adapter emits the same events as OpenAI:

```javascript
// Audio events
adapter.on('audio', (event) => {
    // Handle audio delta
    twilioWs.send(/* forward audio to Twilio */);
});

// Transcript events
adapter.on('transcript', (event) => {
    console.log(`${event.role}: ${event.content}`);
});

// Function call events
adapter.on('function_call', async (event) => {
    const result = await handleFunction(event.name, event.arguments);
    adapter.send({
        type: 'conversation.item.create',
        item: {
            type: 'function_call_output',
            call_id: event.call_id,
            output: JSON.stringify(result)
        }
    });
});
```

### 4. Update Session Manager

For the enhanced session manager with hooks:

```javascript
class LightningSessionManager extends SessionManager {
    async createSession(sessionId, config) {
        const adapter = new LightningRealtimeAdapter({
            userId: sessionId,
            ...config
        });
        
        await adapter.connect({
            instructions: await this.buildInstructions(sessionId),
            tools: this.tools,
            voice: config.voice || 'ash'
        });
        
        this.sessions.set(sessionId, {
            adapter,
            config,
            startTime: Date.now()
        });
        
        return adapter;
    }
    
    async processAudio(sessionId, audioData) {
        const session = this.sessions.get(sessionId);
        if (session) {
            session.adapter.sendAudio(audioData);
        }
    }
}
```

### 5. Minimal Changes with Compatibility Mode

For minimal code changes, use the OpenAI-compatible adapter:

```javascript
// Replace OpenAI import
// const { RealtimeClient } = require('@openai/realtime-api-beta');
const { createOpenAICompatibleAdapter } = require('./lightning-adapter');

// Create client with same interface
const client = createOpenAICompatibleAdapter({
    lightningUrl: process.env.LIGHTNING_REALTIME_URL,
    userId: callSid
});

// Rest of the code remains the same!
await client.realtime.connect();
client.realtime.send('input_audio_buffer.append', { audio: audioData });
```

## API Endpoints

### WebSocket Endpoint
- `ws://localhost:8001/realtime` - Main WebSocket endpoint

### HTTP Endpoints
- `GET /health` - Health check with session count
- `GET /sessions` - List active voice sessions
- `GET /demo` - Interactive demo page

## Session Configuration

First message after connection must include configuration:

```json
{
    "user_id": "unique_user_id",
    "model": "gpt-4o-realtime-preview-2024-12-17",
    "voice": "ash",
    "instructions": "System prompt here",
    "input_audio_format": "g711_ulaw",
    "output_audio_format": "g711_ulaw",
    "turn_detection": {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 200
    },
    "tools": [
        {
            "type": "function",
            "name": "transfer_call",
            "description": "Transfer to agent",
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string"}
                }
            }
        }
    ]
}
```

## Usage Tracking

Lightning Core automatically tracks:
- **Audio Duration**: Input and output audio time
- **Token Usage**: Estimated from transcripts
- **Cost Calculation**: Based on current pricing
- **Session Metadata**: User ID, duration, model used

Access usage data via:
```bash
curl http://localhost:8000/usage/stats -H "X-User-Id: user123"
```

## Debugging

1. **Monitor Sessions**: 
   ```bash
   curl http://localhost:8001/sessions
   ```

2. **View Logs**: Lightning Core logs all Realtime events

3. **Test Connection**: Use the demo page at http://localhost:8001/demo

## Production Considerations

1. **Scaling**: Run multiple Lightning Realtime proxy instances
2. **Load Balancing**: Use a WebSocket-aware load balancer
3. **Monitoring**: Set up alerts for session duration and costs
4. **Security**: Use WSS in production with proper certificates
5. **Rate Limiting**: Implement per-user session limits

## Example: Updated Twilio Integration

```javascript
const { LightningRealtimeAdapter } = require('./lightning-adapter');

class TwilioVoiceHandler {
    async handleCall(ws, callSid, from, to) {
        // Create Lightning adapter
        const adapter = new LightningRealtimeAdapter({
            userId: callSid,
            voice: 'ash'
        });
        
        // Connect with call-specific configuration
        await adapter.connect({
            instructions: `You are handling a call from ${from} to ${to}.`,
            tools: this.getToolsForNumber(to),
            turn_detection: { type: 'server_vad' }
        });
        
        // Forward Twilio audio to Lightning
        ws.on('message', (msg) => {
            const data = JSON.parse(msg);
            if (data.event === 'media' && data.media) {
                adapter.sendAudio(data.media.payload);
            }
        });
        
        // Forward Lightning audio to Twilio
        adapter.on('audio', (event) => {
            ws.send(JSON.stringify({
                event: 'media',
                streamSid: this.streamSid,
                media: {
                    payload: event.delta
                }
            }));
        });
        
        // Log transcripts with call context
        adapter.on('transcript', (event) => {
            console.log(`[${callSid}] ${event.role}: ${event.content}`);
        });
        
        // Handle call end
        ws.on('close', () => {
            adapter.disconnect();
        });
    }
}
```

## Migration Checklist

- [ ] Update environment variables (remove OPENAI_API_KEY)
- [ ] Install Lightning adapter (`lightning-adapter.js`)
- [ ] Update WebSocket connection code
- [ ] Test audio streaming in both directions
- [ ] Verify function calling works
- [ ] Check usage tracking is working
- [ ] Test interruption handling
- [ ] Verify session cleanup on disconnect
- [ ] Update monitoring/logging integration

## Support

- Health check: `GET http://localhost:8001/health`
- Active sessions: `GET http://localhost:8001/sessions` 
- Demo interface: http://localhost:8001/demo
- Usage stats: `GET http://localhost:8000/usage/stats`