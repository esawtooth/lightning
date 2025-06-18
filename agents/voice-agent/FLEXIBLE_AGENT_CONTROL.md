# Flexible Agent Control System

This document describes the flexible agent control system for the Voice Agent (Vex) that leverages the full power of the OpenAI Realtime API WebSocket interface.

## Overview

The flexible agent control system provides hooks and controls to:
- Control agent behavior dynamically per response
- Implement content moderation and validation
- Route conversations based on content
- Generate out-of-band responses for classification
- Maintain full voice-to-voice capabilities
- Control VAD (Voice Activity Detection) behavior
- Override session configuration dynamically

## Architecture

### Core Components

1. **AgentController** (`agentController.ts`)
   - Central control system for agent behavior
   - Manages hooks and control flow
   - Handles out-of-band responses

2. **Enhanced Session Manager** (`sessionManager.enhanced.ts`)
   - Integrates hooks into the WebSocket flow
   - Manages conversation state
   - Handles validation and moderation

3. **Agent Control Panel** (`agent-control-panel.tsx`)
   - React UI for real-time agent control
   - Dynamic hook configuration
   - Out-of-band response testing

## Hook System

### Available Hooks

#### 1. beforeResponse
Called before each response is generated. Can modify instructions, voice, modalities, and more.

```typescript
beforeResponse: async (context: ResponseContext) => {
  return {
    proceed: true, // Whether to generate response
    instructions: "Custom instructions for this response",
    voice: "sage", // Override voice
    modalities: ["audio"], // Override modalities
    delay: 1000, // Add delay before response
    tools: [...], // Override available tools
    outOfBand: { // Generate out-of-band response instead
      instructions: "Classify this query",
      metadata: { type: "classification" }
    }
  };
}
```

#### 2. onSpeechEnd
Called when speech is detected. Controls response generation and validation.

```typescript
onSpeechEnd: async (context: SpeechContext) => {
  return {
    createResponse: true, // Auto-generate response
    addToConversation: true, // Add to conversation history
    processedTranscript: "Modified transcript", // Process input
    validateFirst: { // Validate before responding
      instructions: "Check if this is appropriate",
      onValidation: async (result) => result === "appropriate"
    }
  };
}
```

#### 3. beforeFunctionCall
Controls function execution with ability to modify or block calls.

```typescript
beforeFunctionCall: async (context: FunctionContext) => {
  return {
    execute: true, // Whether to execute
    overrideArgs: { modified: "args" }, // Override arguments
    overrideResult: { custom: "result" }, // Override result
    context: { audit: true } // Additional context
  };
}
```

#### 4. modifySession
Dynamically modify session configuration based on context.

```typescript
modifySession: async (context: SessionContext) => {
  return {
    apply: true,
    updates: {
      voice: "coral",
      turn_detection: { 
        type: "server_vad",
        silence_duration_ms: 800 
      }
    }
  };
}
```

#### 5. routeResponse
Route conversations to different handlers based on content.

```typescript
routeResponse: async (context: RoutingContext) => {
  return {
    route: "custom", // or "default", "classification", "moderation"
    handler: async (ctx) => { /* custom logic */ },
    metadata: { department: "support" }
  };
}
```

## Usage Examples

### 1. Basic Setup with Custom Hooks

```typescript
import { handleCallConnection, setAgentHooks } from "./sessionManager.enhanced";

// Define custom hooks
const customHooks = {
  beforeResponse: async (context) => {
    // Add custom behavior per response
    if (context.userProfile?.isVip) {
      return {
        proceed: true,
        instructions: "This is a VIP customer. Provide premium service.",
        voice: "sage"
      };
    }
    return { proceed: true };
  }
};

// Apply hooks when handling connection
handleCallConnection(ws, apiKey, objective, userProfile, customHooks);
```

### 2. Content Moderation

```typescript
const moderationHooks = {
  onSpeechEnd: async (context) => {
    // Check for sensitive content
    if (context.transcript.includes("payment")) {
      return {
        createResponse: true,
        addToConversation: true,
        validateFirst: {
          instructions: "Is this a legitimate payment request? Reply 'yes' or 'no'.",
          onValidation: async (result) => result.includes("yes")
        }
      };
    }
    return { createResponse: true, addToConversation: true };
  }
};
```

### 3. Dynamic Voice Control

```typescript
const voiceControlHooks = {
  modifySession: async (context) => {
    const hour = new Date().getHours();
    
    // Morning voice
    if (hour < 12) {
      return {
        apply: true,
        updates: { voice: "coral" }
      };
    }
    
    // Evening voice
    if (hour >= 18) {
      return {
        apply: true,
        updates: { voice: "ballad" }
      };
    }
    
    return { apply: false };
  }
};
```

### 4. Out-of-Band Classification

```typescript
const classificationHooks = {
  beforeResponse: async (context) => {
    // First classify the query
    return {
      proceed: true,
      outOfBand: {
        instructions: "Classify this as: support, sales, or general",
        metadata: { type: "classification" },
        input: [{
          type: "message",
          role: "user",
          content: [{ type: "input_text", text: context.userInput }]
        }]
      }
    };
  }
};
```

## Frontend Control

### Using the Agent Control Panel

The Agent Control Panel provides a UI for controlling agent behavior:

```tsx
import AgentControlPanel from "@/components/agent-control-panel";

<AgentControlPanel 
  ws={websocket}
  onHooksUpdate={(hooks) => console.log("Hooks updated:", hooks)}
/>
```

### Sending Control Messages

```javascript
// Disable VAD
ws.send(JSON.stringify({
  type: "agent.control",
  action: "disableVAD"
}));

// Create out-of-band response
ws.send(JSON.stringify({
  type: "agent.control",
  action: "createOutOfBandResponse",
  instructions: "Summarize the conversation",
  metadata: { type: "summary" }
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

## Pre-built Hook Implementations

The system includes several pre-built hook implementations:

1. **Customer Service** - Department routing, VIP handling, sentiment detection
2. **Financial Services** - Compliance, sensitive data protection, transaction validation
3. **Healthcare** - HIPAA compliance, emergency detection, mental health support
4. **Education** - Adaptive learning, grade-level appropriate responses
5. **Sales** - Lead qualification, objection handling, buying signal detection
6. **Multi-lingual** - Language detection and response

### Using Pre-built Hooks

```typescript
import { customerServiceHooks, combineHooks } from "./exampleHookImplementations";

// Use a single hook set
handleCallConnection(ws, apiKey, objective, userProfile, customerServiceHooks);

// Combine multiple hook sets
const combinedHooks = combineHooks(
  customerServiceHooks,
  complianceHooks,
  customHooks
);
```

## Advanced Features

### 1. Manual VAD Control

```typescript
// Disable VAD for push-to-talk interface
sendControlMessage("disableVAD");

// Manually commit audio and create response
ws.send(JSON.stringify({ type: "input_audio_buffer.commit" }));
ws.send(JSON.stringify({ type: "response.create" }));
```

### 2. Response Cancellation

```typescript
beforeResponse: async (context) => {
  if (shouldBlockResponse(context)) {
    return { proceed: false }; // Cancels response
  }
  return { proceed: true };
}
```

### 3. Custom Context Injection

```typescript
beforeResponse: async (context) => {
  return {
    proceed: true,
    customContext: [{
      type: "message",
      role: "system",
      content: [{ 
        type: "text", 
        text: "Additional context for this response" 
      }]
    }]
  };
}
```

## Best Practices

1. **Performance**: Keep hooks lightweight and async
2. **Error Handling**: Always handle errors in hooks gracefully
3. **State Management**: Use session metadata for maintaining state
4. **Security**: Validate and sanitize all inputs in hooks
5. **Testing**: Test hooks thoroughly with various scenarios

## Troubleshooting

### Common Issues

1. **Hooks not firing**: Ensure WebSocket connection is established
2. **Response delays**: Check hook execution time and delays
3. **VAD conflicts**: Ensure VAD settings match your use case
4. **Out-of-band responses**: Listen for response.done events with metadata

### Debug Mode

Enable debug logging in hooks:

```typescript
beforeResponse: async (context) => {
  console.log("Hook context:", context);
  const result = { proceed: true };
  console.log("Hook result:", result);
  return result;
}
```

## Migration from Basic Agent

To migrate from the basic agent to the flexible control system:

1. Replace `sessionManager.ts` with `sessionManager.enhanced.ts`
2. Add `AgentController` to your imports
3. Define your hooks based on requirements
4. Update frontend to use `AgentControlPanel`
5. Test thoroughly with various scenarios

The system maintains full backward compatibility - if no hooks are provided, it behaves exactly like the original implementation.