import type { ClaimStatus } from "../../../api";

export const STATUS_LABELS: Record<ClaimStatus, string> = {
  brouillon: "Brouillon",
  soumis: "Soumis",
  facture: "Facturé",
};
