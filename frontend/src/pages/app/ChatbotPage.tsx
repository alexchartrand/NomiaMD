import { Eraser } from "lucide-react";
import { AppPage, AppPageHeader, Button, RamqChatPanel } from "../../components";
import { useRamqChat } from "../../chat/RamqChatProvider";

export default function ChatbotPage() {
  const { messages, loading, clear } = useRamqChat();

  return (
    <AppPage width="narrow" className="flex h-[calc(100dvh-4rem)] flex-col">
      <AppPageHeader
        title="Assistant"
        description="Questions générales sur la facturation (codes, tarifs, règles d&apos;application)."
        actions={
          <Button variant="secondary" onClick={clear} disabled={loading || messages.length === 0}>
            <Eraser aria-hidden />
            Effacer la conversation
          </Button>
        }
        className="mb-4"
      />
      <RamqChatPanel className="flex-1" />
    </AppPage>
  );
}
