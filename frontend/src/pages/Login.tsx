import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, TextField } from "../components";
import { Logo } from "../Logo";

export default function Login() {
  const navigate = useNavigate();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    navigate("/app");
  }

  return (
    <main className="login-shell">
      <Card className="login-card">
        <Logo size={28} className="login-logo" />
        <p className="login-subtext">
          Version d&rsquo;aperçu — connectez-vous avec n&rsquo;importe quelles informations
          pour continuer.
        </p>
        <form onSubmit={handleSubmit} className="login-form">
          <label htmlFor="login-email">Courriel</label>
          <TextField id="login-email" type="email" placeholder="vous@clinique.ca" autoFocus />

          <label htmlFor="login-password">Mot de passe</label>
          <TextField id="login-password" type="password" placeholder="••••••••" />

          <Button type="submit">Se connecter</Button>
        </form>
      </Card>
    </main>
  );
}
