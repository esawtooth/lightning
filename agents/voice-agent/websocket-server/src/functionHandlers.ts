import { FunctionHandler } from "./types";

const functions: FunctionHandler[] = [];


functions.push({
  schema: {
    name: "user_search",
    type: "function",
    description: "Search the user's knowledge base for relevant facts.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "search query" },
      },
      required: ["query"],
    },
  },
  handler: async (args: { query: string }) => {
    // TODO: replace with real implementation
    return JSON.stringify({ result: `No results for '${args.query}'.` });
  },
});

export default functions;
