import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type SectionProps = {
  id?: string;
  // "plain" sits on the page's cream background, "raised" on white — alternated for rhythm.
  tone?: "plain" | "raised";
  className?: string;
  children: ReactNode;
};

export function Section({ id, tone = "plain", className, children }: SectionProps) {
  return (
    <section id={id} className={cn("scroll-mt-20", tone === "raised" && "border-y border-border bg-card")}>
      <div className={cn("mx-auto max-w-[1080px] px-6 py-16 min-[801px]:py-20", className)}>{children}</div>
    </section>
  );
}

type SectionHeadingProps = {
  eyebrow?: string;
  title: ReactNode;
  lead?: ReactNode;
  align?: "left" | "center";
  as?: "h1" | "h2";
};

export function SectionHeading({ eyebrow, title, lead, align = "left", as: Heading = "h2" }: SectionHeadingProps) {
  return (
    <div className={cn("mb-10 max-w-[44rem]", align === "center" && "mx-auto text-center")}>
      {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
      <Heading
        className={cn(
          "m-0 font-heading font-[620] tracking-[-0.015em] text-foreground",
          // Size before leading: tailwind-merge drops a `leading-*` that precedes a font size.
          Heading === "h1" ? "text-[clamp(2rem,4.5vw,2.75rem)]" : "text-[clamp(1.6rem,3.5vw,2.1rem)]",
          "leading-[1.15]",
        )}
      >
        {title}
      </Heading>
      {lead && <p className="mt-4 mb-0 text-[1.05rem] text-muted-foreground">{lead}</p>}
    </div>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <span className="mb-4 inline-block rounded-full bg-[color:var(--color-primary-tint)] px-3 py-1 text-[0.78rem] font-[650] tracking-[0.03em] text-primary uppercase">
      {children}
    </span>
  );
}
