import { fetchAllPages, MAX_PAGE_SIZE } from "./paging";

describe("fetchAllPages", () => {
  it("reads page after page until one comes back short", async () => {
    const items = Array.from({ length: MAX_PAGE_SIZE + 1 }, (_, i) => i);
    const fetchPage = vi.fn(async (limit: number, offset: number) => items.slice(offset, offset + limit));
    expect(await fetchAllPages(fetchPage)).toEqual(items);
    expect(fetchPage.mock.calls).toEqual([
      [MAX_PAGE_SIZE, 0],
      [MAX_PAGE_SIZE, MAX_PAGE_SIZE],
    ]);
  });

  it("asks once more after an exactly full page", async () => {
    const fetchPage = vi.fn(async (_limit: number, offset: number) => (offset === 0 ? Array(MAX_PAGE_SIZE).fill(0) : []));
    expect(await fetchAllPages(fetchPage)).toHaveLength(MAX_PAGE_SIZE);
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });
});
