# Enhanced Voice Agent with Flexible Control

This enhanced version of the voice agent (Vex) provides comprehensive hooks and controls to direct agent behavior with all the power that the WebSocket API affords.

## Quick Start

### 1. Install Dependencies

```bash
cd webapp
npm install @radix-ui/react-switch @radix-ui/react-tabs
```

### 2. Use Enhanced Session Manager

Replace the import in `websocket-server/src/server.ts`:

```typescript
// Instead of:
// import { handleCallConnection } from "./sessionManager";

// Use:
import { handleCallConnection, setAgentHooks } from "./sessionManager.enhanced";
```

### 3. Add Custom Hooks (Optional)

```typescript
import { customerServiceHooks } from "./exampleHookImplementations";

// In your connection handler:
handleCallConnection(ws, apiKey, objective, userProfile, customerServiceHooks);
```

### 4. Launch with New UI

The enhanced UI includes a new Agent Control Panel that provides:
- Real-time VAD control
- Dynamic instruction overrides
- Content moderation toggles
- Out-of-band response testing
- Custom hook code editing

## Key Features

### 🎛️ **Full WebSocket API Control**
- Control every aspect of the OpenAI Realtime API
- Override session configuration dynamically
- Manage voice activity detection (VAD) behavior
- Control response generation flow

### 🛡️ **Content Moderation & Validation**
- Pre-response validation hooks
- Sensitive content detection
- Out-of-band response generation for classification
- Compliance and security controls

### 🎯 **Per-Response Customization**
- Dynamic system instructions per response
- Voice and modality overrides
- Response delays and timing control
- Custom context injection

### 🔄 **Smart Routing & Classification**
- Route conversations based on content
- Department routing (support, sales, etc.)
- Intent classification
- Lead scoring and qualification

### 📊 **Out-of-Band Processing**
- Generate responses outside main conversation flow
- Real-time sentiment analysis
- Topic classification
- Conversation summarization

## Example Use Cases

### 1. Customer Service Agent
```typescript
const hooks = {
  beforeResponse: async (context) => {
    if (context.userProfile?.isVip) {
      return {
        proceed: true,
        instructions: "VIP customer - provide premium service",
        voice: "sage"
      };
    }
    return { proceed: true };
  }
};
```

### 2. Content Moderation
```typescript
const hooks = {
  onSpeechEnd: async (context) => {
    if (context.transcript.includes("payment")) {
      return {
        validateFirst: {
          instructions: "Is this a legitimate payment request?",
          onValidation: async (result) => result.includes("legitimate")
        }
      };
    }
    return { createResponse: true, addToConversation: true };
  }
};
```

### 3. Multi-language Support
```typescript
const hooks = {
  beforeResponse: async (context) => {
    const lang = detectLanguage(context.userInput);
    return {
      proceed: true,
      instructions: `Respond in ${lang}. Be culturally appropriate.`,
      voice: getVoiceForLanguage(lang)
    };
  }
};
```

## Control Methods

### Frontend Controls

```javascript
// Disable VAD for push-to-talk
ws.send(JSON.stringify({
  type: "agent.control",
  action: "disableVAD"
}));

// Generate classification response
ws.send(JSON.stringify({
  type: "agent.control",
  action: "createOutOfBandResponse",
  instructions: "Classify as: support, sales, or general",
  metadata: { type: "classification" }
}));

// Update hooks dynamically
ws.send(JSON.stringify({
  type: "agent.updateHooks",
  hooks: {
    beforeResponse: `async (context) => ({ 
      proceed: true, 
      instructions: "Be extra helpful" 
    })`
  }
}));
```

### Backend Hooks

```typescript
// Set hooks programmatically
setAgentHooks({
  beforeResponse: async (context) => {
    // Your logic here
    return { proceed: true };
  }
});
```

## Pre-built Templates

Choose from ready-made hook implementations:

- **Customer Service**: VIP handling, sentiment detection, department routing
- **Financial Services**: HIPAA compliance, transaction validation, fraud detection
- **Healthcare**: Emergency detection, compliance, sensitive data protection
- **Education**: Adaptive learning, grade-appropriate responses
- **Sales**: Lead qualification, objection handling, buying signals
- **Multi-lingual**: Language detection and appropriate responses

## Migration Guide

1. **Backup Current Implementation**
2. **Install New Dependencies** (React components)
3. **Replace Session Manager** with enhanced version
4. **Update UI** to include Agent Control Panel
5. **Test Thoroughly** with your use cases
6. **Gradually Add Hooks** based on your needs

## Backward Compatibility

✅ **Fully backward compatible** - if no hooks are provided, behaves exactly like the original implementation.

## Advanced Features

- **Hook Chaining**: Combine multiple hook sets
- **Conditional Logic**: Apply different behaviors based on context
- **State Management**: Maintain conversation state across hooks
- **Performance Monitoring**: Track hook execution times
- **Debug Mode**: Comprehensive logging for troubleshooting

## Documentation

- `FLEXIBLE_AGENT_CONTROL.md` - Complete technical documentation
- `exampleHookImplementations.ts` - Ready-to-use examples
- `agentController.ts` - Core control system API

## Support

The enhanced system maintains all original voice agent capabilities while adding powerful control features. You can start with basic controls and gradually add more sophisticated behavior as needed.

For questions or issues, refer to the detailed documentation in `FLEXIBLE_AGENT_CONTROL.md`.