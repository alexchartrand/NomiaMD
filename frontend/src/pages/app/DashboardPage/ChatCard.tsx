import { Link } from "react-router-dom";
import { RamqChatPanel } from "../../../components";
import { useRamqChat } from "../../../chat/RamqChatProvider";
import { panelLinkClasses } from "./Panel";

// The RAMQ assistant beside the dashboard — the same thread as /app/chat, which
// "Agrandir" opens full-page.
export function ChatCard() {
  const { messages, loading, clear } = useRamqChat();
  return (
    <aside aria-label="Assistant RAMQ" className="flex flex-col lg:sticky lg:top-0">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-heading text-base font-semibold">Assistant RAMQ</h2>
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={clear}
            disabled={loading || messages.length === 0}
            className="cursor-pointer border-none bg-transparent p-0 text-sm font-medium text-muted-foreground hover:text-foreground disabled:cursor-default disabled:opacity-50"
          >
            Effacer
          </button>
          <Link to="/app/chat" className={panelLinkClasses}>
            Agrandir
          </Link>
        </div>
      </div>
      <RamqChatPanel className="h-[420px] max-h-[calc(100vh-8rem)] lg:h-[560px]" />
    </aside>
  );
}
