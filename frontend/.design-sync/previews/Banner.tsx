import { Banner } from "facturemd-frontend";

export function ErrorTone() {
  return (
    <Banner tone="error">
      Impossible de charger la liste des patients : Internal Server Error
    </Banner>
  );
}

export function WarningTone() {
  return (
    <Banner tone="warning">
      ⚠ Le code 15818 nécessite une confirmation du statut vulnérable du patient.
    </Banner>
  );
}
