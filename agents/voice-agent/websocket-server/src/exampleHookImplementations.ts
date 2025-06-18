import { AgentControlHooks } from "./agentController";

// Example 1: Customer Service Agent with Department Routing
export const customerServiceHooks: AgentControlHooks = {
  beforeResponse: async (context) => {
    const { userInput, userProfile } = context;
    
    // VIP customers get priority treatment
    if (userProfile?.tier === "vip") {
      return {
        proceed: true,
        instructions: "This is a VIP customer. Be extra attentive and offer premium solutions. Address them by name if available.",
        voice: "sage", // More professional voice for VIPs
      };
    }
    
    // Angry customer detection
    const angryWords = ["frustrated", "angry", "terrible", "worst", "unacceptable"];
    const isAngry = angryWords.some(word => userInput.toLowerCase().includes(word));
    
    if (isAngry) {
      return {
        proceed: true,
        instructions: "The customer seems frustrated. Be empathetic, apologize for any inconvenience, and focus on resolving their issue quickly.",
        voice: "coral", // Calmer voice for de-escalation
      };
    }
    
    return { proceed: true };
  },
  
  routeResponse: async (context) => {
    const input = context.input.toLowerCase();
    
    // Technical support routing
    if (input.includes("error") || input.includes("not working") || input.includes("bug")) {
      return {
        route: "custom",
        metadata: { 
          department: "technical_support",
          priority: input.includes("urgent") ? "high" : "normal"
        }
      };
    }
    
    // Billing inquiries
    if (input.includes("bill") || input.includes("charge") || input.includes("payment")) {
      return {
        route: "custom",
        metadata: { department: "billing" }
      };
    }
    
    // Sales opportunities
    if (input.includes("upgrade") || input.includes("new feature") || input.includes("pricing")) {
      return {
        route: "custom",
        metadata: { department: "sales" }
      };
    }
    
    return { route: "default" };
  }
};

// Example 2: Financial Services Agent with Compliance
export const financialServicesHooks: AgentControlHooks = {
  onSpeechEnd: async (context) => {
    const { transcript } = context;
    const sensitiveTerms = ["ssn", "social security", "account number", "routing number", "password"];
    
    // Check for sensitive information
    const containsSensitive = sensitiveTerms.some(term => 
      transcript.toLowerCase().includes(term)
    );
    
    if (containsSensitive) {
      return {
        createResponse: true,
        addToConversation: false, // Don't store sensitive info
        processedTranscript: "[REDACTED - Contains sensitive information]",
        validateFirst: {
          instructions: "Determine if the user is trying to share sensitive financial information. If yes, respond 'sensitive'. If no, respond 'safe'.",
          onValidation: async (result) => {
            if (result.includes("sensitive")) {
              // Log security event
              console.log("Security: User attempted to share sensitive information");
              return false;
            }
            return true;
          }
        }
      };
    }
    
    // Transaction requests need validation
    if (transcript.includes("transfer") || transcript.includes("send money")) {
      return {
        createResponse: true,
        addToConversation: true,
        validateFirst: {
          instructions: "Analyze if this is a legitimate transaction request. Check for signs of fraud or coercion. Respond 'legitimate' or 'suspicious'.",
          onValidation: async (result) => result.includes("legitimate")
        }
      };
    }
    
    return { createResponse: true, addToConversation: true };
  },
  
  beforeFunctionCall: async (context) => {
    const { functionName, arguments: args } = context;
    
    // Block high-value transactions without additional verification
    if (functionName === "transfer_funds" && args.amount > 10000) {
      console.log("High-value transaction blocked pending verification");
      return {
        execute: false,
        overrideResult: {
          error: "High-value transactions require additional verification. Please contact support."
        }
      };
    }
    
    // Log all financial operations
    if (["transfer_funds", "check_balance", "view_transactions"].includes(functionName)) {
      console.log(`Financial operation: ${functionName}`, args);
    }
    
    return { execute: true };
  }
};

// Example 3: Healthcare Agent with HIPAA Compliance
export const healthcareHooks: AgentControlHooks = {
  beforeResponse: async (context) => {
    const { userInput, userProfile } = context;
    
    // Ensure HIPAA compliance notice
    const baseInstructions = "Remember to maintain HIPAA compliance. Do not discuss patient information without proper verification.";
    
    // Emergency detection
    const emergencyWords = ["emergency", "urgent", "critical", "severe pain", "can't breathe"];
    const isEmergency = emergencyWords.some(word => userInput.toLowerCase().includes(word));
    
    if (isEmergency) {
      return {
        proceed: true,
        instructions: `${baseInstructions} This seems like an emergency. Advise the caller to call 911 or go to the nearest emergency room immediately.`,
        modalities: ["audio"], // Audio only for emergencies
        voice: "sage" // Clear, calm voice
      };
    }
    
    // Mental health support
    if (userInput.includes("depressed") || userInput.includes("anxious") || userInput.includes("suicide")) {
      return {
        proceed: true,
        instructions: `${baseInstructions} Be extremely compassionate and supportive. Provide crisis helpline numbers if appropriate.`,
        voice: "coral" // Warm, empathetic voice
      };
    }
    
    return { 
      proceed: true,
      instructions: baseInstructions
    };
  },
  
  onSpeechEnd: async (context) => {
    // Never record detailed medical information in logs
    const medicalTerms = ["diagnosis", "prescription", "symptoms", "medical history"];
    const containsMedical = medicalTerms.some(term => 
      context.transcript.toLowerCase().includes(term)
    );
    
    if (containsMedical) {
      return {
        createResponse: true,
        addToConversation: true,
        processedTranscript: "[Medical information discussed - details redacted for HIPAA compliance]"
      };
    }
    
    return { createResponse: true, addToConversation: true };
  }
};

// Example 4: Educational Tutor with Adaptive Learning
export const educationTutorHooks: AgentControlHooks = {
  beforeResponse: async (context) => {
    const { userInput, userProfile, metadata } = context;
    
    // Adapt instruction style based on student level
    const studentLevel = userProfile?.gradeLevel || metadata?.gradeLevel || "unknown";
    
    let instructions = "You are a friendly educational tutor. ";
    
    switch (studentLevel) {
      case "elementary":
        instructions += "Use simple language, be encouraging, and use fun examples. Break down concepts into small steps.";
        break;
      case "middle":
        instructions += "Balance explanation with practice. Encourage critical thinking and relate concepts to real life.";
        break;
      case "high":
        instructions += "Provide detailed explanations, introduce advanced concepts, and prepare for standardized tests.";
        break;
      case "college":
        instructions += "Engage in academic discourse, cite sources when relevant, and encourage independent research.";
        break;
    }
    
    // Detect struggling students
    const struggleIndicators = ["don't understand", "confused", "help", "lost"];
    const isStruggling = struggleIndicators.some(phrase => userInput.toLowerCase().includes(phrase));
    
    if (isStruggling) {
      instructions += " The student seems to be struggling. Slow down, provide more examples, and check understanding frequently.";
      return {
        proceed: true,
        instructions,
        voice: "alloy", // Patient, clear voice
        modalities: ["text", "audio"] // Both modalities for better understanding
      };
    }
    
    return { proceed: true, instructions };
  },
  
  modifySession: async (context) => {
    // Adjust session based on time of day (student attention spans)
    const hour = new Date().getHours();
    
    if (hour < 10) {
      // Morning session - students might be sleepy
      return {
        apply: true,
        updates: {
          voice: "echo", // Energetic voice
          turn_detection: {
            type: "server_vad",
            silence_duration_ms: 800 // Give sleepy students more time
          }
        }
      };
    } else if (hour > 20) {
      // Evening session - students might be tired
      return {
        apply: true,
        updates: {
          voice: "ballad", // Calm voice
          turn_detection: {
            type: "server_vad",
            silence_duration_ms: 700
          }
        }
      };
    }
    
    return { apply: false };
  }
};

// Example 5: Sales Agent with Lead Qualification
export const salesAgentHooks: AgentControlHooks = {
  beforeResponse: async (context) => {
    const { conversation, userInput } = context;
    
    // Track conversation stage
    const messageCount = conversation.filter(item => item.role === "user").length;
    
    if (messageCount === 0) {
      return {
        proceed: true,
        instructions: "Warmly greet the prospect. Briefly introduce our value proposition and ask an open-ended question to understand their needs."
      };
    } else if (messageCount < 3) {
      return {
        proceed: true,
        instructions: "Focus on discovery. Ask qualifying questions about their current solution, pain points, and budget.",
        outOfBand: {
          instructions: "Based on the conversation so far, score this lead as: HOT, WARM, or COLD",
          metadata: { type: "lead_scoring", stage: "early" }
        }
      };
    } else if (messageCount < 6) {
      return {
        proceed: true,
        instructions: "Present relevant solutions based on their stated needs. Use social proof and case studies."
      };
    } else {
      return {
        proceed: true,
        instructions: "Move towards closing. Offer a demo, trial, or next steps. Handle objections professionally."
      };
    }
  },
  
  routeResponse: async (context) => {
    const input = context.input.toLowerCase();
    
    // Detect buying signals
    const buyingSignals = ["how much", "pricing", "when can we start", "implementation", "contract"];
    const hasBuyingSignal = buyingSignals.some(signal => input.includes(signal));
    
    if (hasBuyingSignal) {
      return {
        route: "custom",
        handler: async (ctx) => {
          // Log high-intent lead
          console.log("High-intent lead detected:", ctx.input);
          return { priority: "high", action: "notify_sales_team" };
        },
        metadata: { intent: "high", stage: "consideration" }
      };
    }
    
    // Detect objections
    const objections = ["too expensive", "not sure", "need to think", "competitor"];
    const hasObjection = objections.some(obj => input.includes(obj));
    
    if (hasObjection) {
      return {
        route: "custom",
        metadata: { type: "objection_handling" }
      };
    }
    
    return { route: "default" };
  }
};

// Example 6: Multi-lingual Support Agent
export const multiLingualHooks: AgentControlHooks = {
  onSpeechEnd: async (context) => {
    // First, detect language
    return {
      createResponse: false, // Don't respond yet
      addToConversation: true,
      validateFirst: {
        instructions: "Detect the language of this text and respond with ONLY the language code (en, es, fr, de, ja, zh, etc.): " + context.transcript,
        onValidation: async (langCode) => {
          // Store detected language for response
          context.sessionConfig.detectedLanguage = langCode.trim().toLowerCase();
          return true;
        }
      }
    };
  },
  
  beforeResponse: async (context) => {
    const detectedLang = context.sessionConfig?.detectedLanguage || "en";
    
    const languageInstructions: Record<string, string> = {
      es: "Responda en español. Sea formal y use 'usted'.",
      fr: "Répondez en français. Soyez poli et formel.",
      de: "Antworten Sie auf Deutsch. Seien Sie höflich und formell.",
      ja: "日本語で応答してください。丁寧語を使用してください。",
      zh: "请用中文回复。请使用礼貌和正式的语言。"
    };
    
    return {
      proceed: true,
      instructions: languageInstructions[detectedLang] || "Respond in English.",
      voice: detectedLang === "es" ? "sage" : "ash" // Some voices work better for certain languages
    };
  }
};

// Utility function to combine multiple hook sets
export function combineHooks(...hookSets: AgentControlHooks[]): AgentControlHooks {
  const combined: AgentControlHooks = {};
  
  // Combine each hook type
  const hookTypes: (keyof AgentControlHooks)[] = [
    'beforeResponse', 
    'onSpeechEnd', 
    'beforeFunctionCall', 
    'modifySession', 
    'routeResponse'
  ];
  
  for (const hookType of hookTypes) {
    const hooks = hookSets.filter(set => set[hookType]).map(set => set[hookType]!);
    
    if (hooks.length > 0) {
      combined[hookType] = async (context: any) => {
        // Run hooks in sequence, passing results forward
        let result: any = {};
        
        for (const hook of hooks) {
          const hookResult = await hook(context);
          result = { ...result, ...hookResult };
        }
        
        return result;
      };
    }
  }
  
  return combined;
}

// Example: Combine compliance with department routing
export const enterpriseHooks = combineHooks(
  customerServiceHooks,
  {
    beforeResponse: async (context) => {
      // Add compliance footer to all responses
      return {
        proceed: true,
        instructions: (context.userInput || '') + "\n\nAlways end responses with: 'This call may be recorded for quality assurance.'"
      };
    }
  }
);