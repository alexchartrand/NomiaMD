import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes, useLocation } from "react-router-dom";
import type { Dashboard } from "../../../api";
import { makeDashboard, makeEncounterRow } from "../../../test/factories";
import { makeUser, renderWithProviders, serveSession } from "../../../test/render";
import { server } from "../../../test/server";
import DashboardPage from ".";

beforeEach(() => serveSession(makeUser({ full_name: "Dr Test" })));

function serveDashboard(dashboard: Dashboard | (() => Dashboard)) {
  let calls = 0;
  server.use(
    http.get("/api/dashboard", () => {
      calls += 1;
      return HttpResponse.json(typeof dashboard === "function" ? dashboard() : dashboard);
    }),
  );
  return () => calls;
}

function Landed() {
  const location = useLocation();
  return <p data-testid="landed">{decodeURIComponent(location.pathname + location.search)}</p>;
}

function renderDashboard() {
  return renderWithProviders(
    <Routes>
      <Route path="/app" element={<DashboardPage />} />
      <Route path="*" element={<Landed />} />
    </Routes>,
    { route: "/app" },
  );
}

const panel = (name: string) => within(screen.getByRole("region", { name }));

describe("the dashboard", () => {
  it("greets the physician with the clinic's date and the headline figures", async () => {
    serveDashboard(
      makeDashboard({
        tasks: { to_do: 7 },
        kpis: { encounters_this_week: 23, draft_count: 3, draft_total: 412.5, billed_this_month: 3120 },
      }),
    );
    renderDashboard();
    expect(await screen.findByText("lundi 5 octobre 2026")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Bonjour, Dr Test" })).toBeInTheDocument();
    expect(screen.getByText("Notes à traiter").nextSibling).toHaveTextContent("7");
    expect(screen.getByText("Rencontres cette semaine").nextSibling).toHaveTextContent("23");
    expect(screen.getByText("412,50 $").nextSibling).toHaveTextContent("3 réclamations à facturer");
    expect(screen.getByText("Facturé en octobre").nextSibling).toHaveTextContent("3 120,00 $");
  });

  it("lists each kind of task, linking to the inbox filtered on it", async () => {
    serveDashboard(
      makeDashboard({
        tasks: { to_review: 4, approvable: 2, to_associate: 1, failed: 1, possible_duplicates: 2 },
        kpis: { draft_count: 1, draft_total: 33.15 },
      }),
    );
    const { user } = renderDashboard();
    const tasks = await screen.findByRole("region", { name: "À faire" });
    const link = (name: RegExp) => within(tasks).getByRole("link", { name });

    expect(link(/4 notes à réviser/)).toHaveTextContent("2 approuvables en lot");
    expect(link(/1 note à associer à un patient/)).toBeInTheDocument();
    expect(link(/1 extraction en échec/)).toBeInTheDocument();
    expect(link(/2 doublons possibles à confirmer/)).toBeInTheDocument();
    expect(link(/1 réclamation à facturer/)).toHaveTextContent("33,15 $");
    expect(within(tasks).queryByText(/en attente d'extraction/)).not.toBeInTheDocument();

    await user.click(link(/1 note à associer/));
    // "+" is the query string's space: the inbox's useSearchParams reads "à associer".
    expect(await screen.findByTestId("landed")).toHaveTextContent("/app/inbox?all=1&status=à+associer");
  });

  it("says when there's nothing left to do", async () => {
    serveDashboard(makeDashboard());
    renderDashboard();
    expect(await screen.findByText("Rien à faire — tout est à jour.")).toBeInTheDocument();
    expect(screen.getByText("Aucune rencontre ces 8 dernières semaines.")).toBeInTheDocument();
    expect(screen.getByText("Aucune rencontre reçue pour l'instant.")).toBeInTheDocument();
  });

  it("warns about work close to the RAMQ deadline, most urgent first", async () => {
    serveDashboard(
      makeDashboard({
        deadlines: [
          { kind: "encounter", id: 11, patient_display: "Roch D.", service_date: "2026-07-01", days_left: -5 },
          { kind: "claim", id: 4, patient_display: "Marie T.", service_date: "2026-07-07", days_left: 0 },
          { kind: "encounter", id: 12, patient_display: null, service_date: "2026-07-17", days_left: 10 },
        ],
      }),
    );
    const { user } = renderDashboard();
    await screen.findByText("Délai de facturation RAMQ (90 jours)");
    const items = panel("À faire").getAllByRole("link");

    expect(items[0]).toHaveTextContent("Roch D.Note du 01/07/2026Délai dépassé de 5 j");
    expect(items[1]).toHaveTextContent("Marie T.Réclamation du 07/07/2026Dernier jour");
    expect(items[2]).toHaveTextContent("Patient à associerNote du 17/07/2026" + "10 j restants");
    expect(items[1]).toHaveAttribute("href", "/app/facturation");

    await user.click(items[0]);
    expect(await screen.findByTestId("landed")).toHaveTextContent("/app/inbox/11");
  });

  it("shows the latest encounters, each opening its review page", async () => {
    serveDashboard(
      makeDashboard({
        recent_encounters: [
          makeEncounterRow({ id: 8, status: "revu", patient: { id: 1, display_name: "Roch D.", nam: null } }),
          makeEncounterRow({ id: 7, status: "à associer", patient: null, service_date: null, received_at: "2026-10-05T02:00:00Z" }),
        ],
      }),
    );
    renderDashboard();
    await screen.findByRole("region", { name: "Dernières rencontres" });
    const rows = panel("Dernières rencontres").getAllByRole("link").filter((a) => a.textContent !== "Tout voir");

    expect(rows[0]).toHaveTextContent("01/10/2026Roch D.Revu");
    expect(rows[0]).toHaveAttribute("href", "/app/inbox/8");
    // Undated: the clinic day it was received (02:00 UTC is still the 4th in Montréal).
    expect(rows[1]).toHaveTextContent("04/10/2026Patient à associerÀ associer");
  });

  it("charts the weeks' encounters, with an accessible table of the same figures", async () => {
    const dashboard = makeDashboard();
    dashboard.weekly_activity[7] = { week_start: "2026-10-05", received: 5, reviewed: 3 };
    serveDashboard(dashboard);
    renderDashboard();
    expect(
      await screen.findByLabelText("Semaine du 5 oct. : 5 rencontres, 3 revues"),
    ).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Rencontres par semaine" });
    const rows = within(table).getAllByRole("row");
    expect(rows[rows.length - 1]).toHaveTextContent("5 oct.53");
  });

  it("shows the error when the summary can't be loaded", async () => {
    server.use(http.get("/api/dashboard", () => HttpResponse.json({ detail: "Erreur serveur" }, { status: 500 })));
    renderDashboard();
    expect(await screen.findByText(/Erreur serveur/)).toBeInTheDocument();
  });

  describe("polling", () => {
    beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
    afterEach(() => vi.useRealTimers());

    it("re-reads the summary while a note is still being extracted", async () => {
      let extracting = 1;
      const calls = serveDashboard(() => makeDashboard({ tasks: { extracting, to_do: extracting } }));
      renderDashboard();
      expect(await screen.findByText("1 note en attente d'extraction")).toBeInTheDocument();

      extracting = 0;
      await vi.advanceTimersByTimeAsync(15_000);
      expect(await screen.findByText("Rien à faire — tout est à jour.")).toBeInTheDocument();
      const after = calls();
      await vi.advanceTimersByTimeAsync(30_000);
      expect(calls()).toBe(after);
    });
  });
});
