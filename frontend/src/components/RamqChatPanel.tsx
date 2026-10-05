import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { useRamqChat } from "../chat/RamqChatProvider";
import { Banner } from "./Banner";
import { Button } from "./Button";
import { ChatBubble } from "./ChatBubble";
import { Spinner } from "./Spinner";
import { TextArea } from "./TextArea";

// The RAMQ conversation (messages + question box) over the shared RamqChatProvider thread.
// The page around it sets its height through `className`.
export function RamqChatPanel({ className }: { className?: string }) {
  const { messages, loading, error, send } = useRamqChat();
  const [input, setInput] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "nearest" });
  }, [messages.length, loading]);

  function handleSend(event: React.FormEvent) {
    event.preventDefault();
    if (!input.trim() || loading) return;
    void send(input);
    setInput("");
  }

  return (
    <div className={cn("flex flex-col overflow-hidden rounded-xl border border-border bg-card", className)}>
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
        <div ref={bottom} />
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
  );
}
