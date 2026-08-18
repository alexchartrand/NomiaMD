import { TextField } from "facturemd-frontend";

export function Email() {
  return (
    <div style={{ width: 280 }}>
      <TextField type="email" placeholder="vous@clinique.ca" />
    </div>
  );
}

export function Password() {
  return (
    <div style={{ width: 280 }}>
      <TextField type="password" placeholder="••••••••" />
    </div>
  );
}
