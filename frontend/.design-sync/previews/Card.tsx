import { Button, Card, TextField } from "facturemd-frontend";

export function Text() {
  return (
    <Card style={{ maxWidth: 320 }}>
      <p style={{ margin: 0 }}>
        Version d&rsquo;aperçu — connectez-vous avec n&rsquo;importe quelles informations pour
        continuer.
      </p>
    </Card>
  );
}

export function WithForm() {
  return (
    <Card style={{ maxWidth: 280, display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      <label htmlFor="ds-card-email" style={{ fontSize: "0.9rem" }}>
        Courriel
      </label>
      <TextField id="ds-card-email" type="email" placeholder="vous@clinique.ca" />
      <Button style={{ marginTop: "0.75rem" }}>Se connecter</Button>
    </Card>
  );
}
