import type { ReactNode } from "react";
import { Accordion } from "radix-ui";
import { ChevronDownIcon } from "lucide-react";

export type FaqItem = { question: string; answer: ReactNode };

export function FaqList({ items }: { items: FaqItem[] }) {
  return (
    <Accordion.Root type="multiple" className="divide-y divide-border rounded-2xl border border-border bg-card">
      {items.map((item) => (
        <Accordion.Item key={item.question} value={item.question}>
          <Accordion.Header className="m-0">
            <Accordion.Trigger className="group flex w-full cursor-pointer items-center justify-between gap-4 bg-transparent px-5 py-4 text-left font-heading text-[1rem] font-[600] text-foreground hover:text-primary">
              {item.question}
              <ChevronDownIcon
                className="size-5 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
                aria-hidden="true"
              />
            </Accordion.Trigger>
          </Accordion.Header>
          <Accordion.Content className="px-5 pb-5 text-[0.95rem] text-muted-foreground">{item.answer}</Accordion.Content>
        </Accordion.Item>
      ))}
    </Accordion.Root>
  );
}
