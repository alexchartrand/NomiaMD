import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import * as api from "./api";
import type { UserOut } from "./api";
import { Spinner } from "./components";

type AuthContextValue = {
  user: UserOut | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: (updated: UserOut) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getCurrentUser()
      .then(setUser)
      .finally(() => setLoading(false));
  }, []);

  async function login(email: string, password: string) {
    const loggedInUser = await api.login(email, password);
    setUser(loggedInUser);
  }

  async function logout() {
    await api.logout();
    setUser(null);
  }

  function refreshUser(updated: UserOut) {
    setUser(updated);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
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
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="auth-loading">
        <Spinner label="Chargement..." />
      </div>
    );
  }

  if (user === null) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
