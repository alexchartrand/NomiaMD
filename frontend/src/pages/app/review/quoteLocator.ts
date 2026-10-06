// Where a code's supporting quote sits in the received note, to highlight it there. The
// model quotes the note or its own summary of it, so a quote that isn't found is normal and
// shows no highlight, not an error.
export interface QuoteRange {
  start: number;
  end: number;
}

// Shorter fragments match too much of an ordinary note to point at anything.
const MIN_FRAGMENT_LENGTH = 12;

const FOLDED: Record<string, string> = {
  "’": "'",
  "‘": "'",
  "“": '"',
  "”": '"',
  "«": '"',
  "»": '"',
};

// The text lower-cased, curly quotes folded and whitespace runs collapsed to one space, with
// each folded character's offset in the original.
function fold(text: string): { folded: string; offsets: number[] } {
  let folded = "";
  const offsets: number[] = [];
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (/\s/.test(char)) {
      if (folded.endsWith(" ")) continue;
      folded += " ";
    } else {
      folded += (FOLDED[char] ?? char).toLowerCase();
    }
    offsets.push(i);
  }
  return { folded, offsets };
}

// The quote's pieces worth looking for: itself, or the longest part between the ellipses the
// model leaves when it shortens a quote, trimmed of the quote marks around it.
function fragment(quote: string): string {
  const parts = quote
    .split(/\.{3}|…|\[\.\.\.\]/)
    .map((part) => part.trim().replace(/^["'«»“”\s]+|["'«»“”\s]+$/g, ""));
  return parts.reduce((longest, part) => (part.length > longest.length ? part : longest), "");
}

export function locateQuote(note: string, quote: string): QuoteRange | null {
  const needle = fold(fragment(quote)).folded.trim();
  if (needle.length < MIN_FRAGMENT_LENGTH) return null;
  const { folded, offsets } = fold(note);
  const at = folded.indexOf(needle);
  if (at < 0) return null;
  return { start: offsets[at], end: offsets[at + needle.length - 1] + 1 };
}
