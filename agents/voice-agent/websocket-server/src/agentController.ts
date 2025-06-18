import { WebSocket } from "ws";

export interface AgentControlHooks {
  // Called before each response is generated
  beforeResponse?: (context: ResponseContext) => Promise<ResponseControl>;
  
  // Called after speech is detected but before creating response
  onSpeechEnd?: (context: SpeechContext) => Promise<SpeechControl>;
  
  // Called when a function call is about to be made
  beforeFunctionCall?: (context: FunctionContext) => Promise<FunctionControl>;
  
  // Called to modify session configuration dynamically
  modifySession?: (context: SessionContext) => Promise<SessionModification>;
  
  // Called for custom routing logic
  routeResponse?: (context: RoutingContext) => Promise<RoutingDecision>;
}

export interface ResponseContext {
  conversation: any[];
  userInput: string;
  sessionConfig: any;
  userProfile?: any;
  metadata?: Record<string, any>;
}

export interface ResponseControl {
  // Whether to proceed with response generation
  proceed: boolean;
  
  // Override instructions for this specific response
  instructions?: string;
  
  // Override modalities for this response
  modalities?: ("text" | "audio")[];
  
  // Generate out-of-band response instead
  outOfBand?: {
    instructions: string;
    metadata?: Record<string, any>;
    input?: any[];
  };
  
  // Custom context to include
  customContext?: any[];
  
  // Delay before generating response (ms)
  delay?: number;
  
  // Override voice for this response
  voice?: string;
  
  // Override tools available for this response
  tools?: any[];
  
  // Force specific tool usage
  toolChoice?: "auto" | "none" | { type: "function"; name: string };
}

export interface SpeechContext {
  transcript: string;
  audioDuration: number;
  sessionConfig: any;
  conversationHistory: any[];
}

export interface SpeechControl {
  // Whether to create a response automatically
  createResponse: boolean;
  
  // Whether to add the speech to conversation
  addToConversation: boolean;
  
  // Pre-process the transcript
  processedTranscript?: string;
  
  // Generate validation response first
  validateFirst?: {
    instructions: string;
    onValidation: (result: string) => Promise<boolean>;
  };
}

export interface FunctionContext {
  functionName: string;
  arguments: any;
  conversationHistory: any[];
}

export interface FunctionControl {
  // Whether to execute the function
  execute: boolean;
  
  // Override the arguments
  overrideArgs?: any;
  
  // Override the result
  overrideResult?: any;
  
  // Additional context for function execution
  context?: any;
}

export interface SessionContext {
  event: any;
  currentSession: any;
}

export interface SessionModification {
  // Dynamic session updates
  updates?: any;
  
  // Whether to apply the modification
  apply: boolean;
}

export interface RoutingContext {
  input: string;
  conversation: any[];
  metadata?: any;
}

export interface RoutingDecision {
  // Route to specific handler
  route: "default" | "classification" | "moderation" | "custom";
  
  // Custom handler function
  handler?: (context: RoutingContext) => Promise<any>;
  
  // Metadata for routing
  metadata?: any;
}

export class AgentController {
  private hooks: AgentControlHooks;
  private modelConn?: WebSocket;
  
  constructor(hooks: AgentControlHooks = {}) {
    this.hooks = hooks;
  }
  
  setModelConnection(ws: WebSocket) {
    this.modelConn = ws;
  }
  
  async handleBeforeResponse(context: ResponseContext): Promise<ResponseControl> {
    if (this.hooks.beforeResponse) {
      return await this.hooks.beforeResponse(context);
    }
    return { proceed: true };
  }
  
  async handleSpeechEnd(context: SpeechContext): Promise<SpeechControl> {
    if (this.hooks.onSpeechEnd) {
      return await this.hooks.onSpeechEnd(context);
    }
    return { createResponse: true, addToConversation: true };
  }
  
  async handleBeforeFunctionCall(context: FunctionContext): Promise<FunctionControl> {
    if (this.hooks.beforeFunctionCall) {
      return await this.hooks.beforeFunctionCall(context);
    }
    return { execute: true };
  }
  
  async handleSessionModification(context: SessionContext): Promise<SessionModification> {
    if (this.hooks.modifySession) {
      return await this.hooks.modifySession(context);
    }
    return { apply: false };
  }
  
  async handleRouting(context: RoutingContext): Promise<RoutingDecision> {
    if (this.hooks.routeResponse) {
      return await this.hooks.routeResponse(context);
    }
    return { route: "default" };
  }
  
  // Helper method to send events to the model
  sendToModel(event: any) {
    if (this.modelConn && this.modelConn.readyState === WebSocket.OPEN) {
      this.modelConn.send(JSON.stringify(event));
    }
  }
  
  // Create an out-of-band response
  async createOutOfBandResponse(
    instructions: string, 
    metadata?: any,
    input?: any[]
  ): Promise<void> {
    const event = {
      type: "response.create",
      response: {
        conversation: "none",
        metadata: metadata || {},
        modalities: ["text"],
        instructions,
        input: input || []
      }
    };
    
    this.sendToModel(event);
  }
  
  // Create a moderated response
  async createModeratedResponse(
    originalInput: string,
    validationPrompt: string,
    onValidation: (result: string) => boolean
  ): Promise<boolean> {
    // First, validate the input
    await this.createOutOfBandResponse(
      validationPrompt,
      { type: "moderation", originalInput },
      [{
        type: "message",
        role: "user",
        content: [{ type: "input_text", text: originalInput }]
      }]
    );
    
    // Wait for validation result (this would need to be implemented with proper event handling)
    // For now, returning true as a placeholder
    return true;
  }
  
  // Update hooks dynamically
  updateHooks(newHooks: Partial<AgentControlHooks>) {
    this.hooks = { ...this.hooks, ...newHooks };
  }
  
  // Get current hooks (for debugging/inspection)
  getHooks(): AgentControlHooks {
    return { ...this.hooks };
  }
}

// Example hook implementations
export const exampleHooks: AgentControlHooks = {
  // Add custom instructions per response based on context
  beforeResponse: async (context) => {
    // Example: Different behavior based on user profile
    if (context.userProfile?.preferences?.formal) {
      return {
        proceed: true,
        instructions: "Respond in a formal, professional manner. Use titles and formal language."
      };
    }
    
    // Example: Route certain queries for classification first
    if (context.userInput.toLowerCase().includes("urgent")) {
      return {
        proceed: true,
        instructions: "This seems urgent. Prioritize helping the user quickly and efficiently.",
        modalities: ["audio"], // Audio only for urgent requests
      };
    }
    
    return { proceed: true };
  },
  
  // Control response generation after speech
  onSpeechEnd: async (context) => {
    // Example: Don't auto-respond to very short inputs
    if (context.transcript.split(' ').length < 3) {
      return {
        createResponse: false,
        addToConversation: true
      };
    }
    
    // Example: Validate sensitive content first
    if (context.transcript.toLowerCase().includes("payment")) {
      return {
        createResponse: true,
        addToConversation: true,
        validateFirst: {
          instructions: "Determine if this is a legitimate payment request. Respond with 'legitimate' or 'suspicious'.",
          onValidation: async (result) => result.includes("legitimate")
        }
      };
    }
    
    return { createResponse: true, addToConversation: true };
  },
  
  // Control function execution
  beforeFunctionCall: async (context) => {
    // Example: Require confirmation for certain functions
    if (context.functionName === "send_email") {
      // Could check user permissions here
      return {
        execute: true,
        context: { requireConfirmation: true }
      };
    }
    
    return { execute: true };
  },
  
  // Dynamic session modifications
  modifySession: async (context) => {
    // Example: Change voice based on time of day
    const hour = new Date().getHours();
    if (hour < 12 && context.currentSession.voice !== "coral") {
      return {
        apply: true,
        updates: { voice: "coral" } // Morning voice
      };
    }
    
    return { apply: false };
  },
  
  // Custom routing logic
  routeResponse: async (context) => {
    // Example: Route support vs sales queries differently
    if (context.input.toLowerCase().includes("technical support")) {
      return {
        route: "custom",
        handler: async (ctx) => {
          // Custom handling for support queries
          return {
            type: "support",
            priority: "high"
          };
        },
        metadata: { department: "support" }
      };
    }
    
    return { route: "default" };
  }
};