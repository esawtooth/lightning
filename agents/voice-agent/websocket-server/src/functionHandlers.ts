import { FunctionHandler } from "./types";
import { sendDigits } from "./callControl";

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
