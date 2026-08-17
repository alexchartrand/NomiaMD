type ChatBubbleProps = {
  role: "user" | "assistant";
  content: string;
};

export function ChatBubble({ role, content }: ChatBubbleProps) {
  return (
    <div className={`chat-bubble-row chat-bubble-row-${role}`}>
      <div className={`chat-bubble chat-bubble-${role}`}>{content}</div>
    </div>
  );
}
