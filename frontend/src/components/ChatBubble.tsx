import { memo } from "react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";

type ChatBubbleProps = {
  role: "user" | "assistant";
  content: string;
};

function ChatBubbleComponent({ role, content }: ChatBubbleProps) {
  const isUser = role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[32rem] rounded-xl px-4 py-2.5 text-sm whitespace-pre-wrap",
          isUser
            ? "rounded-br-[3px] bg-primary text-primary-foreground"
            : "rounded-bl-[3px] border border-border bg-card",
        )}
      >
        {role === "assistant" ? (
          <div
            className={cn(
              "whitespace-normal [&>*:first-child]:mt-0 [&>*:last-child]:mb-0",
              "[&_ul]:my-2 [&_ul]:pl-5 [&_ol]:my-2 [&_ol]:pl-5 [&_p]:my-2 [&_li+li]:mt-1",
              "[&_code]:rounded [&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[0.88em]",
              "[&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-muted [&_pre]:p-3 [&_pre_code]:bg-transparent [&_pre_code]:p-0",
            )}
          >
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        ) : (
          content
        )}
      </div>
    </div>
  );
}

export const ChatBubble = memo(ChatBubbleComponent);
