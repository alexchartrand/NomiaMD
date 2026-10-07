// The most rows a list shows at once; past that, it's split into pages.
export const PAGE_SIZE = 50;

export interface PageSlice<T> {
  items: T[];
  // 1-based, clamped to the pages there are: a list that shrank (a row deleted, a reload)
  // never leaves you on an empty page past its end.
  page: number;
  pageCount: number;
  // 1-based positions of the page's first and last items, and the list's length.
  first: number;
  last: number;
  total: number;
}

export function paginate<T>(items: T[], page: number, pageSize = PAGE_SIZE): PageSlice<T> {
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const current = Math.min(Math.max(1, Math.floor(page) || 1), pageCount);
  const start = (current - 1) * pageSize;
  const pageItems = items.slice(start, start + pageSize);
  return {
    items: pageItems,
    page: current,
    pageCount,
    first: pageItems.length > 0 ? start + 1 : 0,
    last: start + pageItems.length,
    total: items.length,
  };
}

export const GAP = "…";

// The page buttons to show: the first and last pages, and the ones around the current
// page, with a gap where pages are skipped. A gap never stands for a single page — that
// page is shown instead.
export function pageWindow(page: number, pageCount: number, around = 1): (number | typeof GAP)[] {
  const shown = new Set([1, pageCount]);
  for (let n = page - around; n <= page + around; n++) if (n >= 1 && n <= pageCount) shown.add(n);
  const sorted = [...shown].sort((a, b) => a - b);
  const buttons: (number | typeof GAP)[] = [];
  let previous: number | null = null;
  for (const n of sorted) {
    if (previous !== null && n - previous === 2) buttons.push(n - 1);
    else if (previous !== null && n - previous > 2) buttons.push(GAP);
    buttons.push(n);
    previous = n;
  }
  return buttons;
}
