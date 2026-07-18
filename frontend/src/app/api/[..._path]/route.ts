import { initApiPassthrough } from "langgraph-nextjs-api-passthrough";

// Local development defaults to the local LangGraph server. Production must
// set LANGGRAPH_API_URL and keep any deployment key server-side.
export const { GET, POST, PUT, PATCH, DELETE, OPTIONS, runtime } =
  initApiPassthrough({
    apiUrl: process.env.LANGGRAPH_API_URL ?? "http://localhost:2024",
    apiKey: process.env.LANGSMITH_API_KEY,
    runtime: "edge",
  });
