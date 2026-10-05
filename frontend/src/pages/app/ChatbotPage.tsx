import { Button, RamqChatPanel } from "../../components";
import { useRamqChat } from "../../chat/RamqChatProvider";

export default function ChatbotPage() {
  const { messages, loading, clear } = useRamqChat();

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
        <Button variant="secondary" onClick={clear} disabled={loading || messages.length === 0}>
          Effacer la conversation
        </Button>
      </div>

      <RamqChatPanel className="mt-4 flex-1" />
    </section>
  );
}
