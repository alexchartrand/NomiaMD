import { useEffect, useRef, useState } from "react";
import { SendHorizontal, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { useRamqChat } from "../chat/RamqChatProvider";
import { Banner } from "./Banner";
import { Button } from "./Button";
import { ChatBubble } from "./ChatBubble";
import { Spinner } from "./Spinner";
import { TextArea } from "./TextArea";

// Questions the manual answers, to show what the assistant is for.
const SUGGESTIONS = [
  "Quelle est la différence entre une visite de suivi et une visite périodique ?",
  "Quand puis-je facturer un supplément pour un patient vulnérable ?",
  "Quel est le délai pour transmettre une facturation à la RAMQ ?",
];

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
          <div className="flex flex-col gap-3">
            <p className="m-0 flex items-center gap-2 text-sm text-muted-foreground">
              <Sparkles aria-hidden className="size-4 text-primary" />
              Posez une question pour commencer, par exemple :
            </p>
            <ul className="m-0 flex list-none flex-col items-start gap-2 p-0">
              {SUGGESTIONS.map((question) => (
                <li key={question}>
                  <button
                    type="button"
                    onClick={() => void send(question)}
                    className="cursor-pointer rounded-xl border border-border bg-card px-3 py-2 text-left text-sm transition-colors hover:border-primary hover:bg-[color:var(--color-primary-tint)]"
                  >
                    {question}
                  </button>
                </li>
              ))}
            </ul>
          </div>
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
          aria-label="Votre question"
          className="flex-1 font-sans"
          placeholder="Posez une question de facturation..."
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend(e);
            }
          }}
        />
        <Button type="submit" disabled={loading || !input.trim()}>
          <SendHorizontal aria-hidden />
          Envoyer
        </Button>
      </form>
    </div>
  );
}
