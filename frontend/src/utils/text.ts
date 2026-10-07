// Accents and case don't matter: "fred" finds "Frédéric".
export function fold(text: string): string {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}
