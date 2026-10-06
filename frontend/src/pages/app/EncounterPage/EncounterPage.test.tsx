import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import {
  makeClaim,
  makeClaimLine,
  makeEncounterDetail,
  makeEncounterRow,
  makeExtraction,
  makeFee,
  makeProposedCode,
} from "../../../test/factories";
import { makeUser, renderWithProviders, serveSession } from "../../../test/render";
import { server } from "../../../test/server";
import type { EncounterDetail } from "../../../api";
import EncounterPage from ".";

beforeEach(() => serveSession(makeUser()));

function serveEncounter(detail: EncounterDetail | (() => EncounterDetail)) {
  let loads = 0;
  server.use(
    http.get("/api/encounters/:id", () => {
      loads += 1;
      return HttpResponse.json(typeof detail === "function" ? detail() : detail);
    }),
  );
  return { loads: () => loads };
}

function renderEncounter(state?: unknown) {
  return renderWithProviders(
    <Routes>
      <Route path="/app/inbox/:encounterId" element={<EncounterPage />} />
    </Routes>,
    { route: "/app/inbox/5", state },
  );
}

const visit = makeProposedCode({ code: "00103", description: "Visite principale", fees: [makeFee({ amount: 50 })] });
const consult = makeProposedCode({
  code: "00200",
  description: "Consultation",
  confidence: "low",
  fees: [makeFee({ amount: 80, role: 1 }), makeFee({ amount: 95, role: 2, context: "soir" })],
});
const anesthesia = makeProposedCode({
  code: "09001",
  description: "Anesthésie",
  confidence: "medium",
  fees: [makeFee({ amount: 8, unit: "unités" })],
});

const withCodes = (extra: Partial<EncounterDetail> = {}) =>
  makeEncounterDetail({ id: 5, extraction: makeExtraction([consult, visit, anesthesia], { extraction_run_id: 77 }), ...extra });

const checkbox = (code: string) => screen.getByRole("checkbox", { name: `Facturer le code ${code}` });
const total = () => screen.getByText("Total indicatif").nextElementSibling as HTMLElement;

describe("loading", () => {
  it("shows the patient, status, source line, review and the received note", async () => {
    serveEncounter(withCodes({ batch_label: "Garde du soir", note_text: "Texte de la note." }));
    renderEncounter();
    expect(await screen.findByRole("heading", { level: 1, name: "Patient Test" })).toBeInTheDocument();
    expect(screen.getByText(/sample · 01\/10\/2026 · reçue à .* · Garde du soir/)).toBeInTheDocument();
    expect(screen.getByText("TEST12345678")).toBeInTheDocument();
    expect(screen.getByText("Texte de la note.")).toBeInTheDocument();
  });

  it("shows the server's error", async () => {
    server.use(http.get("/api/encounters/:id", () => HttpResponse.json({ detail: "Rencontre introuvable" }, { status: 404 })));
    renderEncounter();
    expect(await screen.findByText("Rencontre introuvable")).toBeInTheDocument();
  });

  it("links back to the inbox with the period and filters it came from", async () => {
    serveEncounter(withCodes());
    renderEncounter({ inboxSearch: "?status=revu&from=2026-10-01" });
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByRole("link", { name: "← Rencontres" })).toHaveAttribute("href", "/app/inbox?status=revu&from=2026-10-01");
  });

  it("links back to the plain inbox otherwise", async () => {
    serveEncounter(withCodes());
    renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByRole("link", { name: "← Rencontres" })).toHaveAttribute("href", "/app/inbox");
  });
});

describe("reviewing the proposed codes", () => {
  it("lists the codes most confident first, the high-confidence ones ticked and ready to save", async () => {
    serveEncounter(withCodes());
    renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    const boxes = screen.getAllByRole("checkbox").map((box) => box.getAttribute("aria-label"));
    expect(boxes).toEqual(["Facturer le code 00103", "Facturer le code 09001", "Facturer le code 00200"]);
    await waitFor(() => expect(checkbox("00103")).toBeChecked());
    expect(checkbox("09001")).not.toBeChecked();
    expect(checkbox("00200")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Enregistrer la facturation" })).toBeEnabled();
    expect(total()).toHaveTextContent("50.00 $");
  });

  it("starts with nothing ticked once the physician un-ticks it, and saving is disabled", async () => {
    serveEncounter(withCodes());
    const { user } = renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    await user.click(checkbox("00103"));
    expect(screen.getByRole("button", { name: "Enregistrer la facturation" })).toBeDisabled();
    expect(total()).toHaveTextContent("0.00 $");
  });

  it("ticks a code from its description too", async () => {
    serveEncounter(withCodes());
    const { user } = renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    await user.click(screen.getByText("Consultation"));
    expect(checkbox("00200")).toBeChecked();
  });

  it("marks a hovered code's supporting quote in the note, without showing it on the card", async () => {
    const quoted = makeProposedCode({ code: "00103", description: "Visite", supporting_quote: "« toux depuis trois jours »" });
    const unquoted = makeProposedCode({ code: "15145", description: "Autre visite", supporting_quote: "Résumé : patient vu pour une toux" });
    serveEncounter(
      makeEncounterDetail({ id: 5, note_text: "Motif : toux depuis trois jours.", extraction: makeExtraction([quoted, unquoted]) }),
    );
    const { user } = renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByText(/«/)).not.toBeInTheDocument();
    const note = screen.getByText("Note reçue").closest("details")!;
    await user.hover(screen.getByText("Visite"));
    expect(note.querySelector("mark")).toHaveTextContent("toux depuis trois jours");
    // A quote that isn't in the note (it came from the summary) marks nothing.
    await user.hover(screen.getByText("Autre visite"));
    expect(note.querySelector("mark")).toBeNull();
  });

  it("totals the ticked codes at their chosen fee and leaves out a fee in units", async () => {
    serveEncounter(withCodes());
    const { user } = renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    await user.click(checkbox("00200"));
    expect(total()).toHaveTextContent("130.00 $");
    await user.selectOptions(screen.getByLabelText("Tarif pour le code 00200"), "1");
    expect(total()).toHaveTextContent("145.00 $");
    await user.click(checkbox("09001"));
    expect(total()).toHaveTextContent("145.00 $");
    expect(screen.getByText("(1 code sans montant en $)")).toBeInTheDocument();
  });

  it("lists a code's fees by lieu, \"Autre\" when it has none, adding the role when lieux collide", async () => {
    serveEncounter(withCodes());
    renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByText("8 unités")).toBeInTheDocument();
    const options = within(screen.getByLabelText("Tarif pour le code 00200")).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(["Autre — R = 1", "Autre — R = 2 — soir"]);
  });

  it("shows what the physician must confirm, and the run's notes", async () => {
    const flagged = makeProposedCode({ code: "00103", needs_confirmation: ["Lieu de consultation à confirmer"] });
    const extraction = makeExtraction([flagged]);
    extraction.billing.result.notes = "Note incomplète";
    serveEncounter(makeEncounterDetail({ id: 5, extraction }));
    renderEncounter();
    expect(await screen.findByText("⚠ Lieu de consultation à confirmer")).toBeInTheDocument();
    expect(screen.getByText("⚠ Note incomplète")).toBeInTheDocument();
  });

  it("says when no code is supported by the note", async () => {
    serveEncounter(makeEncounterDetail({ id: 5, extraction: makeExtraction([]) }));
    renderEncounter();
    expect(await screen.findByText(/Aucun code candidat/)).toBeInTheDocument();
  });

  it("quotes an unrecognized date, and the physician can set one", async () => {
    serveEncounter(
      makeEncounterDetail({
        id: 5,
        service_date: null,
        extraction: makeExtraction([visit], { encounter_date: null, encounter_date_raw: "le 31 février" }),
      }),
    );
    const { user } = renderEncounter();
    expect(await screen.findByText(/Date non reconnue : « le 31 février »/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enregistrer la facturation" })).toBeDisabled();
    await user.type(screen.getByLabelText("Date de la consultation"), "2026-10-02");
    expect(screen.getByRole("button", { name: "Enregistrer la facturation" })).toBeEnabled();
  });
});

describe("saving", () => {
  it("posts the claim for the extraction run, then confirms and reloads the encounter", async () => {
    let detail = withCodes();
    const { loads } = serveEncounter(() => detail);
    let body: unknown;
    server.use(
      http.post("/api/claims", async ({ request }) => {
        body = await request.json();
        detail = withCodes({ status: "revu", claim: makeClaim({ id: 3, codes: [makeClaimLine({ code: "00200", fee_amount: 95, fee_role: 2, fee_context: "soir" })] }) });
        return HttpResponse.json(makeClaim({ id: 3 }));
      }),
    );
    const { user } = renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    await user.click(checkbox("00200"));
    await user.selectOptions(screen.getByLabelText("Tarif pour le code 00200"), "1");
    await user.click(screen.getByRole("button", { name: "Enregistrer la facturation" }));
    await waitFor(() => expect(loads()).toBe(2));
    expect(body).toEqual({
      extraction_run_id: 77,
      service_date: "2026-10-01",
      // 00103 was ticked from the start, for its high confidence.
      selected_codes: [
        { code: "00200", fee_index: 1 },
        { code: "00103", fee_index: 0 },
      ],
    });
    expect((await screen.findAllByText(/Facturation enregistrée\./)).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Voir la facturation" })[0]).toHaveAttribute("href", "/app/facturation");
    // The reload brought the saved claim back, so the review now starts from it, unchanged.
    expect(screen.getByRole("button", { name: "Enregistrer les modifications" })).toBeDisabled();
  });

  it("shows the server's error and lets the physician try again", async () => {
    serveEncounter(withCodes());
    server.use(http.post("/api/claims", () => HttpResponse.json({ detail: "Patient introuvable" }, { status: 404 })));
    const { user } = renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    await user.click(screen.getByRole("button", { name: "Enregistrer la facturation" }));
    expect(await screen.findByText("Patient introuvable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enregistrer la facturation" })).toBeEnabled();
  });

  it("asks before saving over an existing claim for the same patient and day", async () => {
    serveEncounter(withCodes());
    const flags: (string | null)[] = [];
    server.use(
      http.post("/api/claims", ({ request }) => {
        const flag = new URL(request.url).searchParams.get("confirm_duplicate");
        flags.push(flag);
        return flag === "true"
          ? HttpResponse.json(makeClaim())
          : HttpResponse.json({ detail: { code: "duplicate_claim", message: "Déjà facturé." } }, { status: 409 });
      }),
    );
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { user } = renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    await user.click(screen.getByRole("button", { name: "Enregistrer la facturation" }));
    await waitFor(() => expect(flags).toEqual(["false", "true"]));
    expect(confirm).toHaveBeenCalledWith("Déjà facturé. Enregistrer quand même ?");
    confirm.mockRestore();
  });
});

describe("an encounter with a saved claim", () => {
  const saved = () =>
    withCodes({
      status: "revu",
      claim: makeClaim({ id: 9, codes: [makeClaimLine({ code: "00200", fee_amount: 95, fee_role: 2, fee_context: "soir" })] }),
    });

  it("starts with the claim's codes and fee ticked, and cannot be re-saved unchanged", async () => {
    serveEncounter(saved());
    renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    expect(checkbox("00200")).toBeChecked();
    expect(checkbox("00103")).not.toBeChecked();
    expect(screen.getByLabelText("Tarif pour le code 00200")).toHaveValue("1");
    expect(screen.getByText(/Facturation enregistrée \(brouillon\)/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enregistrer les modifications" })).toBeDisabled();
    expect(total()).toHaveTextContent("95.00 $");
  });

  it("replaces the claim (PUT) once the physician changes something", async () => {
    serveEncounter(saved());
    let seen: { method: string; path: string; body: unknown } | undefined;
    server.use(
      http.put("/api/claims/:id", async ({ request }) => {
        seen = { method: request.method, path: new URL(request.url).pathname, body: await request.json() };
        return HttpResponse.json(makeClaim({ id: 10 }));
      }),
    );
    const { user } = renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    await user.click(checkbox("00103"));
    await user.click(screen.getByRole("button", { name: "Enregistrer les modifications" }));
    await waitFor(() => expect(seen).toBeDefined());
    expect(seen!.method).toBe("PUT");
    expect(seen!.path).toBe("/api/claims/9");
    expect(seen!.body).toMatchObject({
      extraction_run_id: 77,
      // In the result's order (not the confidence order the list is shown in).
      selected_codes: [
        { code: "00200", fee_index: 1 },
        { code: "00103", fee_index: 0 }, // a single-fee code is sent with its only fee
      ],
    });
  });
});

describe("read-only reviews", () => {
  it.each([
    ["a confirmed duplicate", { duplicate_of_id: 2 }, /marquée comme doublon/],
    ["a claim on a bill", { status: "revu" as const, claim: makeClaim({ status: "soumis", bill_id: 1 }) }, /fait partie d'une facture/],
    ["an outdated note", { status: "modifié" as const }, /version plus récente/],
  ])("%s is shown but not editable", async (_name, extra, message) => {
    serveEncounter(withCodes(extra));
    renderEncounter();
    expect(await screen.findByText(message)).toBeInTheDocument();
    for (const box of screen.getAllByRole("checkbox")) expect(box).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Enregistrer/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Date de la consultation")).toBeDisabled();
  });

  it("ticks nothing it can't save", async () => {
    serveEncounter(withCodes({ duplicate_of_id: 2 }));
    renderEncounter();
    await screen.findByText(/marquée comme doublon/);
    expect(checkbox("00103")).not.toBeChecked();
  });
});

describe("what an encounter still needs", () => {
  it("'à associer': asks for a patient, with no review yet", async () => {
    serveEncounter(makeEncounterDetail({ id: 5, status: "à associer", patient: null, extraction: null }));
    renderEncounter();
    expect(await screen.findByRole("heading", { level: 1, name: "Patient à associer" })).toBeInTheDocument();
    expect(screen.getByText("Associer un patient", { selector: "[data-slot=card-title], div, h3" })).toBeInTheDocument();
    expect(screen.queryByText("Codes proposés")).not.toBeInTheDocument();
  });

  it("'reçu' with a patient: extracts on demand, then shows the result", async () => {
    let detail = makeEncounterDetail({ id: 5, status: "reçu", extraction: null });
    serveEncounter(() => detail);
    let extracted = false;
    server.use(
      http.post("/api/encounters/5/extract", () => {
        extracted = true;
        detail = withCodes();
        return HttpResponse.json(makeExtraction([visit]));
      }),
    );
    const { user } = renderEncounter();
    await user.click(await screen.findByRole("button", { name: "Extraire les codes" }));
    expect(await screen.findByText("Codes proposés")).toBeInTheDocument();
    expect(extracted).toBe(true);
  });

  it("'échec': shows why, retries, and shows a new failure", async () => {
    let detail = makeEncounterDetail({ id: 5, status: "échec", extraction: null, extraction_error: "Délai dépassé" });
    serveEncounter(() => detail);
    server.use(
      http.post("/api/encounters/5/extract", () => {
        detail = makeEncounterDetail({ id: 5, status: "échec", extraction: null, extraction_error: "Quota atteint" });
        return HttpResponse.json({ detail: "Quota atteint" }, { status: 502 });
      }),
    );
    const { user } = renderEncounter();
    expect(await screen.findByText(/L.extraction a échoué : Délai dépassé/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByText(/L.extraction a échoué : Quota atteint/)).toBeInTheDocument();
    expect(screen.getAllByText(/Quota atteint/).length).toBeGreaterThan(0);
  });

  it("does not offer extraction without a patient", async () => {
    serveEncounter(makeEncounterDetail({ id: 5, status: "reçu", patient: null, extraction: null }));
    renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByRole("button", { name: "Extraire les codes" })).not.toBeInTheDocument();
  });

  it.each(["prêt", "revu", "modifié"] as const)("does not offer extraction once '%s'", async (status) => {
    serveEncounter(withCodes({ status }));
    renderEncounter();
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByRole("button", { name: /Extraire|Réessayer/ })).not.toBeInTheDocument();
  });
});

describe("stepping between encounters", () => {
  const serveList = (...ids: number[]) =>
    server.use(http.get("/api/encounters", () => HttpResponse.json(ids.map((id) => makeEncounterRow({ id })))));

  it("links to the encounters around this one, in the inbox's order", async () => {
    serveEncounter(withCodes());
    serveList(9, 5, 2);
    renderEncounter({ inboxSearch: "?all=1" });
    expect(await screen.findByText("2 / 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Précédente" })).toHaveAttribute("href", "/app/inbox/9");
    expect(screen.getByRole("link", { name: "Suivante →" })).toHaveAttribute("href", "/app/inbox/2");
  });

  it("disables the step that has nowhere to go", async () => {
    serveEncounter(withCodes());
    serveList(5, 2);
    renderEncounter({ inboxSearch: "?all=1" });
    expect(await screen.findByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "← Précédente" })).toBeDisabled();
  });

  it("saves and opens the next encounter, saying whose claim was saved", async () => {
    serveEncounter(() => withCodes());
    serveList(9, 5, 2);
    server.use(http.post("/api/claims", () => HttpResponse.json(makeClaim())));
    const { user } = renderWithProviders(
      <Routes>
        <Route path="/app/inbox/:encounterId" element={<EncounterPage />} />
      </Routes>,
      { route: "/app/inbox/5", state: { inboxSearch: "?all=1" } },
    );
    const saveAndNext = await screen.findByRole("button", { name: "Enregistrer et suivante →" });
    server.use(
      http.get("/api/encounters/:id", ({ params }) =>
        HttpResponse.json(
          makeEncounterDetail({ id: Number(params.id), patient: { id: 8, full_name: "Suivant Patient", nam: null } }),
        ),
      ),
    );
    await user.click(saveAndNext);
    expect(await screen.findByText("3 / 3")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1, name: "Suivant Patient" })).toBeInTheDocument();
    expect(screen.getByText(/Facturation de Patient Test enregistrée\./)).toBeInTheDocument();
  });

  it("offers the next encounter when there's nothing to save", async () => {
    serveEncounter(
      withCodes({ status: "revu", claim: makeClaim({ codes: [makeClaimLine({ code: "00103", fee_amount: 50 })] }) }),
    );
    serveList(5, 2);
    renderEncounter({ inboxSearch: "?all=1" });
    expect(await screen.findByRole("button", { name: "Suivante →" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Enregistrer et suivante →" })).not.toBeInTheDocument();
  });

  it("shows no steps when the encounter isn't in the list it was opened from", async () => {
    serveEncounter(withCodes());
    serveList(9, 2);
    renderEncounter({ inboxSearch: "?all=1" });
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByRole("navigation", { name: "Navigation entre les rencontres" })).not.toBeInTheDocument();
  });
});
