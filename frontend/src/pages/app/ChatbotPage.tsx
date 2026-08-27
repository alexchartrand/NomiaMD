import { useState } from "react";
import { describeError, queryChatbot, type RAMQChatMessage } from "../../api";
import { Banner, Button, ChatBubble, Spinner, TextArea } from "../../components";

// Mirrors backend's ramq_chatbot/engine.py MAX_HISTORY_MESSAGES. Bandwidth/latency
// optimization only — the backend is the authoritative cap regardless of what's sent here.
const MAX_HISTORY_MESSAGES = 20;

export default function ChatbotPage() {
  const [messages, setMessages] = useState<RAMQChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSend(event: React.FormEvent) {
    event.preventDefault();
    const query = input.trim();
    if (!query || loading) return;

    const history = messages.slice(-MAX_HISTORY_MESSAGES);
    const nextMessages: RAMQChatMessage[] = [...messages, { role: "user", content: query }];
    setMessages(nextMessages);
    setInput("");
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
  }

  function handleClear() {
    setMessages([]);
    setError(null);
  }

  return (
    <section className="mx-auto flex h-[calc(100vh-5rem)] max-w-[860px] flex-col">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold">Clavardage de facturation</h1>
          <p className="mt-1 max-w-lg text-sm text-muted-foreground">
            Posez des questions générales de facturation RAMQ — sans lien avec une consultation
            précise.
          </p>
        </div>
        <Button variant="secondary" onClick={handleClear} disabled={loading || messages.length === 0}>
          Effacer la conversation
        </Button>
      </div>

      <div className="mt-4 flex flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card">
        <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
          {messages.length === 0 && !loading && (
            <p className="text-sm text-muted-foreground">Posez une question pour commencer.</p>
          )}
          {messages.map((message, i) => (
            <ChatBubble key={i} role={message.role} content={message.content} />
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="rounded-xl rounded-bl-[3px] border border-border bg-card px-4 py-2.5">
                <Spinner label="Réflexion…" />
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="px-5 pb-2">
            <Banner tone="error">{error}</Banner>
          </div>
        )}

        <form onSubmit={handleSend} className="flex items-end gap-3 border-t border-border px-5 py-4">
          <TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            rows={2}
            className="flex-1"
            placeholder="Posez une question de facturation..."
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend(e);
              }
            }}
          />
          <Button type="submit" disabled={loading || !input.trim()}>
            Envoyer
          </Button>
        </form>
      </div>
    </section>
  );
}
