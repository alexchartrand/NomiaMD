// The list endpoints hard-cap a page at 200 (`le=200` on their `limit`), so a whole list is
// read page by page — none silently dropped.
export const MAX_PAGE_SIZE = 200;

export async function fetchAllPages<T>(fetchPage: (limit: number, offset: number) => Promise<T[]>): Promise<T[]> {
  const all: T[] = [];
  for (let offset = 0; ; offset += MAX_PAGE_SIZE) {
    const page = await fetchPage(MAX_PAGE_SIZE, offset);
    all.push(...page);
    if (page.length < MAX_PAGE_SIZE) return all;
  }
}
