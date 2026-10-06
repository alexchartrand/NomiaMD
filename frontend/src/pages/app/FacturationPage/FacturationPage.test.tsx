import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { makeClaim, makeClaimLine, makePatient } from "../../../test/factories";
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
  serveSession(makeUser());
  server.use(http.get("/api/patients", () => HttpResponse.json([makePatient({ id: 4, full_name: "Roster Patient" })])));
});

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

const renderPage = (route = "/app/facturation") =>
  renderWithProviders(
    <Routes>
      <Route path="/app/facturation" element={<FacturationPage />} />
      <Route path="/app/facturer/:claimId" element={<FacturerStub />} />
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

  it("says when there is nothing, and shows a loading error", async () => {
    serveClaims([]);
    renderPage();
    expect(await screen.findByText("Aucune réclamation enregistrée.")).toBeInTheDocument();
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

  it("sends the filters to the server", async () => {
    const requests = serveClaims([claimFor(1, "Jeanne Dupont")]);
    const { user } = renderPage();
    await screen.findByText("Jeanne Dupont");
    expect(requests[0].size).toBe(0);
    await screen.findByRole("option", { name: "Roster Patient" });
    await user.selectOptions(screen.getByLabelText("Patient"), "4");
    await user.type(screen.getByLabelText("Du"), "2026-10-01");
    await user.type(screen.getByLabelText("Au"), "2026-10-31");
    await user.click(within(screen.getByRole("group", { name: "Statut" })).getByRole("button", { name: "Brouillons" }));
    await waitFor(() =>
      expect(Object.fromEntries(requests[requests.length - 1])).toEqual({
        patient_id: "4",
        date_from: "2026-10-01",
        date_to: "2026-10-31",
        status: "brouillon",
      }),
    );
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
      expect(await screen.findByText("Aucune réclamation enregistrée.")).toBeInTheDocument();
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

describe("creating a bill", () => {
  async function openModal(user: ReturnType<typeof renderPage>["user"]) {
    await user.click(screen.getByRole("button", { name: "Créer une facture" }));
    return screen.findByRole("dialog");
  }

  // Drafts served to the dialog's paged read (it always sends `limit`); the tab behind it
  // gets none.
  const serveDrafts = (drafts: () => Claim[]) =>
    serveClaims((params) => (params.has("limit") ? drafts() : []));

  async function setDate(user: ReturnType<typeof renderPage>["user"], field: HTMLElement, value: string) {
    await user.clear(field);
    if (value) await user.type(field, value);
  }

  it("loads every draft page by page, with the period covering them, all ticked", async () => {
    const full = Array.from({ length: 200 }, (_, i) => claimFor(i + 1, `Patient ${i + 1}`));
    const requests = serveClaims((params) =>
      !params.has("limit") ? [] : params.get("offset") === "0" ? full : [claimFor(201, "Patient 201", { service_date: "2026-10-09" })],
    );
    const { user } = renderPage();
    const dialog = await openModal(user);
    expect(await within(dialog).findByLabelText("Sélectionner la facturation de Patient 201")).toBeChecked();
    const reads = requests.filter((r) => r.has("limit")).map((r) => Object.fromEntries(r));
    expect(reads).toEqual([
      { status: "brouillon", limit: "200", offset: "0" },
      { status: "brouillon", limit: "200", offset: "200" },
    ]);
    expect(within(dialog).getByLabelText("Du")).toHaveValue("2026-10-01");
    expect(within(dialog).getByLabelText("Au")).toHaveValue("2026-10-09");
    expect(within(dialog).getByText(/^201 facturation\(s\) sélectionnée\(s\)/)).toBeInTheDocument();
  });

  it("narrows to a period, ticking what's in it, and requires both dates in order", async () => {
    serveDrafts(() => [
      claimFor(1, "Jeanne Dupont", { service_date: "2026-10-01" }),
      claimFor(2, "Marc Roy", { service_date: "2026-10-05" }),
      claimFor(3, "Lise Tremblay", { service_date: "2026-10-09" }),
    ]);
    const { user } = renderPage();
    const dialog = await openModal(user);
    await within(dialog).findByText("Lise Tremblay");
    await setDate(user, within(dialog).getByLabelText("Au"), "2026-10-05");
    expect(within(dialog).queryByText("Lise Tremblay")).not.toBeInTheDocument();
    expect(within(dialog).getByText("2 facturation(s) sélectionnée(s) — total 103,00 $")).toBeInTheDocument();

    await setDate(user, within(dialog).getByLabelText("Du"), "2026-10-07");
    expect(within(dialog).getByText("La date de début doit précéder la date de fin.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Générer la facture" })).toBeDisabled();
    await setDate(user, within(dialog).getByLabelText("Du"), "");
    expect(within(dialog).getByText("Les deux dates sont requises.")).toBeInTheDocument();
  });

  it("says when there is no draft to bill", async () => {
    serveDrafts(() => []);
    const { user } = renderPage();
    const dialog = await openModal(user);
    expect(await within(dialog).findByText("Aucune réclamation en brouillon à facturer.")).toBeInTheDocument();
  });

  it("totals the selection, with select-all, and posts the chosen claim ids", async () => {
    serveDrafts(() => [claimFor(1, "Jeanne Dupont"), claimFor(2, "Marc Roy"), claimFor(3, "Lise Tremblay", { total_amount: null })]);
    let body: unknown;
    server.use(
      http.post("/api/bills", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(makeBill());
      }),
    );
    serveBills([makeBill()]);
    const { user } = renderPage();
    const dialog = await openModal(user);
    expect(await within(dialog).findByText("3 facturation(s) sélectionnée(s) — total 103,00 $")).toBeInTheDocument();
    await user.click(within(dialog).getByLabelText("Tout sélectionner"));
    expect(within(dialog).getByText("0 facturation(s) sélectionnée(s) — total 0,00 $")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Générer la facture" })).toBeDisabled();
    await user.click(within(dialog).getByLabelText("Sélectionner la facturation de Marc Roy"));
    await user.click(within(dialog).getByLabelText("Sélectionner la facturation de Lise Tremblay"));
    expect(within(dialog).getByText("2 facturation(s) sélectionnée(s) — total 52,00 $")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Générer la facture" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(body).toEqual({ start_date: "2026-10-01", end_date: "2026-10-01", claim_ids: [2, 3] });
    // …and the page moved to the generated bills.
    expect(await screen.findByText("F-2026-0001")).toBeInTheDocument();
    expect(screen.getByText("Facture générée.")).toBeInTheDocument();
  });

  it("opens straight away from a link (the dashboard's drafts task)", async () => {
    serveDrafts(() => [claimFor(1, "Jeanne Dupont")]);
    renderPage("/app/facturation?bill=1");
    const dialog = await screen.findByRole("dialog", { name: "Créer une facture" });
    expect(await within(dialog).findByText("Jeanne Dupont")).toBeInTheDocument();
  });

  it("refreshes the list and clears the selection when a claim is no longer available (409)", async () => {
    let claims = [claimFor(1, "Jeanne Dupont"), claimFor(2, "Marc Roy")];
    serveDrafts(() => claims);
    server.use(
      http.post("/api/bills", () => {
        claims = [claimFor(2, "Marc Roy")];
        return HttpResponse.json({ detail: "Réclamation 1 déjà facturée." }, { status: 409 });
      }),
    );
    const { user } = renderPage();
    const dialog = await openModal(user);
    await within(dialog).findByText("Jeanne Dupont");
    await user.click(within(dialog).getByRole("button", { name: "Générer la facture" }));
    expect(
      await within(dialog).findByText("Réclamation 1 déjà facturée. La liste a été mise à jour, veuillez vérifier votre sélection."),
    ).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).queryByLabelText("Sélectionner la facturation de Jeanne Dupont")).not.toBeInTheDocument());
    expect(within(dialog).getByText(/^0 facturation\(s\)/)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows any other error and keeps the selection", async () => {
    serveDrafts(() => [claimFor(1, "Jeanne Dupont")]);
    server.use(http.post("/api/bills", () => HttpResponse.json({ detail: "Erreur interne" }, { status: 500 })));
    const { user } = renderPage();
    const dialog = await openModal(user);
    await within(dialog).findByText("Jeanne Dupont");
    await user.click(within(dialog).getByRole("button", { name: "Générer la facture" }));
    expect(await within(dialog).findByText("Erreur interne")).toBeInTheDocument();
    expect(within(dialog).getByText(/^1 facturation\(s\)/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Générer la facture" })).toBeEnabled();
  });

  it("shows why the drafts could not be loaded", async () => {
    server.use(http.get("/api/claims", () => HttpResponse.json({ detail: "Erreur de lecture" }, { status: 500 })));
    const { user } = renderPage();
    const dialog = await openModal(user);
    expect(await within(dialog).findByText("Erreur de lecture")).toBeInTheDocument();
  });
});
