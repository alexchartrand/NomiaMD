import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Banner, Button, Card, TextField } from "../components";
import { Logo } from "../Logo";
import { useAuth } from "../AuthContext";
import { describeError } from "../api";

export default function Login() {
  const navigate = useNavigate();
  const { user, loading, login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user !== null) {
    return <Navigate to="/app" replace />;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password, rememberMe);
      navigate("/app");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-shell">
      <Card className="login-card">
        <Link to="/" className="login-back-link">
          ← Retour à l&rsquo;accueil
        </Link>
        <Logo size={28} className="login-logo" />
        {error && <Banner tone="error">{error}</Banner>}
        <form onSubmit={handleSubmit} className="login-form">
          <label htmlFor="login-email">Courriel</label>
          <TextField
            id="login-email"
            type="email"
            placeholder="vous@clinique.ca"
            autoFocus
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />

          <label htmlFor="login-password">Mot de passe</label>
          <TextField
            id="login-password"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          <label className="login-remember-me" htmlFor="login-remember-me">
            <input
              id="login-remember-me"
              type="checkbox"
              checked={rememberMe}
              onChange={(event) => setRememberMe(event.target.checked)}
            />
            Rester connecté
          </label>

          <Button type="submit" disabled={submitting}>
            Se connecter
          </Button>
        </form>
      </Card>
    </main>
  );
}
