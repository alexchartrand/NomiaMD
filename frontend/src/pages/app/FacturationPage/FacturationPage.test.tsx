import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { makeClaim, makeClaimLine, makePatient } from "../../../test/factories";
import { makeUser, renderWithProviders, serveSession } from "../../../test/render";
import { server } from "../../../test/server";
import type { Bill, Claim } from "../../../api";
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

const renderPage = () => renderWithProviders(<FacturationPage />);

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
    expect(within(manualRow).getByRole("link", { name: "Modifier" })).toHaveAttribute("href", "/app/facturer/1");
    const encounterRow = screen.getByText("Marc Roy").closest("tr")!;
    expect(within(encounterRow).queryByRole("link", { name: "Modifier" })).not.toBeInTheDocument();

    await user.click(within(manualRow).getByRole("button", { name: "Détails" }));
    expect(await screen.findByText("Ajouté manuellement")).toBeInTheDocument();
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
    expect(screen.getByText(/— 50.00 \$ — R = 2/)).toBeInTheDocument();
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
    await user.selectOptions(screen.getByLabelText("Statut"), "brouillon");
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
      expect(screen.getByRole("button", { name: "Supprimer" })).toBeDisabled();
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
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
      const { user } = renderPage();
      await user.click(await screen.findByRole("button", { name: "Supprimer" }));
      expect(confirm).toHaveBeenCalledWith("Supprimer la réclamation de Jeanne Dupont ? Cette action est irréversible.");
      expect(await screen.findByText("Aucune réclamation enregistrée.")).toBeInTheDocument();
      expect(deleted).toBe("1");
      confirm.mockRestore();
    });

    it("does nothing when the physician declines", async () => {
      serveClaims([claimFor(1, "Jeanne Dupont")]);
      const onDelete = vi.fn();
      server.use(http.delete("/api/claims/:id", () => (onDelete(), new HttpResponse(null, { status: 204 }))));
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      const { user } = renderPage();
      await user.click(await screen.findByRole("button", { name: "Supprimer" }));
      expect(onDelete).not.toHaveBeenCalled();
      expect(screen.getByText("Jeanne Dupont")).toBeInTheDocument();
      confirm.mockRestore();
    });

    it("shows the server's refusal and keeps the claim", async () => {
      serveClaims([claimFor(1, "Jeanne Dupont")]);
      server.use(http.delete("/api/claims/:id", () => HttpResponse.json({ detail: "Déjà sur une facture" }, { status: 409 })));
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
      const { user } = renderPage();
      await user.click(await screen.findByRole("button", { name: "Supprimer" }));
      expect(await screen.findByText("Déjà sur une facture")).toBeInTheDocument();
      expect(screen.getByText("Jeanne Dupont")).toBeInTheDocument();
      confirm.mockRestore();
    });
  });
});

describe("generated bills tab", () => {
  async function openBills(user: ReturnType<typeof renderPage>["user"]) {
    await user.click(screen.getByRole("button", { name: "Factures générées" }));
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
    expect(await screen.findByText(/Jeanne Dupont — 00101 — 51.00 \$/)).toBeInTheDocument();
    expect(screen.getByText(/Marc Roy — 00102$/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Détails" }));
    expect(screen.queryByText(/Jeanne Dupont — 00101/)).not.toBeInTheDocument();
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
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { user } = renderPage();
    await openBills(user);
    await user.click(await screen.findByRole("button", { name: "Supprimer" }));
    expect(confirm).toHaveBeenCalledWith(
      "Supprimer la facture F-2026-0001 ? Les 2 réclamation(s) qu'elle contient redeviendront des brouillons.",
    );
    expect(await screen.findByText("Aucune facture générée.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Réclamations" }));
    expect(await within((await screen.findByText("Jeanne Dupont")).closest("tr")!).findByText("Brouillon")).toBeInTheDocument();
    expect(claimRequests.length).toBeGreaterThan(1);
    confirm.mockRestore();
  });

  it("does nothing when the physician declines", async () => {
    serveClaims([]);
    serveBills([makeBill()]);
    const onDelete = vi.fn();
    server.use(http.delete("/api/bills/1", () => (onDelete(), new HttpResponse(null, { status: 204 }))));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { user } = renderPage();
    await openBills(user);
    await user.click(await screen.findByRole("button", { name: "Supprimer" }));
    expect(onDelete).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("shows the server's refusal and keeps the list", async () => {
    serveClaims([]);
    serveBills([makeBill()]);
    server.use(http.delete("/api/bills/1", () => HttpResponse.json({ detail: "Facture déjà transmise" }, { status: 409 })));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { user } = renderPage();
    await openBills(user);
    await user.click(await screen.findByRole("button", { name: "Supprimer" }));
    expect(await screen.findByText("Facture déjà transmise")).toBeInTheDocument();
    expect(screen.getByText("F-2026-0001")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Supprimer" })).toBeInTheDocument();
    confirm.mockRestore();
  });
});

describe("creating a bill", () => {
  async function openModal(user: ReturnType<typeof renderPage>["user"]) {
    await user.click(screen.getByRole("button", { name: "Créer une facture" }));
    return screen.findByRole("dialog");
  }

  async function search(user: ReturnType<typeof renderPage>["user"], dialog: HTMLElement, from = "2026-10-01", to = "2026-10-07") {
    if (from) await user.type(within(dialog).getByLabelText("Du"), from);
    if (to) await user.type(within(dialog).getByLabelText("Au"), to);
    await user.click(within(dialog).getByRole("button", { name: "Rechercher" }));
  }

  it("requires both dates, in order", async () => {
    serveClaims([]);
    const { user } = renderPage();
    const dialog = await openModal(user);
    await search(user, dialog, "", "");
    expect(within(dialog).getByText("Les deux dates sont requises.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Du"), "2026-10-09");
    await user.type(within(dialog).getByLabelText("Au"), "2026-10-01");
    await user.click(within(dialog).getByRole("button", { name: "Rechercher" }));
    expect(within(dialog).getByText("La date de début doit précéder la date de fin.")).toBeInTheDocument();
  });

  it("searches the period's unbilled drafts, first page of up to 200", async () => {
    const requests = serveClaims(() => []);
    const { user } = renderPage();
    const dialog = await openModal(user);
    await search(user, dialog);
    expect(await within(dialog).findByText("Aucune facturation non soumise dans cette période.")).toBeInTheDocument();
    expect(Object.fromEntries(requests[requests.length - 1])).toEqual({
      date_from: "2026-10-01",
      date_to: "2026-10-07",
      status: "brouillon",
      limit: "200",
      offset: "0",
    });
  });

  it("reads further pages when a page is full, so no claim is silently dropped", async () => {
    const full = Array.from({ length: 200 }, (_, i) => claimFor(i + 1, `Patient ${i + 1}`));
    const requests = serveClaims((params) => (params.get("offset") === "0" ? full : [claimFor(201, "Patient 201")]));
    const { user } = renderPage();
    const dialog = await openModal(user);
    await search(user, dialog);
    expect(await within(dialog).findByLabelText("Sélectionner la facturation de Patient 201")).toBeInTheDocument();
    const offsets = requests.map((r) => r.get("offset")).filter((o) => o !== null);
    expect(offsets).toEqual(["0", "200"]);
  });

  it("totals the selection, with select-all, and posts the chosen claim ids", async () => {
    serveClaims((params) => (params.has("limit") ? [claimFor(1, "Jeanne Dupont"), claimFor(2, "Marc Roy"), claimFor(3, "Lise Tremblay", { total_amount: null })] : []));
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
    await search(user, dialog);
    expect(within(dialog).getByRole("button", { name: "Générer la facture" })).toBeDisabled();
    await user.click(await within(dialog).findByLabelText("Sélectionner la facturation de Jeanne Dupont"));
    await user.click(within(dialog).getByLabelText("Sélectionner la facturation de Marc Roy"));
    expect(within(dialog).getByText("2 facturation(s) sélectionnée(s) — total 103,00 $")).toBeInTheDocument();
    await user.click(within(dialog).getByLabelText("Tout sélectionner"));
    expect(within(dialog).getByText("3 facturation(s) sélectionnée(s) — total 103,00 $")).toBeInTheDocument();
    await user.click(within(dialog).getByLabelText("Tout sélectionner"));
    expect(within(dialog).getByText("0 facturation(s) sélectionnée(s) — total 0,00 $")).toBeInTheDocument();
    await user.click(within(dialog).getByLabelText("Sélectionner la facturation de Marc Roy"));
    await user.click(within(dialog).getByLabelText("Sélectionner la facturation de Lise Tremblay"));
    await user.click(within(dialog).getByRole("button", { name: "Générer la facture" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(body).toEqual({ start_date: "2026-10-01", end_date: "2026-10-07", claim_ids: [2, 3] });
    // …and the page moved to the generated bills.
    expect(await screen.findByText("F-2026-0001")).toBeInTheDocument();
  });

  it("refreshes the list and clears the selection when a claim is no longer available (409)", async () => {
    let claims = [claimFor(1, "Jeanne Dupont"), claimFor(2, "Marc Roy")];
    serveClaims((params) => (params.has("limit") ? claims : []));
    server.use(
      http.post("/api/bills", () => {
        claims = [claimFor(2, "Marc Roy")];
        return HttpResponse.json({ detail: "Réclamation 1 déjà facturée." }, { status: 409 });
      }),
    );
    const { user } = renderPage();
    const dialog = await openModal(user);
    await search(user, dialog);
    await user.click(await within(dialog).findByLabelText("Tout sélectionner"));
    await user.click(within(dialog).getByRole("button", { name: "Générer la facture" }));
    expect(
      await within(dialog).findByText("Réclamation 1 déjà facturée. La liste a été mise à jour, veuillez vérifier votre sélection."),
    ).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).queryByLabelText("Sélectionner la facturation de Jeanne Dupont")).not.toBeInTheDocument());
    expect(within(dialog).getByText(/^0 facturation\(s\)/)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows any other error and keeps the selection", async () => {
    serveClaims((params) => (params.has("limit") ? [claimFor(1, "Jeanne Dupont")] : []));
    server.use(http.post("/api/bills", () => HttpResponse.json({ detail: "Erreur interne" }, { status: 500 })));
    const { user } = renderPage();
    const dialog = await openModal(user);
    await search(user, dialog);
    await user.click(await within(dialog).findByLabelText("Tout sélectionner"));
    await user.click(within(dialog).getByRole("button", { name: "Générer la facture" }));
    expect(await within(dialog).findByText("Erreur interne")).toBeInTheDocument();
    expect(within(dialog).getByText(/^1 facturation\(s\)/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Générer la facture" })).toBeEnabled();
  });

  it("shows a search error", async () => {
    server.use(http.get("/api/claims", () => HttpResponse.json({ detail: "Erreur de recherche" }, { status: 500 })));
    const { user } = renderPage();
    const dialog = await openModal(user);
    await search(user, dialog);
    expect(await within(dialog).findByText("Erreur de recherche")).toBeInTheDocument();
  });
});
