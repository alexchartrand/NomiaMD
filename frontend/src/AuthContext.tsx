import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import * as api from "./api";
import { describeError, type UserOut } from "./api";
import { Banner, Button, Spinner } from "./components";

type AuthContextValue = {
  user: UserOut | null;
  loading: boolean;
  // Why the session couldn't be checked (server down, 5xx), as opposed to there being none:
  // a failed check is not a logout, so it must never look like one.
  sessionError: string | null;
  retrySession: () => void;
  login: (email: string, password: string, rememberMe: boolean) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: (updated: UserOut) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);

  const checkSession = useCallback(() => {
    setLoading(true);
    setSessionError(null);
    api
      .getCurrentUser()
      .then(setUser)
      .catch((err) => setSessionError(describeError(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(checkSession, [checkSession]);

  async function login(email: string, password: string, rememberMe: boolean) {
    const loggedInUser = await api.login(email, password, rememberMe);
    setUser(loggedInUser);
    setSessionError(null);
  }

  async function logout() {
    await api.logout();
    setUser(null);
  }

  function refreshUser(updated: UserOut) {
    setUser(updated);
  }

  return (
    <AuthContext.Provider value={{ user, loading, sessionError, retrySession: checkSession, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading, sessionError, retrySession } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Chargement..." />
      </div>
    );
  }

  if (user === null && sessionError !== null) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6">
        <Banner tone="error">{sessionError}</Banner>
        <Button type="button" onClick={retrySession}>
          Réessayer
        </Button>
      </div>
    );
  }

  if (user === null) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
