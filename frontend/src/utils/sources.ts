// What a note's `source_system` reads as in the app; an unknown one shows as is.
const SOURCE_LABELS: Record<string, string> = {
  simule: "Note simulée",
  manual: "Saisie manuelle",
  epic_sandbox: "Epic (démo)",
  epic: "Epic",
};

export function sourceLabel(sourceSystem: string | null | undefined): string {
  if (!sourceSystem) return "—";
  return SOURCE_LABELS[sourceSystem] ?? sourceSystem;
}
