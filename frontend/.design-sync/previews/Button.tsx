import { Button } from "facturemd-frontend";

export function Primary() {
  return <Button>Extraire les codes de facturation</Button>;
}

export function Secondary() {
  return <Button variant="secondary">Se connecter</Button>;
}

export function Ghost() {
  return <Button variant="ghost">Se déconnecter</Button>;
}

export function Disabled() {
  return <Button disabled>Extraction en cours...</Button>;
}
