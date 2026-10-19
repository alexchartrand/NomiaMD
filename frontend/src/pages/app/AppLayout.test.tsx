import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { makeDashboard } from "../../test/factories";
import { makeUser, renderWithProviders, serveSession } from "../../test/render";
import { server } from "../../test/server";
import AppLayout from "./AppLayout";

function renderLayout() {
  server.use(http.get("/api/dashboard", () => HttpResponse.json(makeDashboard())));
  return renderWithProviders(
    <Routes>
      <Route path="/app" element={<AppLayout />}>
        <Route index element={<p>accueil</p>} />
      </Route>
    </Routes>,
    { route: "/app" },
  );
}

describe("the app's sidebar", () => {
  it("links admins to the console", async () => {
    serveSession(makeUser({ role: "admin" }));
    renderLayout();
    expect(await screen.findByRole("link", { name: /Console/ })).toHaveAttribute("href", "/app/admin");
  });

  it("shows physicians no console", async () => {
    serveSession(makeUser({ role: "physician" }));
    renderLayout();
    // The session is loaded once the user menu shows who's signed in.
    await screen.findByText("Doc Test");
    expect(screen.queryByRole("link", { name: /Console/ })).not.toBeInTheDocument();
  });
});
