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
import { CosmosClient, Container } from "@azure/cosmos";
import { ServiceBusClient, ServiceBusMessage } from "@azure/service-bus";
import { getCallSid, startCall } from "./callControl";

dotenv.config();

const PORT = parseInt(process.env.PORT || "8081", 10);
const PUBLIC_URL = process.env.PUBLIC_URL || "";
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";
const OBJECTIVE = process.env.OBJECTIVE || "";
const COSMOS_CONNECTION = process.env.COSMOS_CONNECTION || "";
const COSMOS_DATABASE = process.env.COSMOS_DATABASE || "vextir";
const USER_CONTAINER = process.env.USER_CONTAINER || "users";
const LOG_CONTAINER = process.env.LOG_CONTAINER || "logs";
const REPO_CONTAINER = process.env.REPO_CONTAINER || "repos";
const CALL_CONTAINER = process.env.CALL_CONTAINER || "calls";
const SERVICEBUS_CONNECTION = process.env.SERVICEBUS_CONNECTION || "";
const SERVICEBUS_QUEUE = process.env.SERVICEBUS_QUEUE || "";
const OUTBOUND_TO = process.env.OUTBOUND_TO;

let userContainer: Container | undefined;
let logContainer: Container | undefined;
let repoContainer: Container | undefined;
let callContainer: Container | undefined;
let sbClient: ServiceBusClient | undefined;
if (COSMOS_CONNECTION) {
  try {
    const cosmosClient = new CosmosClient(COSMOS_CONNECTION);
    userContainer = cosmosClient
      .database(COSMOS_DATABASE)
      .container(USER_CONTAINER);
    logContainer = cosmosClient
      .database(COSMOS_DATABASE)
      .container(LOG_CONTAINER);
    repoContainer = cosmosClient
      .database(COSMOS_DATABASE)
      .container(REPO_CONTAINER);
    callContainer = cosmosClient
      .database(COSMOS_DATABASE)
      .container(CALL_CONTAINER);
  } catch (err) {
    console.error("Failed to init Cosmos client", err);
  }
}

if (SERVICEBUS_CONNECTION && SERVICEBUS_QUEUE) {
  try {
    sbClient = new ServiceBusClient(SERVICEBUS_CONNECTION);
  } catch (err) {
    console.error("Failed to init Service Bus client", err);
  }
}

setLogCallback(recordLog);
setCallEndCallback(saveTranscript);

function recordLog(event: any) {
  if (!logContainer) return;
  const callId = getCallSid() || "unknown";
  const entity = {
    id: `${callId}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    pk: callId,
    timestamp: new Date().toISOString(),
    event,
  };
  logContainer.items
    .create(entity)
    .catch((err) => console.error("Failed to store log", err));
}

async function saveTranscript(logs: any[], user?: any) {
  const callId = getCallSid() || `call-${Date.now()}`;
  if (callContainer) {
    const entity = {
      id: callId,
      pk: user?.id || "anon",
      timestamp: new Date().toISOString(),
      logs,
    };
    try {
      await callContainer.items.create(entity);
    } catch (err) {
      console.error("Failed to save call transcript", err);
    }
  }

  if (sbClient) {
    const outEvent = {
      timestamp: new Date().toISOString(),
      source: "voice-agent",
      type: "voice.call.done",
      userID: user?.id || "anon",
      metadata: { callId },
    };
    const message: ServiceBusMessage = {
      body: JSON.stringify(outEvent),
      applicationProperties: { topic: outEvent.type },
    } as any;
    try {
      const sender = sbClient.createSender(SERVICEBUS_QUEUE);
      await sender.sendMessages(message);
      await sender.close();
    } catch (err) {
      console.error("Failed to publish call event", err);
    }
  }
}

let currentUserProfile: any | null = null;

async function lookupUserByPhone(phone: string): Promise<any | null> {
  if (!userContainer || !phone) return null;
  try {
    const query = {
      query: "SELECT * FROM c WHERE c.phone_number = @phone",
      parameters: [{ name: "@phone", value: phone }],
    };
    const { resources } = await userContainer.items.query(query).fetchAll();
    return resources[0] || null;
  } catch (err) {
    console.error("Failed to query user", err);
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
    cosmos: !!userContainer,
    servicebus: !!sbClient
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
