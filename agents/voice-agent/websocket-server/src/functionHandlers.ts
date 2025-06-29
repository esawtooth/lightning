import { FunctionHandler } from "./types";
import { sendDigits } from "./callControl";

const functions: FunctionHandler[] = [];

const CONTEXT_HUB_URL = process.env.CONTEXT_HUB_URL || "http://context-hub:3000";
const API_BASE = process.env.API_BASE || "http://lightning-api:8000";

functions.push({
  schema: {
    name: "user_search",
    type: "function",
    description: "Search the user's knowledge base for relevant facts and information.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query to find relevant information in the knowledge base" },
      },
      required: ["query"],
    },
  },
  handler: async (args: { query: string }) => {
    try {
      // Use Lightning Core Context Hub search endpoint
      const searchUrl = `${CONTEXT_HUB_URL}/search?q=${encodeURIComponent(args.query)}&limit=5`;
      const response = await fetch(searchUrl);
      
      if (!response.ok) {
        throw new Error(`Context Hub search failed: ${response.status}`);
      }
      
      const results = await response.json();
      
      if (results.documents && results.documents.length > 0) {
        const summaries = results.documents.map((doc: any) => ({
          title: doc.title || "Document",
          content: doc.content?.substring(0, 300) + "...",
          score: doc.score
        }));
        
        return JSON.stringify({ 
          success: true,
          results: summaries,
          total: results.total || summaries.length,
          query: args.query
        });
      } else {
        return JSON.stringify({ 
          success: true,
          results: [],
          message: `No results found for '${args.query}' in your knowledge base.`,
          query: args.query
        });
      }
    } catch (error: any) {
      console.error("Error searching Context Hub:", error);
      return JSON.stringify({ 
        success: false,
        error: `Search failed: ${error.message}`,
        query: args.query
      });
    }
  },
});

functions.push({
  schema: {
    name: "web_search",
    type: "function",
    description: "Search the web for current information and news.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query for web search" },
        num_results: { type: "number", description: "Number of results to return (default: 5)", minimum: 1, maximum: 10 }
      },
      required: ["query"],
    },
  },
  handler: async (args: { query: string; num_results?: number }) => {
    try {
      // Use Lightning Core's tool system for web search
      const toolsUrl = `${API_BASE}/tools/execute`;
      const response = await fetch(toolsUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          tool_name: "web_search",
          parameters: {
            query: args.query,
            num_results: args.num_results || 5
          }
        })
      });
      
      if (!response.ok) {
        throw new Error(`Web search failed: ${response.status}`);
      }
      
      const results = await response.json();
      return JSON.stringify({
        success: true,
        results: results.data || results,
        query: args.query
      });
    } catch (error: any) {
      console.error("Error performing web search:", error);
      return JSON.stringify({
        success: false,
        error: `Web search failed: ${error.message}`,
        query: args.query
      });
    }
  },
});

functions.push({
  schema: {
    name: "generate_event",
    type: "function", 
    description: "Generate an event in the Lightning OS event system to trigger workflows or notify other components.",
    parameters: {
      type: "object",
      properties: {
        event_type: { type: "string", description: "Type of event to generate (e.g., 'user.task.created', 'reminder.scheduled')" },
        description: { type: "string", description: "Human-readable description of the event" },
        metadata: { type: "object", description: "Additional event metadata", additionalProperties: true }
      },
      required: ["event_type", "description"],
    },
  },
  handler: async (args: { event_type: string; description: string; metadata?: any }) => {
    try {
      // Use Lightning Core's event system
      const eventsUrl = `${API_BASE}/events`;
      const eventData = {
        type: args.event_type,
        source: "voice-agent",
        description: args.description,
        metadata: {
          timestamp: new Date().toISOString(),
          ...(args.metadata || {})
        }
      };
      
      const response = await fetch(eventsUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(eventData)
      });
      
      if (!response.ok) {
        throw new Error(`Event generation failed: ${response.status}`);
      }
      
      const result = await response.json();
      return JSON.stringify({
        success: true,
        event_id: result.id || result.event_id,
        event_type: args.event_type,
        description: args.description,
        message: "Event generated successfully"
      });
    } catch (error: any) {
      console.error("Error generating event:", error);
      return JSON.stringify({
        success: false,
        error: `Event generation failed: ${error.message}`,
        event_type: args.event_type
      });
    }
  },
});

functions.push({
  schema: {
    name: "dial_digits",
    type: "function",
    description: "Send DTMF digits to the current call to navigate IVR menus.",
    parameters: {
      type: "object",
      properties: {
        digits: { type: "string", description: "Digits to send" },
      },
      required: ["digits"],
    },
  },
  handler: async (args: { digits: string }) => {
    const result = await sendDigits(args.digits);
    return JSON.stringify(result);
  },
});

export default functions;
