import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Banner, Button, Card, Checkbox, TextField } from "../components";
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
    <main className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-[22rem] gap-[0.4rem] p-7">
        <Link
          to="/"
          className="self-start text-sm text-muted-foreground no-underline hover:underline"
        >
          ← Retour à l&rsquo;accueil
        </Link>
        <Logo size={28} className="mb-2" />
        {error && <Banner tone="error">{error}</Banner>}
        <form onSubmit={handleSubmit} className="flex flex-col items-start gap-4">
          <div className="flex w-full flex-col gap-1.5">
            <label htmlFor="login-email" className="text-sm text-muted-foreground">
              Courriel
            </label>
            <TextField
              id="login-email"
              type="email"
              placeholder="vous@clinique.ca"
              autoFocus
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>

          <div className="flex w-full flex-col gap-1.5">
            <label htmlFor="login-password" className="text-sm text-muted-foreground">
              Mot de passe
            </label>
            <TextField
              id="login-password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>

          <label
            className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground"
            htmlFor="login-remember-me"
          >
            <Checkbox
              id="login-remember-me"
              checked={rememberMe}
              onCheckedChange={(checked) => setRememberMe(checked === true)}
            />
            Rester connecté
          </label>

          <Button type="submit" disabled={submitting} className="w-full">
            Se connecter
          </Button>
        </form>
      </Card>
    </main>
  );
}
