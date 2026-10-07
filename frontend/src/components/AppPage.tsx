import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDocumentTitle } from "@/site/useDocumentTitle";

const WIDTHS = {
  narrow: "max-w-[860px]",
  default: "max-w-[1120px]",
  wide: "max-w-[1500px]",
} as const;

interface AppPageProps {
  // narrow: forms and single lists · default: tables · wide: side-by-side layouts.
  width?: keyof typeof WIDTHS;
  className?: string;
  children: ReactNode;
}

// One page of the app, centered in the content column at one of three widths.
export function AppPage({ width = "default", className, children }: AppPageProps) {
  return <section className={cn("mx-auto w-full", WIDTHS[width], className)}>{children}</section>;
}

interface AppPageHeaderProps {
  title: ReactNode;
  // The browser tab's title, when `title` isn't plain text.
  documentTitle?: string;
  description?: ReactNode;
  // Buttons on the right of the title.
  actions?: ReactNode;
  // A link above the title, back to where the page was opened from.
  back?: { to: string; label: string };
  // Anything that belongs beside the title on its line (a status badge…).
  aside?: ReactNode;
  className?: string;
}

// Every app page's header: title (also the tab's), what the page is for, its main actions.
export function AppPageHeader({ title, documentTitle, description, actions, back, aside, className }: AppPageHeaderProps) {
  useDocumentTitle(documentTitle ?? (typeof title === "string" ? title : undefined));
  return (
    <header className={cn("mb-6 flex flex-col gap-2", className)}>
      {back && (
        <Link
          to={back.to}
          className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground no-underline transition-colors hover:text-primary"
        >
          <ArrowLeft aria-hidden className="size-4" />
          {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="m-0 font-heading text-[1.65rem] font-bold leading-tight tracking-tight">{title}</h1>
          {aside}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {description && <p className="m-0 max-w-2xl text-sm text-muted-foreground">{description}</p>}
    </header>
  );
}
