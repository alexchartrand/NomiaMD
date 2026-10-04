import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import type { UserOut } from "../api";
import { AuthProvider } from "../AuthContext";
import { server } from "./server";

export function makeUser(overrides: Partial<UserOut> = {}): UserOut {
  return {
    id: 1,
    email: "doc@example.test",
    full_name: "Doc Test",
    role: "physician",
    physician_type: "med_fam",
    panel_size: null,
    remuneration_type: null,
    practice_number: null,
    ...overrides,
  };
}

// What GET /auth/me answers: a user (logged in), or null (401, logged out).
export function serveSession(user: UserOut | null) {
  server.use(
    http.get("/api/auth/me", () =>
      user ? HttpResponse.json(user) : HttpResponse.json({ detail: "Non authentifié" }, { status: 401 }),
    ),
  );
}

// `ui` is usually a <Routes> tree (or one page) rendered at `route`, inside the real
// AuthProvider — so session handling is exercised, not mocked.
export function renderWithProviders(ui: ReactElement, { route = "/", state }: { route?: string; state?: unknown } = {}) {
  return {
    user: userEvent.setup(),
    ...render(
      <MemoryRouter initialEntries={[{ pathname: route.split("?")[0], search: route.includes("?") ? `?${route.split("?")[1]}` : "", state }]}>
        <AuthProvider>{ui}</AuthProvider>
      </MemoryRouter>,
    ),
  };
}
