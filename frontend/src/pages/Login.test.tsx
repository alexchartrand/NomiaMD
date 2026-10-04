import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { makeUser, renderWithProviders, serveSession } from "../test/render";
import { server } from "../test/server";
import Login from "./Login";

function Pages() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/app" element={<p>tableau de bord</p>} />
      <Route path="/" element={<p>accueil</p>} />
    </Routes>
  );
}

async function fillAndSubmit(user: ReturnType<typeof renderWithProviders>["user"], remember = false) {
  await user.type(await screen.findByLabelText("Courriel"), "doc@example.test");
  await user.type(screen.getByLabelText("Mot de passe"), "secret123");
  if (remember) await user.click(screen.getByLabelText("Rester connecté"));
  await user.click(screen.getByRole("button", { name: "Se connecter" }));
}

describe("Login", () => {
  it("posts the credentials and goes to /app", async () => {
    serveSession(null);
    let body: unknown;
    server.use(
      http.post("/api/auth/login", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(makeUser());
      }),
    );
    const { user } = renderWithProviders(<Pages />, { route: "/login" });
    await fillAndSubmit(user, true);
    expect(await screen.findByText("tableau de bord")).toBeInTheDocument();
    expect(body).toEqual({ email: "doc@example.test", password: "secret123", remember_me: true });
  });

  it("sends remember_me=false by default", async () => {
    serveSession(null);
    let body: { remember_me?: boolean } = {};
    server.use(
      http.post("/api/auth/login", async ({ request }) => {
        body = (await request.json()) as typeof body;
        return HttpResponse.json(makeUser());
      }),
    );
    const { user } = renderWithProviders(<Pages />, { route: "/login" });
    await fillAndSubmit(user);
    await screen.findByText("tableau de bord");
    expect(body.remember_me).toBe(false);
  });

  it("shows the server's message on bad credentials and stays on the page", async () => {
    serveSession(null);
    server.use(http.post("/api/auth/login", () => HttpResponse.json({ detail: "Identifiants invalides" }, { status: 401 })));
    const { user } = renderWithProviders(<Pages />, { route: "/login" });
    await fillAndSubmit(user);
    expect(await screen.findByText("Identifiants invalides")).toBeInTheDocument();
    expect(screen.queryByText("tableau de bord")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Se connecter" })).toBeEnabled();
  });

  it("explains an unreachable server", async () => {
    serveSession(null);
    server.use(http.post("/api/auth/login", () => HttpResponse.error()));
    const { user } = renderWithProviders(<Pages />, { route: "/login" });
    await fillAndSubmit(user);
    expect(await screen.findByText(/Impossible de joindre le serveur/)).toBeInTheDocument();
  });

  it("clears the previous error on a new attempt", async () => {
    serveSession(null);
    let attempts = 0;
    server.use(
      http.post("/api/auth/login", () =>
        ++attempts === 1 ? HttpResponse.json({ detail: "Identifiants invalides" }, { status: 401 }) : HttpResponse.json(makeUser()),
      ),
    );
    const { user } = renderWithProviders(<Pages />, { route: "/login" });
    await fillAndSubmit(user);
    await screen.findByText("Identifiants invalides");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    await waitFor(() => expect(screen.queryByText("Identifiants invalides")).not.toBeInTheDocument());
    expect(await screen.findByText("tableau de bord")).toBeInTheDocument();
  });

  it("sends an already logged-in user straight to /app", async () => {
    serveSession(makeUser());
    renderWithProviders(<Pages />, { route: "/login" });
    expect(await screen.findByText("tableau de bord")).toBeInTheDocument();
  });

  it("links back to the home page", async () => {
    serveSession(null);
    const { user } = renderWithProviders(<Pages />, { route: "/login" });
    await user.click(await screen.findByRole("link", { name: /Retour à l.accueil/ }));
    expect(await screen.findByText("accueil")).toBeInTheDocument();
  });
});
