import { locateQuote } from "./quoteLocator";

const note = "Motif : toux depuis 3 jours.\nExamen :   pharynx érythémateux, l’auscultation est normale.";
const quoted = (quote: string) => {
  const range = locateQuote(note, quote);
  return range && note.slice(range.start, range.end);
};

describe("locateQuote", () => {
  it("finds a verbatim quote", () => {
    expect(quoted("toux depuis 3 jours")).toBe("toux depuis 3 jours");
  });

  it("ignores case, curly apostrophes and line breaks or repeated spaces", () => {
    expect(quoted("JOURS. Examen : pharynx")).toBe("jours.\nExamen :   pharynx");
    expect(quoted("l'auscultation est normale")).toBe("l’auscultation est normale");
  });

  it("strips the quote marks around the quote", () => {
    expect(quoted("« pharynx érythémateux »")).toBe("pharynx érythémateux");
  });

  it("matches the longest part of a quote the model shortened with an ellipsis", () => {
    expect(quoted("toux … l’auscultation est normale")).toBe("l’auscultation est normale");
  });

  it("is null when the quote isn't in the note, e.g. it came from the summary", () => {
    expect(locateQuote(note, "Patient de 45 ans avec une toux")).toBeNull();
  });

  it("is null for a fragment too short to point at anything", () => {
    expect(locateQuote(note, "toux")).toBeNull();
    expect(locateQuote(note, "")).toBeNull();
  });
});
