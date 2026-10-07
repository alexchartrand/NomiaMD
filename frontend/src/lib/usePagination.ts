import { useState } from "react";
import { paginate, PAGE_SIZE, type PageSlice } from "./paginate";

export interface Pagination<T> extends PageSlice<T> {
  setPage: (page: number) => void;
}

// A list split into pages, its page held here. `resetKey` stands for whatever narrows the
// list (a search, a period, filters): when it changes, the list goes back to its first page.
// A reload or a deleted row keeps the page (clamped to the pages left).
export function usePagination<T>(items: T[], resetKey: string, pageSize = PAGE_SIZE): Pagination<T> {
  const [state, setState] = useState({ page: 1, key: resetKey });
  const page = state.key === resetKey ? state.page : 1;
  return {
    ...paginate(items, page, pageSize),
    setPage: (next) => setState({ page: next, key: resetKey }),
  };
}
