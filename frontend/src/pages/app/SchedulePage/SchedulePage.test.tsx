import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderWithProviders, serveSession, makeUser } from "../../../test/render";
import { server } from "../../../test/server";
import type { Shift, WorkSite } from "../../../api";
import { addDays, clinicToday, weekdayIndex } from "../../../utils/date";
import SchedulePage from ".";

const monday = addDays(clinicToday(), -weekdayIndex(clinicToday()));

const site: WorkSite = { id: 1, name: "Urgence Saint-Luc", care_setting: "urgence", etablissement_number: null, is_active: true };

const periods = [
  { period: "jour", label: "Jour", start_time: "08:00:00", end_time: "16:00:00" },
  { period: "soir", label: "Soir", start_time: "16:00:00", end_time: "00:00:00" },
  { period: "nuit", label: "Nuit", start_time: "00:00:00", end_time: "08:00:00" },
];

function makeShift(overrides: Partial<Shift> = {}): Shift {
  return {
    id: 10,
    series_id: null,
    work_site_id: 1,
    work_site_name: "Urgence Saint-Luc",
    care_setting: "urgence",
    period: "soir",
    service_date: monday,
    start_time: "16:00:00",
    end_time: "00:00:00",
    ends_next_day: true,
    day_type: "semaine",
    ...overrides,
  };
}

function serveSchedule({ sites = [site], shifts = [] as Shift[] } = {}) {
  const queries: URLSearchParams[] = [];
  server.use(
    http.get("/api/work-sites", () => HttpResponse.json(sites)),
    http.get("/api/shifts/periods", () => HttpResponse.json(periods)),
    http.get("/api/shifts", ({ request }) => {
      queries.push(new URL(request.url).searchParams);
      return HttpResponse.json(shifts);
    }),
  );
  return queries;
}

function renderSchedule() {
  serveSession(makeUser());
  return renderWithProviders(<SchedulePage />);
}

describe("schedule", () => {
  it("shows the week's shifts on their day", async () => {
    const queries = serveSchedule({ shifts: [makeShift()] });
    renderSchedule();
    const day = await screen.findByRole("listitem", { name: monday });
    expect(await within(day).findByText("Urgence Saint-Luc")).toBeInTheDocument();
    expect(within(day).getByText("Urgence · Soir")).toBeInTheDocument();
    expect(queries[0].get("start")).toBe(monday);
    expect(queries[0].get("end")).toBe(addDays(monday, 6));
  });

  it("loads the next week", async () => {
    const queries = serveSchedule();
    const { user } = renderSchedule();
    await screen.findByRole("listitem", { name: monday });
    await user.click(screen.getByRole("button", { name: "Semaine suivante" }));
    await screen.findByRole("listitem", { name: addDays(monday, 7) });
    expect(queries[queries.length - 1].get("start")).toBe(addDays(monday, 7));
  });

  it("sends to the profile when there is no work site yet", async () => {
    serveSchedule({ sites: [] });
    renderSchedule();
    expect(await screen.findByText("Aucun lieu de travail")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ajouter un quart" })).not.toBeInTheDocument();
  });

  it("adds a shift, the period filling in its usual hours", async () => {
    serveSchedule();
    const bodies: unknown[] = [];
    server.use(
      http.post("/api/shifts", async ({ request }) => {
        const body = (await request.json()) as Partial<Shift>;
        bodies.push(body);
        return HttpResponse.json(makeShift(body), { status: 201 });
      }),
    );
    const { user } = renderSchedule();
    await user.click(await screen.findByRole("button", { name: `Ajouter un quart le ${monday}` }));
    await user.click(screen.getByRole("button", { name: "Nuit" }));
    expect(screen.getByLabelText("Début")).toHaveValue("00:00");
    expect(screen.getByLabelText("Fin")).toHaveValue("08:00");
    await user.click(screen.getByRole("button", { name: "Soir" }));
    expect(screen.getByText("Le lendemain.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(await screen.findByText("Horaire mis à jour.")).toBeInTheDocument();
    expect(bodies).toEqual([
      { work_site_id: 1, period: "soir", service_date: monday, start_time: "16:00", end_time: "00:00" },
    ]);
  });

  it("adds one shift a day over a date range, weekdays only", async () => {
    serveSchedule();
    const bodies: unknown[] = [];
    server.use(
      http.post("/api/shifts/series", async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json([], { status: 201 });
      }),
    );
    const { user } = renderSchedule();
    await user.click(await screen.findByRole("button", { name: `Ajouter un quart le ${monday}` }));
    const last = screen.getByLabelText("Au");
    await user.clear(last);
    await user.type(last, addDays(monday, 13));
    expect(screen.getByText("14 quarts, un par jour.")).toBeInTheDocument();
    await user.click(screen.getByLabelText("Jours de semaine seulement"));
    expect(screen.getByText("10 quarts, un par jour.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Enregistrer 10 quarts" }));

    expect(await screen.findByText("Horaire mis à jour.")).toBeInTheDocument();
    expect(bodies).toEqual([
      {
        work_site_id: 1,
        period: "jour",
        start_time: "08:00",
        end_time: "16:00",
        start_date: monday,
        end_date: addDays(monday, 13),
        weekdays_only: true,
      },
    ]);
  });

  it("edits a series' shifts from this one on", async () => {
    serveSchedule({ shifts: [makeShift({ id: 11, series_id: 4, period: "jour", start_time: "08:00:00", end_time: "16:00:00", ends_next_day: false })] });
    const bodies: unknown[] = [];
    server.use(
      http.put("/api/shifts/series/4", async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json([]);
      }),
    );
    const { user } = renderSchedule();
    await user.click(await screen.findByRole("button", { name: /08:00–16:00/ }));
    await user.click(screen.getByRole("button", { name: "Ce quart et les suivants" }));
    expect(screen.queryByLabelText("Date")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Soir" }));
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(await screen.findByText("Horaire mis à jour.")).toBeInTheDocument();
    expect(bodies).toEqual([{ work_site_id: 1, period: "soir", start_time: "16:00", end_time: "00:00", from_date: monday }]);
  });

  it("deletes a whole series after confirming", async () => {
    serveSchedule({ shifts: [makeShift({ series_id: 4 })] });
    const deleted: string[] = [];
    server.use(
      http.delete("/api/shifts/series/4", ({ request }) => {
        deleted.push(request.url);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderSchedule();
    await user.click(await screen.findByRole("button", { name: /16:00–00:00/ }));
    await user.click(screen.getByRole("button", { name: "Toute la série" }));
    await user.click(screen.getByRole("button", { name: "Supprimer" }));
    const confirmDialog = (await screen.findByText("Supprimer toute la série ?")).closest("[role=dialog],[role=alertdialog]");
    await user.click(within(confirmDialog as HTMLElement).getByRole("button", { name: "Supprimer" }));

    expect(await screen.findByText("Quarts supprimés.")).toBeInTheDocument();
    expect(deleted).toHaveLength(1);
    expect(new URL(deleted[0]).search).toBe("");
  });
});
