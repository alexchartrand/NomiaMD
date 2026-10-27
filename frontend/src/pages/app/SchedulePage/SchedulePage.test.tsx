import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderWithProviders, serveSession, makeUser } from "../../../test/render";
import { server } from "../../../test/server";
import type { Shift, ShiftBilling, WorkSite } from "../../../api";
import { makeEncounterRow, makeEncounterSetting, makeShiftClaim } from "../../../test/factories";
import { addDays, clinicToday, weekdayIndex } from "../../../utils/date";
import SchedulePage from ".";

const today = clinicToday();
const monday = addDays(today, -weekdayIndex(today));
const firstOfMonth = `${today.slice(0, 7)}-01`;
const gridStart = addDays(firstOfMonth, -weekdayIndex(firstOfMonth));
const nextMonth = `${addDays(firstOfMonth, 31).slice(0, 7)}-01`;
const lastOfMonth = addDays(nextMonth, -1);
const gridEnd = addDays(lastOfMonth, 6 - weekdayIndex(lastOfMonth));

// The view picked is remembered in localStorage; each test starts on the default (month).
beforeEach(() => localStorage.clear());

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
    // An opened shift: no shift code, no encounter, unless a test says otherwise.
    http.get("/api/shifts/:id/billing", ({ params }) =>
      HttpResponse.json({
        shift: shifts.find((s) => s.id === Number(params.id)),
        garde_option: "acte",
        garde_choices: [],
        suggested: [],
        available_codes: [],
        claim: null,
      }),
    ),
    http.get("/api/encounters", () => HttpResponse.json([])),
  );
  return queries;
}

const code09791 = {
  code: "09791",
  description: "Supplément de garde au service d'urgence — de 20 h à 24 h, du lundi au vendredi",
  quart_hours: 4,
  divisible_in_hours: true,
  hourly_fee: 39.1,
  secteur_dispensation: "07",
  secteur_dispensation_label: "Service d'urgence",
  source: "P.G. 2.2.9 B, p. 71 (manuel 2026-06-05)",
};
const code19953 = { ...code09791, code: "19953", description: "Supplément de garde — fin de semaine ou jour férié" };

function renderSchedule() {
  serveSession(makeUser());
  return renderWithProviders(<SchedulePage />);
}

describe("schedule", () => {
  it("shows the month by default, the shifts on their day", async () => {
    const queries = serveSchedule({ shifts: [makeShift()] });
    renderSchedule();
    const day = await screen.findByRole("listitem", { name: monday });
    expect(await within(day).findByText("Urgence Saint-Luc")).toBeInTheDocument();
    expect(queries[0].get("start")).toBe(gridStart);
    // Whole weeks, Monday to Sunday, covering the month.
    expect(queries[0].get("end")).toBe(gridEnd);
  });

  it("shows only the week, and remembers it", async () => {
    const queries = serveSchedule({ shifts: [makeShift()] });
    const { user, unmount } = renderSchedule();
    await screen.findByRole("listitem", { name: monday });
    await user.click(screen.getByRole("button", { name: "Semaine" }));
    await waitFor(() => expect(queries[queries.length - 1].get("start")).toBe(monday));
    expect(queries[queries.length - 1].get("end")).toBe(addDays(monday, 6));
    const day = await screen.findByRole("listitem", { name: monday });
    expect(within(day).getByText("Urgence · Soir")).toBeInTheDocument();

    unmount();
    renderSchedule();
    expect(await screen.findByRole("button", { name: "Semaine suivante" })).toBeInTheDocument();
  });

  it("loads the next month, and in the week view the next week", async () => {
    const queries = serveSchedule();
    const { user } = renderSchedule();
    await screen.findByRole("listitem", { name: monday });
    await user.click(screen.getByRole("button", { name: "Mois suivant" }));
    await waitFor(() => expect(queries[queries.length - 1].get("start")).toBe(addDays(nextMonth, -weekdayIndex(nextMonth))));

    await user.click(screen.getByRole("button", { name: "Aujourd'hui" }));
    await user.click(screen.getByRole("button", { name: "Semaine" }));
    await user.click(await screen.findByRole("button", { name: "Semaine suivante" }));
    await waitFor(() => expect(queries[queries.length - 1].get("start")).toBe(addDays(monday, 7)));
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
    await user.click(screen.getByRole("button", { name: "Modifier le quart" }));
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
    await user.click(screen.getByRole("button", { name: "Modifier le quart" }));
    await user.click(screen.getByRole("button", { name: "Toute la série" }));
    await user.click(screen.getByRole("button", { name: "Supprimer" }));
    const confirmDialog = (await screen.findByText("Supprimer toute la série ?")).closest("[role=dialog],[role=alertdialog]");
    await user.click(within(confirmDialog as HTMLElement).getByRole("button", { name: "Supprimer" }));

    expect(await screen.findByText("Quarts supprimés.")).toBeInTheDocument();
    expect(deleted).toHaveLength(1);
    expect(new URL(deleted[0]).search).toBe("");
  });

  it("opens a shift: its encounters, and its suggested codes saved as its claim", async () => {
    const shift = makeShift();
    serveSchedule({ shifts: [shift] });
    const billing: ShiftBilling = {
      shift,
      garde_option: "acte",
      garde_choices: [],
      suggested: [
        {
          code: "09791",
          description: code09791.description,
          hours: 4,
          hourly_fee: 39.1,
          fee_amount: 156.4,
          secteur_dispensation: "07",
          secteur_dispensation_label: "Service d'urgence",
          source: code09791.source,
        },
      ],
      available_codes: [code09791, code19953],
      claim: null,
    };
    const bodies: unknown[] = [];
    server.use(
      http.get("/api/shifts/10/billing", () => HttpResponse.json(billing)),
      http.get("/api/encounters", () =>
        HttpResponse.json([
          makeEncounterRow({ id: 7, setting: makeEncounterSetting({ shift }) }),
          // Same day, another shift: not this one's.
          makeEncounterRow({ id: 8, setting: makeEncounterSetting({ shift: makeShift({ id: 99 }) }) }),
        ]),
      ),
      http.put("/api/shifts/10/claim", async ({ request }) => {
        const body = (await request.json()) as { codes: { code: string; hours: number }[] };
        bodies.push(body);
        return HttpResponse.json(makeShiftClaim({ shift_id: 10 }));
      }),
    );
    const { user } = renderSchedule();
    await user.click(await screen.findByRole("button", { name: /16:00–00:00/ }));

    const encounters = await screen.findByRole("region", { name: "Rencontres du quart" });
    await waitFor(() => expect(within(encounters).getAllByRole("link")).toHaveLength(1));
    expect(within(encounters).getByRole("link")).toHaveAttribute("href", "/app/inbox/7");

    const codes = screen.getByRole("region", { name: "Codes du quart" });
    expect(await within(codes).findByLabelText("Code 09791")).toBeChecked();
    expect(within(codes).getByLabelText("Code 19953")).not.toBeChecked();
    expect(within(codes).getByText("156,40 $")).toBeInTheDocument();
    expect(within(codes).getAllByText(/Secteur 07 — Service d'urgence/)).toHaveLength(2);

    await user.click(within(codes).getByLabelText("Code 19953"));
    const hours = within(codes).getByLabelText("Heures, code 19953");
    await user.clear(hours);
    await user.type(hours, "2");
    await user.click(within(codes).getByRole("button", { name: "Enregistrer la réclamation" }));

    expect(await screen.findByText("Réclamation du quart enregistrée.")).toBeInTheDocument();
    expect(bodies).toEqual([{ codes: [{ code: "09791", hours: 4 }, { code: "19953", hours: 2 }], garde_option: "acte" }]);
    expect(within(codes).getByRole("button", { name: "Mettre à jour la réclamation" })).toBeInTheDocument();
  });

  it("picks a garde forfait: its codes, the modifier warning, saved with the option", async () => {
    const shift = makeShift({ start_time: "20:00:00", end_time: "08:00:00", period: "nuit" });
    serveSchedule({ shifts: [shift] });
    const choices = [
      { value: "acte", label: "Rémunération à l'acte" },
      { value: "premier", label: "Forfait de garde — seul médecin ou premier médecin" },
    ] as const;
    const code09998 = {
      ...code09791,
      code: "09998",
      description: "Forfait de garde sur place — 0 h à 8 h, en semaine",
      quart_hours: 8,
      divisible_in_hours: false,
      hourly_fee: 89.4,
    };
    const asked: (string | null)[] = [];
    const bodies: unknown[] = [];
    server.use(
      http.get("/api/shifts/10/billing", ({ request }) => {
        const option = new URL(request.url).searchParams.get("garde_option");
        asked.push(option);
        const premier = option === "premier";
        return HttpResponse.json({
          shift,
          garde_option: premier ? "premier" : "acte",
          garde_choices: choices,
          suggested: premier ? [{ ...code09998, hours: 8, fee_amount: 715.2 }] : [],
          available_codes: premier ? [code09998] : [code09791],
          claim: null,
        });
      }),
      http.put("/api/shifts/10/claim", async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(makeShiftClaim({ shift_id: 10, garde_option: "premier" }));
      }),
    );
    const { user } = renderSchedule();
    await user.click(await screen.findByRole("button", { name: /20:00–08:00/ }));
    const codes = screen.getByRole("region", { name: "Codes du quart" });
    expect(within(codes).queryByText(/MOD=096/)).not.toBeInTheDocument();

    await user.selectOptions(await within(codes).findByLabelText("Garde sur place (P.G. 1.4)"), "premier");
    expect(await within(codes).findByLabelText("Code 09998")).toBeChecked();
    expect(within(codes).getByText(/MOD=096/)).toBeInTheDocument();
    await user.click(within(codes).getByRole("button", { name: "Enregistrer la réclamation" }));

    await waitFor(() => expect(bodies).toEqual([{ codes: [{ code: "09998", hours: 8 }], garde_option: "premier" }]));
    expect(asked).toEqual([null, "premier"]);
  });
});
