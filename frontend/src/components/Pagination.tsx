import type { RefObject } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { GAP, pageWindow } from "../lib/paginate";
import { Button } from "./Button";

interface PaginationProps {
  page: number;
  pageCount: number;
  first: number;
  last: number;
  total: number;
  onChange: (page: number) => void;
  // The list's top, brought back into view on a page change: the buttons sit under the
  // list, so the next page would otherwise open on its last rows.
  listRef?: RefObject<HTMLElement | null>;
  className?: string;
}

// Under a list too long to show at once: where you are in it, and its pages. Nothing when
// the whole list fits on one page.
export function Pagination({ page, pageCount, first, last, total, onChange, listRef, className }: PaginationProps) {
  if (pageCount <= 1) return null;

  function go(next: number) {
    onChange(next);
    listRef?.current?.scrollIntoView?.({ block: "nearest" });
  }

  return (
    <nav aria-label="Pagination" className={cn("flex flex-wrap items-center justify-between gap-2 text-sm", className)}>
      <span className="text-muted-foreground tabular-nums">
        {first}–{last} sur {total}
      </span>
      <div className="flex items-center gap-1">
        <Button type="button" variant="ghost" size="icon-sm" aria-label="Page précédente" disabled={page <= 1} onClick={() => go(page - 1)}>
          <ChevronLeft aria-hidden />
        </Button>
        {pageWindow(page, pageCount).map((n, i) =>
          n === GAP ? (
            <span key={`gap-${i}`} aria-hidden className="w-7 text-center text-muted-foreground">
              {GAP}
            </span>
          ) : (
            <Button
              key={n}
              type="button"
              variant={n === page ? "secondary" : "ghost"}
              size="icon-sm"
              aria-label={`Page ${n}`}
              aria-current={n === page ? "page" : undefined}
              className="tabular-nums"
              onClick={() => n !== page && go(n)}
            >
              {n}
            </Button>
          ),
        )}
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Page suivante"
          disabled={page >= pageCount}
          onClick={() => go(page + 1)}
        >
          <ChevronRight aria-hidden />
        </Button>
      </div>
    </nav>
  );
}
