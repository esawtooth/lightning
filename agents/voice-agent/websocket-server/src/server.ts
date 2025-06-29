import express from "express";
import { WebSocketServer, WebSocket } from "ws";
import { IncomingMessage } from "http";
import dotenv from "dotenv";
import http from "http";
import { readFileSync } from "fs";
import { join } from "path";
import cors from "cors";
import {
  handleCallConnection,
  handleFrontendConnection,
  setLogCallback,
  setCallEndCallback,
} from "./sessionManager";
import functions from "./functionHandlers";
import { getCallSid, startCall } from "./callControl";

dotenv.config();

const PORT = parseInt(process.env.PORT || "8081", 10);
const PUBLIC_URL = process.env.PUBLIC_URL || "";
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";
const OBJECTIVE = process.env.OBJECTIVE || "";
const OUTBOUND_TO = process.env.OUTBOUND_TO;

// Lightning Core Integration
const LIGHTNING_MODE = process.env.LIGHTNING_MODE || "local";
const API_BASE = process.env.API_BASE || "http://lightning-api:8000";
const CONTEXT_HUB_URL = process.env.CONTEXT_HUB_URL || "http://context-hub:3000";

// Lightning Core API helpers
async function callLightningAPI(endpoint: string, options: RequestInit = {}) {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });
  
  if (!response.ok) {
    throw new Error(`Lightning API call failed: ${response.status} ${response.statusText}`);
  }
  
  return response.json();
}

setLogCallback(recordLog);
setCallEndCallback(saveTranscript);

function recordLog(event: any) {
  // Store logs through Lightning Core storage API
  const callId = getCallSid() || "unknown";
  const logData = {
    id: `${callId}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    call_id: callId,
    timestamp: new Date().toISOString(),
    event,
  };
  
  callLightningAPI('/storage/voice-logs', {
    method: 'POST',
    body: JSON.stringify(logData),
  }).catch((err) => console.error("Failed to store log via Lightning Core:", err));
}

async function saveTranscript(logs: any[], user?: any) {
  const callId = getCallSid() || `call-${Date.now()}`;
  
  // Save transcript through Lightning Core storage
  const transcriptData = {
    id: callId,
    user_id: user?.id || "anon",
    timestamp: new Date().toISOString(),
    logs,
  };
  
  try {
    await callLightningAPI('/storage/call-transcripts', {
      method: 'POST',
      body: JSON.stringify(transcriptData),
    });
  } catch (err) {
    console.error("Failed to save call transcript via Lightning Core:", err);
  }

  // Publish event through Lightning Core event system
  const eventData = {
    type: "voice.call.completed",
    source: "voice-agent",
    description: `Voice call completed for user ${user?.id || "anon"}`,
    metadata: {
      call_id: callId,
      user_id: user?.id || "anon",
      duration_ms: logs.length > 0 ? Date.now() - new Date(logs[0]?.timestamp || Date.now()).getTime() : 0,
      total_interactions: logs.filter(log => log.type === 'function_call').length,
    },
  };
  
  try {
    await callLightningAPI('/events', {
      method: 'POST',
      body: JSON.stringify(eventData),
    });
  } catch (err) {
    console.error("Failed to publish call completion event via Lightning Core:", err);
  }
}

let currentUserProfile: any | null = null;

async function lookupUserByPhone(phone: string): Promise<any | null> {
  if (!phone) return null;
  try {
    // Use Lightning Core storage API to lookup user by phone
    const users = await callLightningAPI(`/storage/users?phone_number=${encodeURIComponent(phone)}`);
    return users.length > 0 ? users[0] : null;
  } catch (err) {
    console.error("Failed to query user via Lightning Core:", err);
    return null;
  }
}

if (!OPENAI_API_KEY) {
  console.error("OPENAI_API_KEY environment variable is required");
  process.exit(1);
}

const app = express();
app.use(cors());
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

app.use(express.urlencoded({ extended: false }));

const twimlPath = join(__dirname, "twiml.xml");
const twimlTemplate = readFileSync(twimlPath, "utf-8");

app.get("/public-url", (req, res) => {
  res.json({ publicUrl: PUBLIC_URL });
});

// Health check endpoint
app.get("/health", (req, res) => {
  res.json({
    status: "healthy",
    service: "voice-websocket-server",
    timestamp: new Date().toISOString(),
    lightning_mode: LIGHTNING_MODE,
    api_base: API_BASE,
    context_hub: CONTEXT_HUB_URL,
    openai_configured: !!OPENAI_API_KEY
  });
});

app.all("/twiml", async (req, res) => {
  const from = (req.body?.From as string) || (req.query?.From as string) || "";
  currentUserProfile = await lookupUserByPhone(from);

  const wsUrl = new URL(PUBLIC_URL);
  wsUrl.protocol = "wss:";
  wsUrl.pathname = `/call`;

  const twimlContent = twimlTemplate.replace("{{WS_URL}}", wsUrl.toString());
  res.type("text/xml").send(twimlContent);
});

// New endpoint to list available tools (schemas)
app.get("/tools", (req, res) => {
  res.json(functions.map((f) => f.schema));
});

let currentCall: WebSocket | null = null;
let currentLogs: WebSocket | null = null;

wss.on("connection", (ws: WebSocket, req: IncomingMessage) => {
  const url = new URL(req.url || "", `http://${req.headers.host}`);
  const parts = url.pathname.split("/").filter(Boolean);

  if (parts.length < 1) {
    ws.close();
    return;
  }

  const type = parts[0];

  if (type === "call") {
    if (currentCall) currentCall.close();
    currentCall = ws;
    handleCallConnection(currentCall, OPENAI_API_KEY, OBJECTIVE, currentUserProfile || undefined);
  } else if (type === "logs") {
    if (currentLogs) currentLogs.close();
    currentLogs = ws;
    handleFrontendConnection(currentLogs);
  } else {
    ws.close();
  }
});

server.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
  if (OUTBOUND_TO) {
    startCall(OUTBOUND_TO).catch((err) =>
      console.error("Failed to start outbound call", err)
    );
  }
});
