import { FunctionHandler } from "./types";

const functions: FunctionHandler[] = [];

functions.push({
  schema: {
    name: "get_weather_from_coords",
    type: "function",
    description: "Get the current weather",
    parameters: {
      type: "object",
      properties: {
        latitude: {
          type: "number",
        },
        longitude: {
          type: "number",
        },
      },
      required: ["latitude", "longitude"],
    },
  },
  handler: async (args: { latitude: number; longitude: number }) => {
    const response = await fetch(
      `https://api.open-meteo.com/v1/forecast?latitude=${args.latitude}&longitude=${args.longitude}&current=temperature_2m,wind_speed_10m&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m`
    );
    const data = await response.json();
    const currentTemp = data.current?.temperature_2m;
    return JSON.stringify({ temp: currentTemp });
  },
});

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
