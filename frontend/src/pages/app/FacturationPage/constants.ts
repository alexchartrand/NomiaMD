import type { BillingStatus } from "../../../api";

export const STATUS_LABELS: Record<BillingStatus, string> = {
  brouillon: "Brouillon",
  soumis: "Soumis",
  facture: "Facturé",
};
