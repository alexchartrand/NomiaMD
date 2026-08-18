import { TextArea } from "facturemd-frontend";

export function Empty() {
  return (
    <div style={{ width: 320 }}>
      <TextArea
        rows={5}
        placeholder="Collez la transcription de la consultation ici, ou sélectionnez un patient simulé ci-dessus..."
      />
    </div>
  );
}

export function Filled() {
  return (
    <div style={{ width: 320 }}>
      <TextArea
        rows={4}
        defaultValue={
          "Patiente se présente pour une visite de suivi de routine. Discussion de son diabète de type 2, bien contrôlé sous metformine."
        }
      />
    </div>
  );
}
