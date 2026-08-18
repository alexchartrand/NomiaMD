import { Select } from "facturemd-frontend";

export function Default() {
  return (
    <div style={{ width: 280 }}>
      <Select defaultValue="">
        <option value="">Sélectionnez un patient...</option>
        <option value="p1">Patiente, 34 ans — suivi diabète</option>
        <option value="p2">Patient, 58 ans — douleur thoracique</option>
      </Select>
    </div>
  );
}

export function Disabled() {
  return (
    <div style={{ width: 280 }}>
      <Select disabled defaultValue="">
        <option value="">Aucun patient simulé disponible</option>
      </Select>
    </div>
  );
}
