import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { makeUser, renderWithProviders, serveSession } from "./test/render";
import { server } from "./test/server";
import { RequireAuth, useAuth } from "./AuthContext";

function Protected() {
  return (
    <Routes>
      <Route path="/login" element={<p>page de connexion</p>} />
      <Route
        path="/app"
        element={
          <RequireAuth>
            <p>zone protégée</p>
          </RequireAuth>
        }
      />
    </Routes>
  );
}

describe("RequireAuth", () => {
  it("shows a spinner while the session is being checked", async () => {
    serveSession(makeUser());
    renderWithProviders(<Protected />, { route: "/app" });
    expect(screen.getByRole("status")).toHaveTextContent("Chargement...");
    expect(screen.queryByText("zone protégée")).not.toBeInTheDocument();
    expect(await screen.findByText("zone protégée")).toBeInTheDocument();
  });

  it("renders the page for a logged-in user", async () => {
    serveSession(makeUser());
    renderWithProviders(<Protected />, { route: "/app" });
    expect(await screen.findByText("zone protégée")).toBeInTheDocument();
    expect(screen.queryByText("page de connexion")).not.toBeInTheDocument();
  });

  it("redirects to /login when there is no session (401)", async () => {
    serveSession(null);
    renderWithProviders(<Protected />, { route: "/app" });
    expect(await screen.findByText("page de connexion")).toBeInTheDocument();
    expect(screen.queryByText("zone protégée")).not.toBeInTheDocument();
  });

  // Known gap (BACKLOG.md): AuthProvider has no .catch on getCurrentUser, so a 5xx or network
  // error is an unhandled rejection that ends up as a redirect to /login. Expected once fixed:
  // a "couldn't check your session" state with a retry, not the login page.
  it.todo("does not treat a server error on /auth/me as a logout");
});

function Probe() {
  const { user, logout } = useAuth();
  return (
    <>
      <p>{user ? user.full_name : "personne"}</p>
      <button onClick={() => void logout()}>sortir</button>
    </>
  );
}

describe("AuthProvider", () => {
  it("exposes the current user, and clears it on logout", async () => {
    serveSession(makeUser({ full_name: "Doc Test" }));
    let loggedOut = false;
    server.use(http.post("/api/auth/logout", () => ((loggedOut = true), new HttpResponse(null, { status: 204 }))));
    const { user } = renderWithProviders(<Probe />);
    expect(await screen.findByText("Doc Test")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "sortir" }));
    expect(await screen.findByText("personne")).toBeInTheDocument();
    expect(loggedOut).toBe(true);
  });

  it("refuses to be used outside the provider", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow("useAuth must be used within an AuthProvider");
  });
});
