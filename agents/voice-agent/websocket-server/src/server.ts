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
} from "./sessionManager";
import functions from "./functionHandlers";
import { CosmosClient, Container } from "@azure/cosmos";

dotenv.config();

const PORT = parseInt(process.env.PORT || "8081", 10);
const PUBLIC_URL = process.env.PUBLIC_URL || "";
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";
const OBJECTIVE = process.env.OBJECTIVE || "";
const COSMOS_CONNECTION = process.env.COSMOS_CONNECTION || "";
const COSMOS_DATABASE = process.env.COSMOS_DATABASE || "vextir";
const USER_CONTAINER = process.env.USER_CONTAINER || "users";

let userContainer: Container | undefined;
if (COSMOS_CONNECTION) {
  try {
    const cosmosClient = new CosmosClient(COSMOS_CONNECTION);
    userContainer = cosmosClient
      .database(COSMOS_DATABASE)
      .container(USER_CONTAINER);
  } catch (err) {
    console.error("Failed to init Cosmos client", err);
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
});
