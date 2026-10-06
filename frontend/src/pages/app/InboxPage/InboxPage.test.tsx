import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes, useLocation, useParams } from "react-router-dom";
import { makeEncounterDetail, makeEncounterPatient, makeEncounterRow, makeExtraction, makeFee, makePatient, makeProposedCode } from "../../../test/factories";
import { makeUser, renderWithProviders, serveSession } from "../../../test/render";
import { server } from "../../../test/server";
import type { EncounterRow } from "../../../api";
import InboxPage from ".";

// Wednesday 2026-10-07, so the default "this week" is 2026-10-05 .. 2026-10-11.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-07T16:00:00Z"));
  serveSession(makeUser());
});
afterEach(() => vi.useRealTimers());

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname + location.search}</p>;
}

function EncounterStub() {
  const { encounterId } = useParams();
  return <p>rencontre {encounterId}</p>;
}

function Pages() {
  return (
    <>
      <Routes>
        <Route path="/app/inbox" element={<InboxPage />} />
        <Route path="/app/inbox/:encounterId" element={<EncounterStub />} />
        <Route path="/app/ajouter" element={<p>ajouter</p>} />
      </Routes>
      <Where />
    </>
  );
}

// Serves a list, recording each request's query string. `rows` can be swapped between loads.
function serveEncounters(rows: EncounterRow[] | (() => EncounterRow[])) {
  const requests: URLSearchParams[] = [];
  server.use(
    http.get("/api/encounters", ({ request }) => {
      requests.push(new URL(request.url).searchParams);
      return HttpResponse.json(typeof rows === "function" ? rows() : rows);
    }),
  );
  return requests;
}

const last = <T,>(items: T[]) => items[items.length - 1];

const ready = (id: number, extra: Partial<EncounterRow> = {}) =>
  makeEncounterRow({
    id,
    patient: { id, display_name: `Patient ${id}`, nam: `TEST ******0${id}` },
    ...extra,
  });

function renderInbox(route = "/app/inbox", state?: unknown) {
  return renderWithProviders(<Pages />, { route, state });
}

describe("loading the list", () => {
  it("asks for the current week by default and counts the rows per status tab", async () => {
    const requests = serveEncounters([ready(1), ready(2, { status: "à associer", patient: null }), ready(3, { status: "échec" })]);
    renderInbox();
    expect(await screen.findByText("Patient 1")).toBeInTheDocument();
    expect(requests[0].get("date_from")).toBe("2026-10-05");
    expect(requests[0].get("date_to")).toBe("2026-10-11");
    const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    expect(tabs).toEqual(["Toutes3", "À traiter3", "Prêtes1", "À associer1", "Échecs1", "Revues0"]);
    expect(screen.getByRole("tab", { name: /Toutes/ })).toHaveAttribute("aria-selected", "true");
  });

  it("shows each row's codes and indicative total, and what's left to choose", async () => {
    serveEncounters([
      ready(1, { codes: ["15804", "15188"], indicative_total: 87.05 }),
      ready(2, { codes: [], code_count: 2, indicative_total: null }),
      ready(3, { status: "reçu", codes: null, code_count: null, indicative_total: null }),
    ]);
    renderInbox();
    const row = (name: string) => within(screen.getByText(name).closest("tr")!);
    expect(await screen.findByText("Patient 1")).toBeInTheDocument();
    expect(row("Patient 1").getByText("15804")).toBeInTheDocument();
    expect(row("Patient 1").getByText("15188")).toBeInTheDocument();
    expect(row("Patient 1").getByText("87,05 $")).toBeInTheDocument();
    expect(row("Patient 2").getByText("2 codes à confirmer")).toBeInTheDocument();
    expect(row("Patient 3").getByText("Extraction en attente")).toBeInTheDocument();
    // The day's total, in its header.
    expect(screen.getByRole("region", { name: /1 octobre 2026/ })).toHaveTextContent("Total indicatif 87,05 $");
  });

  it("groups rows by day, most recent first, with batch labels", async () => {
    serveEncounters([
      ready(1, { service_date: "2026-10-05" }),
      ready(2, { service_date: "2026-10-06", batch_label: "Garde du soir" }),
    ]);
    renderInbox();
    await screen.findByText("Patient 1");
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings[0]).toMatch(/^mardi 6 octobre 2026/);
    expect(headings[1]).toMatch(/^lundi 5 octobre 2026/);
    expect(screen.getByRole("heading", { level: 3, name: "Garde du soir" })).toBeInTheDocument();
  });

  it("files an undated encounter under the clinic day it was received", async () => {
    serveEncounters([ready(1, { service_date: null, received_at: "2026-10-07T02:30:00Z" })]); // 22:30 on the 6th in Montreal
    renderInbox();
    await screen.findByText("Patient 1");
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(/mardi 6 octobre 2026/);
  });

  it("says when the period is empty", async () => {
    serveEncounters([]);
    renderInbox();
    expect(await screen.findByText("Aucune rencontre pour cette période.")).toBeInTheDocument();
  });

  it("shows the server's error", async () => {
    server.use(http.get("/api/encounters", () => HttpResponse.json({ detail: "Erreur interne" }, { status: 500 })));
    renderInbox();
    expect(await screen.findByText("Erreur interne")).toBeInTheDocument();
  });

  it("toasts the notes just received (from the add-notes page)", async () => {
    serveEncounters([ready(1)]);
    renderInbox("/app/inbox", { received: { received: 3, duplicates: 1 } });
    expect(await screen.findByText("3 notes reçues · 1 déjà reçue (ignorées).")).toBeInTheDocument();
  });
});

describe("period and filters", () => {
  it("a preset reloads with its dates and is kept in the URL", async () => {
    const requests = serveEncounters([ready(1)]);
    const { user } = renderInbox();
    await screen.findByText("Patient 1");
    await user.click(screen.getByRole("button", { name: "Aujourd'hui" }));
    await waitFor(() => expect(last(requests)?.get("date_from")).toBe("2026-10-07"));
    expect(last(requests)?.get("date_to")).toBe("2026-10-07");
    expect(screen.getByTestId("where")).toHaveTextContent("/app/inbox?from=2026-10-07&to=2026-10-07");
    expect(screen.getByRole("button", { name: "Aujourd'hui" })).toHaveAttribute("aria-pressed", "true");
  });

  it("'Tout' asks for every encounter, without bounds", async () => {
    const requests = serveEncounters([ready(1)]);
    const { user } = renderInbox();
    await screen.findByText("Patient 1");
    await user.click(screen.getByRole("button", { name: "Tout" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/app/inbox?all=1"));
    await waitFor(() => expect([...last(requests)!.keys()]).toEqual([]));
  });

  it("reads the period and filters back from the URL", async () => {
    const requests = serveEncounters([ready(1), ready(2, { status: "revu" })]);
    renderInbox("/app/inbox?from=2026-09-01&to=2026-09-30&status=revu");
    await screen.findByText("Patient 2");
    expect(requests[0].get("date_from")).toBe("2026-09-01");
    expect(requests[0].get("date_to")).toBe("2026-09-30");
    expect(screen.queryByText("Patient 1")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Revues/ })).toHaveAttribute("aria-selected", "true");
  });

  it("filters rows client-side without a new request, and keeps the status in the URL", async () => {
    const requests = serveEncounters([ready(1), ready(2, { status: "revu" })]);
    const { user } = renderInbox();
    await screen.findByText("Patient 1");
    await user.click(screen.getByRole("tab", { name: /À traiter/ }));
    expect(screen.queryByText("Patient 2")).not.toBeInTheDocument();
    expect(decodeURIComponent(screen.getByTestId("where").textContent!)).toContain("status=à+traiter");
    expect(requests).toHaveLength(1);
  });

  it("filters by patient name, ignoring accents, and clears all filters", async () => {
    serveEncounters([
      ready(1, { patient: { id: 1, display_name: "Frédéric T.", nam: "TEST ******01" } }),
      ready(2),
    ]);
    const { user } = renderInbox();
    await screen.findByText("Frédéric T.");
    await user.type(screen.getByLabelText("Patient"), "fred");
    expect(screen.queryByText("Patient 2")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Effacer les filtres" }));
    expect(await screen.findByText("Patient 2")).toBeInTheDocument();
  });

  it("offers the sources seen in the list", async () => {
    serveEncounters([ready(1, { source_system: "epic" }), ready(2, { source_system: "plume" })]);
    const { user } = renderInbox();
    await screen.findByText("Patient 1");
    const source = screen.getByLabelText("Source");
    // Known sources by their name, others as sent.
    expect(within(source).getAllByRole("option").map((o) => o.textContent)).toEqual(["Toutes", "Epic", "plume"]);
    await user.selectOptions(source, "plume");
    expect(screen.queryByText("Patient 1")).not.toBeInTheDocument();
    expect(screen.getByText("Patient 2")).toBeInTheDocument();
  });

  it("explains when the filters hide everything", async () => {
    serveEncounters([ready(1)]);
    const { user } = renderInbox();
    await screen.findByText("Patient 1");
    await user.click(screen.getByRole("tab", { name: /Revues/ }));
    expect(screen.getByText("Aucune rencontre ne correspond aux filtres.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Effacer les filtres" }));
    expect(screen.getByText("Patient 1")).toBeInTheDocument();
  });

  it("ignores a start date after the end date", async () => {
    serveEncounters([ready(1)]);
    const { user } = renderInbox("/app/inbox?from=2026-10-05&to=2026-10-11");
    await screen.findByText("Patient 1");
    const from = screen.getByLabelText("Du");
    await user.clear(from);
    await user.type(from, "2026-10-20");
    expect(screen.getByTestId("where")).not.toHaveTextContent("2026-10-20");
  });
});

describe("row actions", () => {
  it("'Réviser' opens a ready encounter", async () => {
    serveEncounters([ready(7)]);
    const { user } = renderInbox("/app/inbox?status=à traiter");
    await user.click(await screen.findByRole("button", { name: "Réviser" }));
    expect(await screen.findByText("rencontre 7")).toBeInTheDocument();
  });

  it("clicking a row opens the encounter, with no 'Réviser' once reviewed", async () => {
    serveEncounters([ready(7, { status: "revu" })]);
    const { user } = renderInbox();
    await user.click((await screen.findAllByRole("row"))[1]);
    expect(await screen.findByText("rencontre 7")).toBeInTheDocument();
  });

  it("offers no 'Réviser' once reviewed", async () => {
    serveEncounters([ready(1, { status: "revu" })]);
    renderInbox();
    await screen.findAllByRole("row");
    expect(screen.queryByRole("button", { name: "Réviser" })).not.toBeInTheDocument();
  });

  it.each([
    ["reçu", "Extraire"],
    ["échec", "Réessayer"],
  ] as const)("a '%s' encounter with a patient can be extracted ('%s')", async (status, label) => {
    let rows = [ready(4, { status })];
    serveEncounters(() => rows);
    let extracted = false;
    server.use(
      http.post("/api/encounters/4/extract", () => {
        extracted = true;
        rows = [ready(4, { status: "prêt" })];
        return HttpResponse.json(makeExtraction([]));
      }),
    );
    const { user } = renderInbox();
    await user.click(await screen.findByRole("button", { name: label }));
    expect(extracted).toBe(true);
    expect(await screen.findByRole("button", { name: "Réviser" })).toBeInTheDocument();
  });

  it("does not offer extraction without a patient", async () => {
    serveEncounters([ready(1, { status: "reçu", patient: null })]);
    renderInbox();
    await screen.findAllByRole("row");
    expect(screen.queryByRole("button", { name: "Extraire" })).not.toBeInTheDocument();
  });

  it("shows an extraction failure and re-reads the list (the encounter is now 'échec')", async () => {
    let rows = [ready(4, { status: "reçu" })];
    const requests = serveEncounters(() => rows);
    server.use(
      http.post("/api/encounters/4/extract", () => {
        rows = [ready(4, { status: "échec" })];
        return HttpResponse.json({ detail: "Le modèle a échoué" }, { status: 502 });
      }),
    );
    const { user } = renderInbox();
    await user.click(await screen.findByRole("button", { name: "Extraire" }));
    expect(await screen.findByText("Le modèle a échoué")).toBeInTheDocument();
    expect(requests).toHaveLength(2);
    expect(await screen.findByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });

  it("associates a patient to an 'à associer' note and re-reads the list", async () => {
    let rows = [ready(5, { status: "à associer", patient: null })];
    serveEncounters(() => rows);
    server.use(
      http.get("/api/patients/search", ({ request }) => {
        expect(new URL(request.url).searchParams.get("q")).toBe("Dupont");
        return HttpResponse.json([makePatient({ id: 42, full_name: "Jeanne Dupont", ramq_number: "TEST99999999" })]);
      }),
    );
    let body: unknown;
    server.use(
      http.post("/api/encounters/5/patient", async ({ request }) => {
        body = await request.json();
        rows = [ready(5, { status: "prêt" })];
        return HttpResponse.json(makeEncounterDetail({ id: 5 }));
      }),
    );
    const { user } = renderInbox();
    await user.click(await screen.findByRole("button", { name: "Associer un patient" }));
    expect(screen.getByRole("button", { name: "Associer" })).toBeDisabled();
    await user.type(screen.getByPlaceholderText("Nom ou NAM du patient..."), "Dupont");
    await user.click(await screen.findByRole("option", { name: /Jeanne Dupont/ }));
    await user.click(screen.getByRole("button", { name: "Associer" }));
    await waitFor(() => expect(body).toEqual({ patient_id: 42 }));
    expect(await screen.findByRole("button", { name: "Réviser" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Associer" })).not.toBeInTheDocument();
  });

  it("deletes an encounter from its row menu, after confirming", async () => {
    let rows = [ready(6, { status: "reçu" })];
    serveEncounters(() => rows);
    let deleted = false;
    server.use(
      http.delete("/api/encounters/6", () => {
        deleted = true;
        rows = [];
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderInbox();
    await user.click(await screen.findByRole("button", { name: "Actions — Patient 6" }));
    await user.click(await screen.findByRole("menuitem", { name: "Supprimer" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Supprimer la rencontre ?")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Supprimer" }));
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Aucune rencontre pour cette période.")).toBeInTheDocument();
  });

  it("offers no deletion once the encounter is billed", async () => {
    serveEncounters([ready(6, { status: "revu", deletable: false })]);
    renderInbox();
    await screen.findByText("Patient 6");
    expect(screen.queryByRole("button", { name: "Actions — Patient 6" })).not.toBeInTheDocument();
  });

  it("can cancel the association", async () => {
    serveEncounters([ready(5, { status: "à associer", patient: null })]);
    const { user } = renderInbox();
    await user.click(await screen.findByRole("button", { name: "Associer un patient" }));
    await user.click(screen.getByRole("button", { name: "Annuler" }));
    expect(screen.getByRole("button", { name: "Associer un patient" })).toBeInTheDocument();
  });
});

describe("approve all", () => {
  const clean = (id: number) => ready(id, { all_clean: true });
  const cleanDetail = (id: number, codes = [makeProposedCode({ code: `0010${id}` })]) =>
    makeEncounterDetail({
      id,
      patient: makeEncounterPatient({ id, full_name: `Patient ${id}`, nam: null }),
      extraction: makeExtraction(codes, { extraction_run_id: 100 + id }),
    });

  it("is not offered when nothing is clean", async () => {
    serveEncounters([ready(1)]);
    renderInbox();
    await screen.findByText("Patient 1");
    expect(screen.queryByRole("button", { name: /Approuver en lot/ })).not.toBeInTheDocument();
  });

  it("counts only the rows that pass the current filters", async () => {
    serveEncounters([clean(1), clean(2, ), ready(3, { status: "revu", all_clean: true })]);
    const { user } = renderInbox();
    await screen.findByText("Patient 1");
    expect(screen.getByRole("button", { name: "Approuver en lot (3)" })).toBeEnabled();
    await user.click(screen.getByRole("tab", { name: /À traiter/ }));
    expect(screen.getByRole("button", { name: "Approuver en lot (2)" })).toBeEnabled();
  });

  it("bills every code at its only fee, one claim per encounter, then re-reads the list", async () => {
    const requests = serveEncounters([clean(1), clean(2)]);
    server.use(
      http.get("/api/encounters/:id", ({ params }) =>
        HttpResponse.json(
          cleanDetail(
            Number(params.id),
            Number(params.id) === 1
              ? [makeProposedCode({ code: "00101" }), makeProposedCode({ code: "15145", fees: [makeFee({ amount: 12 })] })]
              : [makeProposedCode({ code: "00102" })],
          ),
        ),
      ),
    );
    const claims: unknown[] = [];
    server.use(
      http.post("/api/claims", async ({ request }) => {
        claims.push({ confirm: new URL(request.url).searchParams.get("confirm_duplicate"), body: await request.json() });
        return HttpResponse.json({});
      }),
    );
    const { user } = renderInbox();
    await user.click(await screen.findByRole("button", { name: "Approuver en lot (2)" }));
    expect(await screen.findByText("2 rencontres à facturer")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approuver et enregistrer" }));
    expect(await screen.findByText("2 facturations enregistrées")).toBeInTheDocument();
    expect(claims).toEqual([
      {
        confirm: "false",
        body: {
          extraction_run_id: 101,
          service_date: "2026-10-01",
          selected_codes: [
            { code: "00101", fee_index: null },
            { code: "15145", fee_index: null },
          ],
        },
      },
      {
        confirm: "false",
        body: { extraction_run_id: 102, service_date: "2026-10-01", selected_codes: [{ code: "00102", fee_index: null }] },
      },
    ]);
    expect(requests.length).toBeGreaterThan(1);
  });

  it("leaves out an encounter that is no longer approvable (several fees, or something to confirm)", async () => {
    serveEncounters([clean(1), clean(2), clean(3)]);
    const details: Record<number, ReturnType<typeof cleanDetail>> = {
      1: cleanDetail(1),
      2: cleanDetail(2, [makeProposedCode({ fees: [makeFee(), makeFee({ role: 2 })] })]),
      3: cleanDetail(3, [makeProposedCode({ needs_confirmation: ["lieu"] })]),
    };
    server.use(http.get("/api/encounters/:id", ({ params }) => HttpResponse.json(details[Number(params.id)])));
    const { user } = renderInbox();
    await user.click(await screen.findByRole("button", { name: /Approuver en lot/ }));
    expect(await screen.findByText("1 rencontre à facturer")).toBeInTheDocument();
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Patient 1")).toBeInTheDocument();
    expect(within(dialog).queryByText("Patient 2")).not.toBeInTheDocument();
  });

  it("reports a failing claim next to it without stopping the others (a duplicate is never overridden)", async () => {
    serveEncounters([clean(1), clean(2)]);
    server.use(
      http.get("/api/encounters/:id", ({ params }) => HttpResponse.json(cleanDetail(Number(params.id)))),
      http.post("/api/claims", async ({ request }) => {
        const body = (await request.json()) as { extraction_run_id: number };
        return body.extraction_run_id === 101
          ? HttpResponse.json({ detail: { code: "duplicate_claim", message: "Déjà facturé." } }, { status: 409 })
          : HttpResponse.json({});
      }),
    );
    const { user } = renderInbox();
    await user.click(await screen.findByRole("button", { name: /Approuver en lot/ }));
    await user.click(await screen.findByRole("button", { name: "Approuver et enregistrer" }));
    expect(await screen.findByText("1 facturation enregistrée")).toBeInTheDocument();
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Déjà facturé.")).toBeInTheDocument();
    expect(within(dialog).getByText("✓ Enregistrée")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Fermer" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows an error when an encounter can't be loaded", async () => {
    serveEncounters([clean(1)]);
    server.use(http.get("/api/encounters/:id", () => HttpResponse.json({ detail: "Introuvable" }, { status: 404 })));
    const { user } = renderInbox();
    await user.click(await screen.findByRole("button", { name: /Approuver en lot/ }));
    expect(await screen.findByText("Introuvable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approuver et enregistrer" })).toBeDisabled();
  });
});

describe("possible duplicates", () => {
  const flagged = () => ready(1, { possible_duplicate_ids: [2] });

  function serveDetails() {
    server.use(
      http.get("/api/encounters/:id", ({ params }) =>
        HttpResponse.json(makeEncounterDetail({ id: Number(params.id), note_text: `Texte de la note ${params.id}` })),
      ),
    );
  }

  it("opens the two notes side by side from the badge", async () => {
    serveEncounters([flagged()]);
    serveDetails();
    const { user } = renderInbox();
    await user.click(await screen.findByRole("button", { name: "Doublon possible" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Texte de la note 1")).toBeInTheDocument();
    expect(within(dialog).getByText("Texte de la note 2")).toBeInTheDocument();
  });

  it("'Visites distinctes' dismisses the flag and re-reads the list", async () => {
    let rows = [flagged()];
    const requests = serveEncounters(() => rows);
    serveDetails();
    let dismissed = false;
    server.use(
      http.post("/api/encounters/1/not-duplicate", () => {
        dismissed = true;
        rows = [ready(1)];
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderInbox();
    await user.click(await screen.findByRole("button", { name: "Doublon possible" }));
    await user.click(await screen.findByRole("button", { name: "Visites distinctes" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(dismissed).toBe(true);
    expect(requests).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Doublon possible" })).not.toBeInTheDocument();
  });

  it("'Même visite — garder celle-ci' hides the other note and keeps this one", async () => {
    serveEncounters([flagged()]);
    serveDetails();
    let called = "";
    server.use(
      http.post("/api/encounters/:id/duplicate-of/:keptId", ({ params }) => {
        called = `${params.id}->${params.keptId}`;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderInbox();
    await user.click(await screen.findByRole("button", { name: "Doublon possible" }));
    const keep = await screen.findAllByRole("button", { name: "Même visite — garder celle-ci" });
    await user.click(keep[1]); // keep note 2, so note 1 is the duplicate
    await waitFor(() => expect(called).toBe("1->2"));
  });

  it("shows the error and keeps the modal open when the answer fails", async () => {
    serveEncounters([flagged()]);
    serveDetails();
    server.use(http.post("/api/encounters/1/not-duplicate", () => HttpResponse.json({ detail: "Refusé" }, { status: 409 })));
    const { user } = renderInbox();
    await user.click(await screen.findByRole("button", { name: "Doublon possible" }));
    await user.click(await screen.findByRole("button", { name: "Visites distinctes" }));
    expect(await screen.findByText("Refusé")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
