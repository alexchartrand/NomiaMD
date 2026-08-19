import { memo } from "react";
import ReactMarkdown from "react-markdown";

type ChatBubbleProps = {
  role: "user" | "assistant";
  content: string;
};

function ChatBubbleComponent({ role, content }: ChatBubbleProps) {
  return (
    <div className={`chat-bubble-row chat-bubble-row-${role}`}>
      <div className={`chat-bubble chat-bubble-${role}`}>
        {role === "assistant" ? (
          <div className="chat-bubble-markdown">
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
