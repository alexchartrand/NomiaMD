import type { ReactNode } from "react";

// A titled block of running text, for the long-form pages (security, privacy policy).
export function ProseSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="max-w-[760px] border-t border-border py-8 first:border-t-0 first:pt-0">
      <h2 className="mb-3 font-heading font-[620] text-[1.3rem] text-foreground">{title}</h2>
      <div className="flex flex-col gap-3 text-[0.98rem] text-muted-foreground [&_li]:ml-5 [&_li]:list-disc [&_strong]:text-foreground [&_ul]:m-0 [&_ul]:flex [&_ul]:flex-col [&_ul]:gap-1.5 [&_ul]:p-0">
        {children}
      </div>
    </section>
  );
}
