import { RawData, WebSocket } from "ws";
import functions from "./functionHandlers";
import { setCallSid } from "./callControl";
import { AgentController, AgentControlHooks, ResponseContext, SpeechContext, FunctionContext } from "./agentController";

export type LogCallback = (ev: any) => void;
export type CallEndCallback = (logs: any[], user?: any) => void;

let logCallback: LogCallback | undefined;
let callEndCallback: CallEndCallback | undefined;

export function setLogCallback(cb: LogCallback) {
  logCallback = cb;
}

export function setCallEndCallback(cb: CallEndCallback) {
  callEndCallback = cb;
}

interface Session {
  twilioConn?: WebSocket;
  frontendConn?: WebSocket;
  modelConn?: WebSocket;
  streamSid?: string;
  saved_config?: any;
  lastAssistantItem?: string;
  responseStartTimestamp?: number;
  latestMediaTimestamp?: number;
  openAIApiKey?: string;
  objective?: string;
  userProfile?: any;
  callSid?: string;
  logs?: any[];
  conversation?: any[];
  lastUserInput?: string;
  agentController?: AgentController;
  pendingValidation?: {
    originalInput: string;
    validationPrompt: string;
    onValidation: (result: string) => Promise<boolean>;
  };
}

let session: Session = {};

// Export function to set custom hooks
export function setAgentHooks(hooks: AgentControlHooks) {
  if (!session.agentController) {
    session.agentController = new AgentController(hooks);
  } else {
    session.agentController.updateHooks(hooks);
  }
}

export function handleCallConnection(
  ws: WebSocket,
  openAIApiKey: string,
  objective?: string,
  userProfile?: any,
  customHooks?: AgentControlHooks
) {
  cleanupConnection(session.twilioConn);
  session.twilioConn = ws;
  session.openAIApiKey = openAIApiKey;
  session.objective = objective;
  session.userProfile = userProfile;
  session.logs = [];
  session.conversation = [];
  
  // Initialize agent controller with custom hooks if provided
  session.agentController = new AgentController(customHooks || {});

  ws.on("message", handleTwilioMessage);
  ws.on("error", ws.close);
  ws.on("close", () => {
    finalizeLogs();
    cleanupConnection(session.modelConn);
    cleanupConnection(session.twilioConn);
    resetSession();
  });
}

export function handleFrontendConnection(ws: WebSocket) {
  cleanupConnection(session.frontendConn);
  session.frontendConn = ws;

  ws.on("message", handleFrontendMessage);
  ws.on("close", () => {
    cleanupConnection(session.frontendConn);
    session.frontendConn = undefined;
    if (!session.twilioConn && !session.modelConn) session = {};
  });
}

async function handleFunctionCall(item: { name: string; arguments: string; call_id: string }) {
  console.log("Handling function call:", item);
  
  // Apply function control hooks
  if (session.agentController) {
    const context: FunctionContext = {
      functionName: item.name,
      arguments: JSON.parse(item.arguments),
      conversationHistory: session.conversation || []
    };
    
    const control = await session.agentController.handleBeforeFunctionCall(context);
    
    if (!control.execute) {
      return JSON.stringify({
        error: "Function execution blocked by agent controller"
      });
    }
    
    // Override arguments if specified
    if (control.overrideArgs) {
      item.arguments = JSON.stringify(control.overrideArgs);
    }
  }
  
  const fnDef = functions.find((f) => f.schema.name === item.name);
  if (!fnDef) {
    throw new Error(`No handler found for function: ${item.name}`);
  }

  let args: unknown;
  try {
    args = JSON.parse(item.arguments);
  } catch {
    return JSON.stringify({
      error: "Invalid JSON arguments for function call.",
    });
  }

  try {
    console.log("Calling function:", fnDef.schema.name, args);
    let result = await fnDef.handler(args as any);
    
    // Override result if specified by hooks
    if (session.agentController) {
      const control = await session.agentController.handleBeforeFunctionCall({
        functionName: item.name,
        arguments: args,
        conversationHistory: session.conversation || []
      });
      
      if (control.overrideResult) {
        result = control.overrideResult;
      }
    }
    
    return result;
  } catch (err: any) {
    console.error("Error running function:", err);
    return JSON.stringify({
      error: `Error running function ${item.name}: ${err.message}`,
    });
  }
}

function handleTwilioMessage(data: RawData) {
  const msg = parseMessage(data);
  if (!msg) return;

  if (session.logs) session.logs.push(msg);
  if (logCallback) logCallback(msg);

  switch (msg.event) {
    case "start":
      session.streamSid = msg.start.streamSid;
      session.callSid = msg.start.callSid ?? msg.start.CallSid;
      setCallSid(session.callSid);
      session.latestMediaTimestamp = 0;
      session.lastAssistantItem = undefined;
      session.responseStartTimestamp = undefined;
      tryConnectModel();
      break;
    case "media":
      session.latestMediaTimestamp = msg.media.timestamp;
      if (isOpen(session.modelConn)) {
        jsonSend(session.modelConn, {
          type: "input_audio_buffer.append",
          audio: msg.media.payload,
        });
      }
      break;
    case "close":
      closeAllConnections();
      break;
  }
}

function handleFrontendMessage(data: RawData) {
  const msg = parseMessage(data);
  if (!msg) return;

  // Handle special control messages
  if (msg.type === "agent.updateHooks" && msg.hooks) {
    setAgentHooks(msg.hooks);
    return;
  }
  
  if (msg.type === "agent.control") {
    handleAgentControlMessage(msg);
    return;
  }

  if (isOpen(session.modelConn)) {
    jsonSend(session.modelConn, msg);
  }

  if (msg.type === "session.update") {
    session.saved_config = msg.session;
  }
}

async function handleAgentControlMessage(msg: any) {
  if (!session.agentController || !session.modelConn) return;
  
  switch (msg.action) {
    case "createOutOfBandResponse":
      await session.agentController.createOutOfBandResponse(
        msg.instructions,
        msg.metadata,
        msg.input
      );
      break;
      
    case "disableVAD":
      jsonSend(session.modelConn, {
        type: "session.update",
        session: { turn_detection: null }
      });
      break;
      
    case "enableVAD":
      jsonSend(session.modelConn, {
        type: "session.update",
        session: { 
          turn_detection: { 
            type: "server_vad",
            threshold: msg.threshold || 0.5,
            prefix_padding_ms: msg.prefix_padding_ms || 300,
            silence_duration_ms: msg.silence_duration_ms || 500
          }
        }
      });
      break;
      
    case "setResponseBehavior":
      jsonSend(session.modelConn, {
        type: "session.update",
        session: {
          turn_detection: {
            type: "server_vad",
            create_response: msg.createResponse ?? true
          }
        }
      });
      break;
  }
}

function tryConnectModel() {
  if (!session.twilioConn || !session.streamSid || !session.openAIApiKey)
    return;
  if (isOpen(session.modelConn)) return;

  session.modelConn = new WebSocket(
    "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17",
    {
      headers: {
        Authorization: `Bearer ${session.openAIApiKey}`,
        "OpenAI-Beta": "realtime=v1",
      },
    }
  );
  
  // Set the model connection in the agent controller
  if (session.agentController) {
    session.agentController.setModelConnection(session.modelConn);
  }

  session.modelConn.on("open", () => {
    const config = session.saved_config || {};
    
    // Apply session modifications from hooks
    if (session.agentController) {
      session.agentController.handleSessionModification({
        event: { type: "session.open" },
        currentSession: config
      }).then(modification => {
        if (modification.apply && modification.updates) {
          Object.assign(config, modification.updates);
        }
      });
    }
    
    jsonSend(session.modelConn, {
      type: "session.update",
      session: {
        modalities: ["text", "audio"],
        turn_detection: { type: "server_vad" },
        voice: "ash",
        input_audio_transcription: { model: "whisper-1" },
        input_audio_format: "g711_ulaw",
        output_audio_format: "g711_ulaw",
        ...config,
      },
    });

    if (session.objective) {
      jsonSend(session.modelConn, {
        type: "conversation.create",
      });
      jsonSend(session.modelConn, {
        type: "conversation.item.create",
        item: {
          type: "message",
          role: "system",
          content: [
            {
              type: "text",
              text: `Your objective is: ${session.objective}. Use the user_search function to look up facts as needed.`,
            },
          ],
        },
      });
      jsonSend(session.modelConn, { type: "response.create" });
    }
  });

  session.modelConn.on("message", handleModelMessage);
  session.modelConn.on("error", closeModel);
  session.modelConn.on("close", closeModel);
}

async function handleModelMessage(data: RawData) {
  const event = parseMessage(data);
  if (!event) return;

  if (session.logs) session.logs.push(event);
  if (logCallback) logCallback(event);

  jsonSend(session.frontendConn, event);

  switch (event.type) {
    case "conversation.item.created":
      // Track conversation items
      if (!session.conversation) session.conversation = [];
      session.conversation.push(event.item);
      
      // Store last user input
      if (event.item.role === "user" && event.item.content?.[0]?.text) {
        session.lastUserInput = event.item.content[0].text;
      }
      break;

    case "input_audio_buffer.speech_started":
      handleTruncation();
      break;
      
    case "input_audio_buffer.speech_stopped":
      // Handle speech end with hooks
      if (session.agentController) {
        handleSpeechEndWithHooks(event);
      }
      break;

    case "response.audio.delta":
      if (session.twilioConn && session.streamSid) {
        if (session.responseStartTimestamp === undefined) {
          session.responseStartTimestamp = session.latestMediaTimestamp || 0;
        }
        if (event.item_id) session.lastAssistantItem = event.item_id;

        jsonSend(session.twilioConn, {
          event: "media",
          streamSid: session.streamSid,
          media: { payload: event.delta },
        });

        jsonSend(session.twilioConn, {
          event: "mark",
          streamSid: session.streamSid,
        });
      }
      break;
      
    case "response.created":
      // Handle response creation with hooks
      if (session.agentController && session.lastUserInput) {
        handleResponseCreatedWithHooks(event);
      }
      break;
      
    case "response.done":
      // Handle out-of-band response results
      if (event.response?.metadata?.type === "moderation" && session.pendingValidation) {
        handleValidationResult(event);
      }
      break;

    case "response.output_item.done": {
      const { item } = event;
      if (item.type === "function_call") {
        handleFunctionCall(item)
          .then((output) => {
            if (session.modelConn) {
              jsonSend(session.modelConn, {
                type: "conversation.item.create",
                item: {
                  type: "function_call_output",
                  call_id: item.call_id,
                  output: JSON.stringify(output),
                },
              });
              jsonSend(session.modelConn, { type: "response.create" });
            }
          })
          .catch((err) => {
            console.error("Error handling function call:", err);
          });
      }
      break;
    }
  }
}

async function handleSpeechEndWithHooks(event: any) {
  if (!session.agentController || !session.modelConn) return;
  
  const context: SpeechContext = {
    transcript: session.lastUserInput || "",
    audioDuration: 0, // Could calculate from timestamps
    sessionConfig: session.saved_config || {},
    conversationHistory: session.conversation || []
  };
  
  const control = await session.agentController.handleSpeechEnd(context);
  
  // Handle validation first if requested
  if (control.validateFirst) {
    session.pendingValidation = {
      originalInput: context.transcript,
      validationPrompt: control.validateFirst.instructions,
      onValidation: control.validateFirst.onValidation
    };
    
    await session.agentController.createOutOfBandResponse(
      control.validateFirst.instructions,
      { type: "moderation", originalInput: context.transcript }
    );
    return;
  }
  
  // Control automatic response generation
  if (!control.createResponse) {
    // Don't create automatic response
    jsonSend(session.modelConn, {
      type: "input_audio_buffer.clear"
    });
    return;
  }
  
  // Process transcript if needed
  if (control.processedTranscript && control.processedTranscript !== context.transcript) {
    // Update the conversation item with processed transcript
    const lastItem = session.conversation?.[session.conversation.length - 1];
    if (lastItem && lastItem.role === "user") {
      lastItem.content[0].text = control.processedTranscript;
    }
  }
}

async function handleResponseCreatedWithHooks(event: any) {
  if (!session.agentController || !session.modelConn) return;
  
  const context: ResponseContext = {
    conversation: session.conversation || [],
    userInput: session.lastUserInput || "",
    sessionConfig: session.saved_config || {},
    userProfile: session.userProfile,
    metadata: event.response?.metadata
  };
  
  const control = await session.agentController.handleBeforeResponse(context);
  
  if (!control.proceed) {
    // Cancel the response
    jsonSend(session.modelConn, {
      type: "response.cancel"
    });
    return;
  }
  
  // Apply response modifications
  const updates: any = {};
  
  if (control.instructions) {
    updates.instructions = control.instructions;
  }
  
  if (control.modalities) {
    updates.modalities = control.modalities;
  }
  
  if (control.voice) {
    updates.voice = control.voice;
  }
  
  if (control.tools) {
    updates.tools = control.tools;
  }
  
  if (control.toolChoice) {
    updates.tool_choice = control.toolChoice;
  }
  
  if (Object.keys(updates).length > 0) {
    // Update the response configuration
    jsonSend(session.modelConn, {
      type: "response.update",
      response: updates
    });
  }
  
  // Handle out-of-band response
  if (control.outOfBand) {
    // Cancel current response and create out-of-band
    jsonSend(session.modelConn, {
      type: "response.cancel"
    });
    
    await session.agentController.createOutOfBandResponse(
      control.outOfBand.instructions,
      control.outOfBand.metadata,
      control.outOfBand.input
    );
  }
  
  // Add custom context if specified
  if (control.customContext && control.customContext.length > 0) {
    for (const item of control.customContext) {
      jsonSend(session.modelConn, {
        type: "conversation.item.create",
        item
      });
    }
  }
  
  // Apply delay if specified
  if (control.delay && control.delay > 0) {
    await new Promise(resolve => setTimeout(resolve, control.delay));
  }
}

async function handleValidationResult(event: any) {
  if (!session.pendingValidation || !session.modelConn) return;
  
  const result = event.response?.output?.[0]?.content?.[0]?.text || "";
  const isValid = await session.pendingValidation.onValidation(result);
  
  if (isValid) {
    // Proceed with original response
    jsonSend(session.modelConn, { type: "response.create" });
  } else {
    // Block the response or provide alternative
    jsonSend(session.modelConn, {
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "assistant",
        content: [{
          type: "text",
          text: "I'm sorry, but I cannot process that request. Is there anything else I can help you with?"
        }]
      }
    });
  }
  
  session.pendingValidation = undefined;
}

function handleTruncation() {
  if (
    !session.lastAssistantItem ||
    session.responseStartTimestamp === undefined
  )
    return;

  const elapsedMs =
    (session.latestMediaTimestamp || 0) - (session.responseStartTimestamp || 0);
  const audio_end_ms = elapsedMs > 0 ? elapsedMs : 0;

  if (isOpen(session.modelConn)) {
    jsonSend(session.modelConn, {
      type: "conversation.item.truncate",
      item_id: session.lastAssistantItem,
      content_index: 0,
      audio_end_ms,
    });
  }

  if (session.twilioConn && session.streamSid) {
    jsonSend(session.twilioConn, {
      event: "clear",
      streamSid: session.streamSid,
    });
  }

  session.lastAssistantItem = undefined;
  session.responseStartTimestamp = undefined;
}

function resetSession() {
  session.twilioConn = undefined;
  session.modelConn = undefined;
  session.streamSid = undefined;
  session.callSid = undefined;
  setCallSid(undefined);
  session.lastAssistantItem = undefined;
  session.responseStartTimestamp = undefined;
  session.latestMediaTimestamp = undefined;
  session.userProfile = undefined;
  session.conversation = [];
  session.lastUserInput = undefined;
  session.agentController = undefined;
  session.pendingValidation = undefined;
  if (!session.frontendConn) session = {};
}

function closeModel() {
  cleanupConnection(session.modelConn);
  session.modelConn = undefined;
  if (!session.twilioConn && !session.frontendConn) session = {};
}

function closeAllConnections() {
  if (session.twilioConn) {
    session.twilioConn.close();
    session.twilioConn = undefined;
  }
  if (session.modelConn) {
    session.modelConn.close();
    session.modelConn = undefined;
  }
  if (session.frontendConn) {
    session.frontendConn.close();
    session.frontendConn = undefined;
  }
  resetSession();
}

function finalizeLogs() {
  if (session.logs && callEndCallback) {
    try {
      callEndCallback([...session.logs], session.userProfile);
    } catch (err) {
      console.error("Error finalizing logs", err);
    }
  }
  session.logs = [];
}

function cleanupConnection(ws?: WebSocket) {
  if (isOpen(ws)) ws.close();
}

function parseMessage(data: RawData): any {
  try {
    return JSON.parse(data.toString());
  } catch {
    return null;
  }
}

function jsonSend(ws: WebSocket | undefined, obj: unknown) {
  if (!isOpen(ws)) return;
  ws.send(JSON.stringify(obj));
}

function isOpen(ws?: WebSocket): ws is WebSocket {
  return !!ws && ws.readyState === WebSocket.OPEN;
}