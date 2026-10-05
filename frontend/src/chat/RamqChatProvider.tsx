import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { describeError, queryChatbot, type RAMQChatMessage } from "../api";

// Mirrors backend's ramq_chatbot/engine.py MAX_HISTORY_MESSAGES. Bandwidth/latency
// optimization only — the backend is the authoritative cap regardless of what's sent here.
const MAX_HISTORY_MESSAGES = 20;

interface RamqChat {
  messages: RAMQChatMessage[];
  loading: boolean;
  error: string | null;
  send: (query: string) => Promise<void>;
  clear: () => void;
}

const RamqChatContext = createContext<RamqChat | null>(null);

// One RAMQ conversation for the whole app area: the dashboard's panel and /app/chat show
// the same thread. Mounted in AppLayout, so it ends with the session (logout unmounts it).
// The backend is stateless — the history travels with each question.
export function RamqChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<RAMQChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = useCallback(
    async (raw: string) => {
      const query = raw.trim();
      if (!query || loading) return;
      const history = messages.slice(-MAX_HISTORY_MESSAGES);
      const nextMessages: RAMQChatMessage[] = [...messages, { role: "user", content: query }];
      setMessages(nextMessages);
      setError(null);
      setLoading(true);
      try {
        const { answer } = await queryChatbot(query, history);
        setMessages([...nextMessages, { role: "assistant", content: answer }]);
      } catch (err) {
        setError(describeError(err));
      } finally {
        setLoading(false);
      }
    },
    [messages, loading],
  );

  const clear = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  const value = useMemo(() => ({ messages, loading, error, send, clear }), [messages, loading, error, send, clear]);
  return <RamqChatContext.Provider value={value}>{children}</RamqChatContext.Provider>;
}

export function useRamqChat(): RamqChat {
  const chat = useContext(RamqChatContext);
  if (!chat) throw new Error("useRamqChat must be used inside a RamqChatProvider");
  return chat;
}
