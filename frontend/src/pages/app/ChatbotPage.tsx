import { useState } from "react";
import { describeError, queryChatbot, type RAMQChatMessage } from "../../api";
import { Banner, Button, ChatBubble, Spinner, TextArea } from "../../components";

export default function ChatbotPage() {
  const [messages, setMessages] = useState<RAMQChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSend(event: React.FormEvent) {
    event.preventDefault();
    const query = input.trim();
    if (!query || loading) return;

    const history = messages;
    const nextMessages: RAMQChatMessage[] = [...history, { role: "user", content: query }];
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

  return (
    <section className="page-panel chat-panel">
      <h1>Clavardage de facturation</h1>
      <p className="lede">
        Posez des questions générales de facturation RAMQ — sans lien avec une consultation
        précise.
      </p>

      <div className="chat-thread">
        {messages.length === 0 && !loading && (
          <p className="chat-empty">Posez une question pour commencer.</p>
        )}
        {messages.map((message, i) => (
          <ChatBubble key={i} role={message.role} content={message.content} />
        ))}
        {loading && (
          <div className="chat-bubble-row chat-bubble-row-assistant">
            <div className="chat-bubble chat-bubble-assistant">
              <Spinner label="Réflexion…" />
            </div>
          </div>
        )}
      </div>

      {error && <Banner tone="error">{error}</Banner>}

      <form onSubmit={handleSend} className="chat-composer">
        <TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={2}
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
    </section>
  );
}
