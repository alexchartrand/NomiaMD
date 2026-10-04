import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import AppRouter from "./AppRouter";
import { makeUser, renderWithProviders, serveSession } from "./test/render";
import { server } from "./test/server";

// jsdom has no scrolling (the site layout scrolls to the top on navigation).
beforeEach(() => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
});

function serveEmptyApp() {
  server.use(
    http.get("/api/encounters", () => HttpResponse.json([])),
    http.get("/api/patients", () => HttpResponse.json([])),
    http.get("/api/claims", () => HttpResponse.json([])),
    http.get("/api/bills", () => HttpResponse.json([])),
    http.get("/api/intake/epic-sandbox", () => new HttpResponse(null, { status: 404 })),
  );
}

describe("public pages", () => {
  it.each([
    ["/", /./, "Facturation RAMQ"],
    ["/prix", "Un forfait pour chaque pratique", "Tarifs · NomiaMD"],
    ["/contact", "Parlons de votre facturation", "Contact · NomiaMD"],
    ["/securite", "La confiance avant tout", "Sécurité et confidentialité · NomiaMD"],
    ["/confidentialite", "Politique de confidentialité", "Politique de confidentialité · NomiaMD"],
  ])("%s renders its heading and sets the page title, without a session", async (route, heading, title) => {
    serveSession(null);
    renderWithProviders(<AppRouter />, { route });
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
    expect(document.title).toContain(title);
    expect(screen.getByRole("link", { name: "Connexion" })).toHaveAttribute("href", "/login");
  });

  it("the header navigates between pages", async () => {
    serveSession(null);
    const { user } = renderWithProviders(<AppRouter />, { route: "/" });
    await screen.findByRole("heading", { level: 1 });
    await user.click(within(document.body).getAllByRole("link", { name: "Tarifs" })[0]);
    expect(await screen.findByRole("heading", { level: 1, name: "Un forfait pour chaque pratique" })).toBeInTheDocument();
  });

  it("the plans' calls to action open the contact form pre-filled with the plan's subject", async () => {
    serveSession(null);
    const { user } = renderWithProviders(<AppRouter />, { route: "/prix" });
    await screen.findByRole("heading", { level: 1 });
    await user.click(screen.getAllByRole("link", { name: "Essayer gratuitement" })[0]);
    expect(await screen.findByRole("heading", { level: 1, name: "Parlons de votre facturation" })).toBeInTheDocument();
    expect(screen.getByLabelText("Sujet")).toHaveValue("essai");
  });

  it("shows the prices from the plans' source of truth", async () => {
    serveSession(null);
    renderWithProviders(<AppRouter />, { route: "/prix" });
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByRole("heading", { level: 2, name: "Gratuit" })).toBeInTheDocument();
    expect(screen.getByText("200 $")).toBeInTheDocument();
    expect(screen.getByText("Communiquez avec nous")).toBeInTheDocument();
  });
});

describe("the app area", () => {
  it.each(["/app", "/app/inbox", "/app/inbox/5", "/app/ajouter", "/app/chat", "/app/patients", "/app/facturation", "/app/profile"])(
    "%s sends a visitor without a session to the login page",
    async (route) => {
      serveSession(null);
      renderWithProviders(<AppRouter />, { route });
      expect(await screen.findByLabelText("Courriel")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Se connecter" })).toBeInTheDocument();
    },
  );

  it("/app opens the inbox for a logged-in physician, with the navigation and their name", async () => {
    serveSession(makeUser({ full_name: "Dr Test" }));
    serveEmptyApp();
    renderWithProviders(<AppRouter />, { route: "/app" });
    expect(await screen.findByRole("heading", { level: 1, name: "Rencontres" })).toBeInTheDocument();
    expect(screen.getByText("Dr Test")).toBeInTheDocument();
    const sidebar = within(screen.getByRole("complementary"));
    for (const name of ["Rencontres", "Ajouter manuellement", "Facturation", "Clavardage", "Patients", "Profil"]) {
      expect(sidebar.getByRole("link", { name })).toBeInTheDocument();
    }
  });

  it("the sidebar navigates between the app's pages", async () => {
    serveSession(makeUser());
    serveEmptyApp();
    const { user } = renderWithProviders(<AppRouter />, { route: "/app/inbox" });
    await screen.findByRole("heading", { level: 1, name: "Rencontres" });
    await user.click(screen.getByRole("link", { name: "Patients" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Patients" })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Facturation" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Facturation" })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Profil" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Profil" })).toBeInTheDocument();
  });

  it("logging out ends the session and returns to the login page", async () => {
    serveSession(makeUser());
    serveEmptyApp();
    let loggedOut = false;
    server.use(http.post("/api/auth/logout", () => ((loggedOut = true), new HttpResponse(null, { status: 204 }))));
    const { user } = renderWithProviders(<AppRouter />, { route: "/app/inbox" });
    await user.click(await screen.findByRole("button", { name: "Se déconnecter" }));
    expect(await screen.findByLabelText("Courriel")).toBeInTheDocument();
    expect(loggedOut).toBe(true);
  });

  it("logging in lands on the inbox", async () => {
    serveSession(null);
    serveEmptyApp();
    server.use(http.post("/api/auth/login", () => HttpResponse.json(makeUser({ full_name: "Dr Test" }))));
    const { user } = renderWithProviders(<AppRouter />, { route: "/login" });
    await user.type(await screen.findByLabelText("Courriel"), "doc@example.test");
    await user.type(screen.getByLabelText("Mot de passe"), "secret123");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Rencontres" })).toBeInTheDocument();
  });
});
