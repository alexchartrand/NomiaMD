import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { makeClaim, makeClaimLine } from "../../../test/factories";
import { makeUser, renderWithProviders, serveSession } from "../../../test/render";
import { server } from "../../../test/server";
import type { Bill, Claim } from "../../../api";
import { Route, Routes, useParams } from "react-router-dom";
import FacturationPage from ".";

const makeBill = (overrides: Partial<Bill> = {}): Bill => ({
  id: 1,
  number: "F-2026-0001",
  start_date: "2026-10-01",
  end_date: "2026-10-07",
  generated_at: "2026-10-08T15:00:00Z",
  total_amount: 120,
  claim_count: 2,
  ...overrides,
});

const claimFor = (id: number, name: string, extra: Partial<Claim> = {}) =>
  makeClaim({
    id,
    patient_full_name: name,
    total_amount: 50 + id,
    codes: [makeClaimLine({ code: `0010${id}`, description: `Visite ${id}`, explanation: `Raison ${id}` })],
    ...extra,
  });

beforeEach(() => {
  // A fixed clinic "today" (a Wednesday), for the presets and the RAMQ deadline.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-07T16:00:00Z"));
  serveSession(makeUser());
});

afterEach(() => vi.useRealTimers());

// Serves /claims, recording each request's query string.
function serveClaims(claims: Claim[] | ((params: URLSearchParams) => Claim[])) {
  const requests: URLSearchParams[] = [];
  server.use(
    http.get("/api/claims", ({ request }) => {
      const params = new URL(request.url).searchParams;
      requests.push(params);
      return HttpResponse.json(typeof claims === "function" ? claims(params) : claims);
    }),
  );
  return requests;
}

function serveBills(bills: Bill[] | (() => Bill[])) {
  server.use(http.get("/api/bills", () => HttpResponse.json(typeof bills === "function" ? bills() : bills)));
}

function FacturerStub() {
  return <p>facturer {useParams().claimId}</p>;
}

function EncounterStub() {
  return <p>rencontre {useParams().encounterId}</p>;
}

const renderPage = (route = "/app/facturation") =>
  renderWithProviders(
    <Routes>
      <Route path="/app/facturation" element={<FacturationPage />} />
      <Route path="/app/facturer/:claimId" element={<FacturerStub />} />
      <Route path="/app/inbox/:encounterId" element={<EncounterStub />} />
    </Routes>,
    { route },
  );

// A row's ⋯ menu, then one of its items.
async function pickRowAction(user: ReturnType<typeof renderPage>["user"], menu: string, item: string) {
  await user.click(await screen.findByRole("button", { name: menu }));
  await user.click(await screen.findByRole("menuitem", { name: item }));
}

// The app's confirm dialog: answers it.
async function answer(user: ReturnType<typeof renderPage>["user"], label: "Supprimer" | "Annuler") {
  const dialog = await screen.findByRole("dialog");
  await user.click(within(dialog).getByRole("button", { name: label }));
}

describe("claims tab", () => {
  it("marks a claim billed without an encounter and offers to edit its draft", async () => {
    serveClaims([
      claimFor(1, "Jeanne Dupont", {
        source_system: "manual",
        codes: [makeClaimLine({ code: "00059", origin: "manual", confidence: null, explanation: "" })],
      }),
      claimFor(2, "Marc Roy"),
    ]);
    const { user } = renderPage();
    const manualRow = (await screen.findByText(/Jeanne Dupont/)).closest("tr")!;
    expect(within(manualRow).getByText("Sans rencontre")).toBeInTheDocument();

    await user.click(within(manualRow).getByRole("button", { name: "Détails" }));
    expect(await screen.findByText("Ajouté manuellement")).toBeInTheDocument();

    // An encounter's claim is edited from its review, not here.
    await user.click(screen.getByRole("button", { name: "Actions — réclamation de Marc Roy" }));
    expect(screen.queryByRole("menuitem", { name: "Modifier" })).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    await pickRowAction(user, "Actions — réclamation de Jeanne Dupont", "Modifier");
    expect(await screen.findByText("facturer 1")).toBeInTheDocument();
  });

  it("lists the claims with date, codes, total and status", async () => {
    serveClaims([claimFor(1, "Jeanne Dupont"), claimFor(2, "Marc Roy", { status: "soumis", bill_id: 1, total_amount: null })]);
    renderPage();
    const row = (await screen.findByText("Jeanne Dupont")).closest("tr")!;
    expect(within(row).getByText("01/10/2026")).toBeInTheDocument();
    expect(within(row).getByText(/00101/)).toBeInTheDocument();
    expect(within(row).getByText("51,00 $")).toBeInTheDocument();
    expect(within(row).getByText("Brouillon")).toBeInTheDocument();
    const submitted = screen.getByText("Marc Roy").closest("tr")!;
    expect(within(submitted).getByText("Soumis")).toBeInTheDocument();
    // The listed claims' total, under the table.
    expect(screen.getByText("2 réclamations").parentElement).toHaveTextContent("Total 51,00 $");
    expect(within(submitted).getByText("—")).toBeInTheDocument();
  });

  it("says when there is nothing in the period", async () => {
    serveClaims([]);
    renderPage();
    expect(await screen.findByText("Aucune réclamation pour cette période.")).toBeInTheDocument();
  });

  it("shows the server's error", async () => {
    server.use(http.get("/api/claims", () => HttpResponse.json({ detail: "Erreur interne" }, { status: 500 })));
    renderPage();
    expect(await screen.findByText("Erreur interne")).toBeInTheDocument();
  });

  it("expands a claim's code lines with fee and explanation, and collapses them again", async () => {
    serveClaims([claimFor(1, "Jeanne Dupont", { codes: [makeClaimLine({ code: "00103", fee_amount: 50, fee_role: 2, explanation: "Raison" })] })]);
    const { user } = renderPage();
    await screen.findByText("Jeanne Dupont");
    await user.click(screen.getByRole("button", { name: "Détails" }));
    expect(screen.getByText("Raison")).toBeInTheDocument();
    expect(screen.getByText("Raison").closest("li")).toHaveTextContent("00103Visite principale — 50,00 $ — R = 2");
    await user.click(screen.getByRole("button", { name: "Détails" }));
    expect(screen.queryByText("Raison")).not.toBeInTheDocument();
  });

  it("reads every claim of the period (paged, see api/paging.test.ts), all of them by default", async () => {
    const requests = serveClaims([claimFor(1, "Jeanne Dupont")]);
    const { user } = renderPage();
    expect(await screen.findByText("Jeanne Dupont")).toBeInTheDocument();
    expect(requests.map((r) => Object.fromEntries(r))).toEqual([{ limit: "200", offset: "0" }]);
    expect(within(screen.getByRole("group", { name: "Période" })).getByRole("button", { name: "Tout" })).toHaveAttribute("aria-pressed", "true");

    await user.click(within(screen.getByRole("group", { name: "Période" })).getByRole("button", { name: "Cette semaine" }));
    await waitFor(() =>
      expect(requests.map((r) => Object.fromEntries(r))).toContainEqual({
        date_from: "2026-10-05",
        date_to: "2026-10-11",
        limit: "200",
        offset: "0",
      }),
    );
  });

  it("filters on status, patient and source in the page, counting each status", async () => {
    serveClaims([
      claimFor(1, "Frédéric Lavoie", { source_system: "epic" }),
      claimFor(2, "Marc Roy", { source_system: "manual" }),
      claimFor(3, "Lise Tremblay", { status: "soumis", bill_id: 1 }),
    ]);
    const { user } = renderPage();
    await screen.findByText("Marc Roy");
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Réclamations",
      "Factures générées",
      "Toutes3",
      "Brouillons2",
      "Soumises1",
    ]);

    await user.click(screen.getByRole("tab", { name: /Brouillons/ }));
    expect(screen.queryByText("Lise Tremblay")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Patient"), "frederic");
    expect(screen.queryByText("Marc Roy")).not.toBeInTheDocument();
    expect(screen.getByText("Frédéric Lavoie")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Effacer les filtres" }));
    await user.selectOptions(screen.getByLabelText("Source"), "manual");
    expect(screen.getByRole("option", { name: "Saisie manuelle" })).toBeInTheDocument();
    expect(screen.queryByText("Frédéric Lavoie")).not.toBeInTheDocument();
    expect(screen.getByText("Marc Roy")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Source"), "epic");
    await user.click(screen.getByRole("tab", { name: /Soumises/ }));
    expect(await screen.findByText("Aucune réclamation ne correspond aux filtres.")).toBeInTheDocument();
    // The empty state's button clears the status too, unlike the bar's.
    await user.click(screen.getAllByRole("button", { name: "Effacer les filtres" }).pop()!);
    expect(screen.getByText("Lise Tremblay")).toBeInTheDocument();
  });

  it("marks how long each draft has left before RAMQ's deadline, with a tab for the urgent ones", async () => {
    serveClaims([
      claimFor(1, "Jeanne Dupont", { service_date: "2026-10-01" }),
      claimFor(2, "Marc Roy", { service_date: "2026-07-19" }),
      claimFor(3, "Lise Tremblay", { service_date: "2026-07-01" }),
      claimFor(4, "Paul Gagnon", { service_date: "2026-07-01", status: "soumis", bill_id: 1 }),
    ]);
    const { user } = renderPage();
    const row = (name: string) => screen.getByText(name).closest("tr")!;
    await screen.findByText("Jeanne Dupont");
    expect(within(row("Jeanne Dupont")).getByText("84 j restants")).toBeInTheDocument();
    expect(within(row("Marc Roy")).getByText("10 j restants")).toBeInTheDocument();
    expect(within(row("Lise Tremblay")).getByText("Délai dépassé")).toBeInTheDocument();
    expect(within(row("Paul Gagnon")).queryByText(/restant|Délai/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Échéance proche/ }));
    expect(screen.queryByText("Jeanne Dupont")).not.toBeInTheDocument();
    expect(screen.queryByText("Paul Gagnon")).not.toBeInTheDocument();
    expect(screen.getByText("Marc Roy")).toBeInTheDocument();
    expect(screen.getByText("Lise Tremblay")).toBeInTheDocument();
  });

  it("opens the encounter a claim was billed from", async () => {
    serveClaims([claimFor(1, "Jeanne Dupont", { encounter_id: 42 }), claimFor(2, "Marc Roy", { source_system: "manual" })]);
    const { user } = renderPage();
    await screen.findByText("Marc Roy");
    // Billed without an encounter: nothing to open.
    await user.click(screen.getByRole("button", { name: "Actions — réclamation de Marc Roy" }));
    expect(screen.queryByRole("menuitem", { name: "Voir la rencontre" })).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    await pickRowAction(user, "Actions — réclamation de Jeanne Dupont", "Voir la rencontre");
    expect(await screen.findByText("rencontre 42")).toBeInTheDocument();
  });

  describe("deleting", () => {
    it("is not possible once on a bill", async () => {
      serveClaims([claimFor(1, "Marc Roy", { status: "soumis", bill_id: 1 })]);
      renderPage();
      await screen.findByText("Marc Roy");
      expect(screen.queryByRole("button", { name: "Actions — réclamation de Marc Roy" })).not.toBeInTheDocument();
    });

    it("asks first, then deletes the draft and re-reads the list", async () => {
      let claims = [claimFor(1, "Jeanne Dupont")];
      serveClaims(() => claims);
      let deleted = "";
      server.use(
        http.delete("/api/claims/:id", ({ params }) => {
          deleted = String(params.id);
          claims = [];
          return new HttpResponse(null, { status: 204 });
        }),
      );
      const { user } = renderPage();
      await pickRowAction(user, "Actions — réclamation de Jeanne Dupont", "Supprimer");
      expect(await screen.findByText(/La réclamation de Jeanne Dupont du 01\/10\/2026 sera supprimée/)).toBeInTheDocument();
      expect(deleted).toBe("");
      await answer(user, "Supprimer");
      expect(await screen.findByText("Aucune réclamation pour cette période.")).toBeInTheDocument();
      expect(deleted).toBe("1");
    });

    it("does nothing when the physician declines", async () => {
      serveClaims([claimFor(1, "Jeanne Dupont")]);
      const onDelete = vi.fn();
      server.use(http.delete("/api/claims/:id", () => (onDelete(), new HttpResponse(null, { status: 204 }))));
      const { user } = renderPage();
      await pickRowAction(user, "Actions — réclamation de Jeanne Dupont", "Supprimer");
      await answer(user, "Annuler");
      expect(onDelete).not.toHaveBeenCalled();
      expect(screen.getByText("Jeanne Dupont")).toBeInTheDocument();
    });

    it("shows the server's refusal and keeps the claim", async () => {
      serveClaims([claimFor(1, "Jeanne Dupont")]);
      server.use(http.delete("/api/claims/:id", () => HttpResponse.json({ detail: "Déjà sur une facture" }, { status: 409 })));
      const { user } = renderPage();
      await pickRowAction(user, "Actions — réclamation de Jeanne Dupont", "Supprimer");
      await answer(user, "Supprimer");
      expect(await screen.findByText("Déjà sur une facture")).toBeInTheDocument();
      expect(screen.getByText("Jeanne Dupont")).toBeInTheDocument();
    });
  });
});

describe("generated bills tab", () => {
  async function openBills(user: ReturnType<typeof renderPage>["user"]) {
    await user.click(screen.getByRole("tab", { name: "Factures générées" }));
  }

  it("lists the bills with period, count, total and a PDF link", async () => {
    serveClaims([]);
    serveBills([makeBill(), makeBill({ id: 2, number: "F-2026-0002", total_amount: null })]);
    const { user } = renderPage();
    await openBills(user);
    const row = (await screen.findByText("F-2026-0001")).closest("tr")!;
    expect(within(row).getByText("01/10/2026 – 07/10/2026")).toBeInTheDocument();
    expect(within(row).getByText("08/10/2026")).toBeInTheDocument();
    expect(within(row).getByText("120,00 $")).toBeInTheDocument();
    const pdf = within(row).getByRole("link", { name: "Télécharger le PDF" });
    expect(pdf).toHaveAttribute("href", "/api/bills/1/pdf");
    expect(pdf).toHaveAttribute("download");
    expect(within(screen.getByText("F-2026-0002").closest("tr")!).getByText("—")).toBeInTheDocument();
  });

  it("says when there is none", async () => {
    serveClaims([]);
    serveBills([]);
    const { user } = renderPage();
    await openBills(user);
    expect(await screen.findByText("Aucune facture générée.")).toBeInTheDocument();
  });

  it("loads a bill's claims when expanded", async () => {
    serveClaims([]);
    serveBills([makeBill()]);
    server.use(
      http.get("/api/bills/1", () =>
        HttpResponse.json({ ...makeBill(), claims: [claimFor(1, "Jeanne Dupont"), claimFor(2, "Marc Roy", { total_amount: null })] }),
      ),
    );
    const { user } = renderPage();
    await openBills(user);
    await user.click(await screen.findByRole("button", { name: "Détails" }));
    const jeanne = (await screen.findByText("Jeanne Dupont")).closest("li")!;
    expect(jeanne).toHaveTextContent("01/10/2026Jeanne Dupont0010151,00 $");
    expect(screen.getByText("Marc Roy").closest("li")).toHaveTextContent(/Marc Roy00102$/);
    await user.click(screen.getByRole("button", { name: "Détails" }));
    expect(screen.queryByText("Jeanne Dupont")).not.toBeInTheDocument();
  });

  it("shows why a bill's details could not be loaded", async () => {
    serveClaims([]);
    serveBills([makeBill()]);
    server.use(http.get("/api/bills/1", () => HttpResponse.json({ detail: "Facture introuvable" }, { status: 404 })));
    const { user } = renderPage();
    await openBills(user);
    await user.click(await screen.findByRole("button", { name: "Détails" }));
    expect(await screen.findByText("Facture introuvable")).toBeInTheDocument();
  });

  it("asks first, deletes the bill, re-reads it and releases the claims on the other tab", async () => {
    let bills = [makeBill()];
    serveBills(() => bills);
    let claims = [claimFor(1, "Jeanne Dupont", { status: "soumis", bill_id: 1 })];
    const claimRequests = serveClaims(() => claims);
    server.use(
      http.delete("/api/bills/1", () => {
        bills = [];
        claims = [claimFor(1, "Jeanne Dupont")];
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderPage();
    await openBills(user);
    await pickRowAction(user, "Actions — facture F-2026-0001", "Supprimer");
    expect(await screen.findByRole("dialog", { name: "Supprimer la facture F-2026-0001 ?" })).toHaveTextContent(
      "Les 2 réclamation(s) qu'elle contient redeviendront des brouillons.",
    );
    await answer(user, "Supprimer");
    expect(await screen.findByText("Aucune facture générée.")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Réclamations" }));
    expect(await within((await screen.findByText("Jeanne Dupont")).closest("tr")!).findByText("Brouillon")).toBeInTheDocument();
    expect(claimRequests.length).toBeGreaterThan(1);
  });

  it("does nothing when the physician declines", async () => {
    serveClaims([]);
    serveBills([makeBill()]);
    const onDelete = vi.fn();
    server.use(http.delete("/api/bills/1", () => (onDelete(), new HttpResponse(null, { status: 204 }))));
    const { user } = renderPage();
    await openBills(user);
    await pickRowAction(user, "Actions — facture F-2026-0001", "Supprimer");
    await answer(user, "Annuler");
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("shows the server's refusal and keeps the list", async () => {
    serveClaims([]);
    serveBills([makeBill()]);
    server.use(http.delete("/api/bills/1", () => HttpResponse.json({ detail: "Facture déjà transmise" }, { status: 409 })));
    const { user } = renderPage();
    await openBills(user);
    await pickRowAction(user, "Actions — facture F-2026-0001", "Supprimer");
    await answer(user, "Supprimer");
    expect(await screen.findByText("Facture déjà transmise")).toBeInTheDocument();
    expect(screen.getByText("F-2026-0001")).toBeInTheDocument();
  });
});

describe("billing from the list", () => {
  const selectionBar = () => screen.getByRole("region", { name: "Sélection" });

  it("ticks only drafts, totals them and posts them with the period they span", async () => {
    serveClaims([
      claimFor(1, "Jeanne Dupont", { service_date: "2026-10-01" }),
      claimFor(2, "Marc Roy", { service_date: "2026-10-05" }),
      claimFor(3, "Lise Tremblay", { service_date: "2026-10-03", total_amount: null }),
      claimFor(4, "Paul Gagnon", { status: "soumis", bill_id: 1 }),
    ]);
    let body: unknown;
    server.use(
      http.post("/api/bills", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(makeBill({ number: "F-2026-0009" }));
      }),
    );
    const { user } = renderPage();
    await screen.findByText("Marc Roy");
    expect(screen.queryByLabelText("Sélectionner la réclamation de Paul Gagnon")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Sélection" })).not.toBeInTheDocument();

    await user.click(screen.getByLabelText("Sélectionner la réclamation de Marc Roy"));
    await user.click(screen.getByLabelText("Sélectionner la réclamation de Lise Tremblay"));
    expect(selectionBar()).toHaveTextContent("2 réclamations sélectionnées · 52,00 $ · du 03/10/2026 au 05/10/2026");

    await user.click(within(selectionBar()).getByRole("button", { name: "Générer la facture" }));
    await waitFor(() => expect(body).toEqual({ start_date: "2026-10-03", end_date: "2026-10-05", claim_ids: [2, 3] }));
    expect(await screen.findByText("Facture F-2026-0009 générée.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Sélection" })).not.toBeInTheDocument();
    // The physician stays on the claims, to keep billing.
    expect(screen.getByRole("tab", { name: "Réclamations" })).toHaveAttribute("aria-selected", "true");
  });

  it("ticks every draft shown with the header box, and only those", async () => {
    serveClaims([
      claimFor(1, "Jeanne Dupont"),
      claimFor(2, "Marc Roy"),
      claimFor(3, "Paul Gagnon", { status: "soumis", bill_id: 1 }),
    ]);
    const { user } = renderPage();
    await screen.findByText("Marc Roy");
    await user.type(screen.getByLabelText("Patient"), "marc");
    await user.click(screen.getByLabelText("Sélectionner tous les brouillons"));
    expect(selectionBar()).toHaveTextContent(/^1 réclamation sélectionnée/);
    // Jeanne, filtered out of view, isn't billed — even once ticked and hidden again.
    await user.clear(screen.getByLabelText("Patient"));
    expect(screen.getByLabelText("Sélectionner la réclamation de Jeanne Dupont")).not.toBeChecked();
    await user.click(screen.getByLabelText("Sélectionner tous les brouillons"));
    expect(selectionBar()).toHaveTextContent(/^2 réclamations sélectionnées/);
    await user.click(screen.getByLabelText("Sélectionner tous les brouillons"));
    expect(screen.queryByRole("region", { name: "Sélection" })).not.toBeInTheDocument();
  });

  it("'Créer une facture' shows the drafts, all ticked", async () => {
    serveClaims([claimFor(1, "Jeanne Dupont"), claimFor(2, "Paul Gagnon", { status: "soumis", bill_id: 1 })]);
    const { user } = renderPage("/app/facturation?tab=factures");
    serveBills([]);
    await user.click(screen.getByRole("button", { name: "Créer une facture" }));
    expect(await screen.findByLabelText("Sélectionner la réclamation de Jeanne Dupont")).toBeChecked();
    expect(screen.getByRole("tab", { name: /Brouillons/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByText("Paul Gagnon")).not.toBeInTheDocument();
    expect(selectionBar()).toHaveTextContent(/^1 réclamation sélectionnée/);
  });

  it("lands with every draft ticked from the dashboard's link", async () => {
    serveClaims([claimFor(1, "Jeanne Dupont"), claimFor(2, "Marc Roy")]);
    renderPage("/app/facturation?bill=1");
    expect(await screen.findByLabelText("Sélectionner la réclamation de Marc Roy")).toBeChecked();
    expect(selectionBar()).toHaveTextContent(/^2 réclamations sélectionnées/);
  });

  it("says when there is no draft to bill", async () => {
    serveClaims([claimFor(1, "Paul Gagnon", { status: "soumis", bill_id: 1 })]);
    const { user } = renderPage();
    await screen.findByText("Paul Gagnon");
    await user.click(screen.getByRole("button", { name: "Créer une facture" }));
    expect(await screen.findByText("Aucune réclamation en brouillon à facturer pour cette période.")).toBeInTheDocument();
  });

  it("re-reads the list and clears the selection when a claim is no longer available (409)", async () => {
    let claims = [claimFor(1, "Jeanne Dupont"), claimFor(2, "Marc Roy")];
    serveClaims(() => claims);
    server.use(
      http.post("/api/bills", () => {
        claims = [claimFor(1, "Jeanne Dupont", { status: "soumis", bill_id: 3 }), claimFor(2, "Marc Roy")];
        return HttpResponse.json({ detail: "Réclamation 1 déjà facturée." }, { status: 409 });
      }),
    );
    const { user } = renderPage();
    await screen.findByText("Jeanne Dupont");
    await user.click(screen.getByLabelText("Sélectionner tous les brouillons"));
    await user.click(within(selectionBar()).getByRole("button", { name: "Générer la facture" }));
    expect(
      await screen.findByText("Réclamation 1 déjà facturée. La liste a été mise à jour, veuillez vérifier votre sélection."),
    ).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByLabelText("Sélectionner la réclamation de Jeanne Dupont")).not.toBeInTheDocument());
    expect(screen.getByLabelText("Sélectionner la réclamation de Marc Roy")).not.toBeChecked();
  });

  it("shows any other error and keeps the selection", async () => {
    serveClaims([claimFor(1, "Jeanne Dupont")]);
    server.use(http.post("/api/bills", () => HttpResponse.json({ detail: "Erreur interne" }, { status: 500 })));
    const { user } = renderPage();
    await user.click(await screen.findByLabelText("Sélectionner la réclamation de Jeanne Dupont"));
    await user.click(within(selectionBar()).getByRole("button", { name: "Générer la facture" }));
    expect(await within(selectionBar()).findByText("Erreur interne")).toBeInTheDocument();
    expect(within(selectionBar()).getByRole("button", { name: "Générer la facture" })).toBeEnabled();
  });
});
