import { useEffect } from "react";
import { SITE } from "./config";

export function useDocumentTitle(title?: string) {
  useEffect(() => {
    document.title = title ? `${title} · ${SITE.name}` : `${SITE.name} — Facturation RAMQ simplifiée par l'IA`;
  }, [title]);
}
