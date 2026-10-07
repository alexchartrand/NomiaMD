import { GAP, pageWindow, paginate } from "./paginate";

const items = Array.from({ length: 23 }, (_, i) => i + 1);

describe("paginate", () => {
  it("slices the requested page and says where it sits in the list", () => {
    expect(paginate(items, 2, 10)).toEqual({
      items: [11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
      page: 2,
      pageCount: 3,
      first: 11,
      last: 20,
      total: 23,
    });
    expect(paginate(items, 3, 10)).toMatchObject({ items: [21, 22, 23], first: 21, last: 23 });
  });

  it("clamps a page past the end (a list that shrank) or below the first", () => {
    expect(paginate(items, 9, 10)).toMatchObject({ page: 3, first: 21 });
    expect(paginate(items, 0, 10)).toMatchObject({ page: 1, first: 1 });
    expect(paginate(items, Number.NaN, 10)).toMatchObject({ page: 1 });
  });

  it("is a single empty page for an empty list", () => {
    expect(paginate([], 4, 10)).toEqual({ items: [], page: 1, pageCount: 1, first: 0, last: 0, total: 0 });
  });
});

describe("pageWindow", () => {
  it("shows every page when there are few", () => {
    expect(pageWindow(1, 1)).toEqual([1]);
    expect(pageWindow(2, 5)).toEqual([1, 2, 3, 4, 5]);
  });

  it("keeps the ends and the current page's neighbours, with gaps between", () => {
    expect(pageWindow(1, 10)).toEqual([1, 2, GAP, 10]);
    expect(pageWindow(6, 10)).toEqual([1, GAP, 5, 6, 7, GAP, 10]);
    expect(pageWindow(10, 10)).toEqual([1, GAP, 9, 10]);
  });

  it("shows a lone skipped page rather than a gap for it", () => {
    expect(pageWindow(4, 10)).toEqual([1, 2, 3, 4, 5, GAP, 10]);
  });
});
