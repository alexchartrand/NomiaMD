import { unwrap } from "./http";

export interface RAMQChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface RAMQQueryResult {
  answer: string;
}

export async function queryChatbot(query: string, history: RAMQChatMessage[]): Promise<RAMQQueryResult> {
  const response = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, history }),
  });
  return unwrap<RAMQQueryResult>(response);
}
