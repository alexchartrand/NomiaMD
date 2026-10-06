import { fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { makeClaim, makeClaimLine, makeCodeDetail, makeCodeHit, makeFee, makePatient } from "../../../test/factories";
import { makeUser, renderWithProviders, serveSession } from "../../../test/render";
import { server } from "../../../test/server";
import FacturerPage from ".";

const patient = makePatient({ id: 7, full_name: "Jeanne Dupont" });
const suture = makeCodeHit();
const visit = makeCodeHit({
  number: "15801",
  description: "Visite périodique",
  fees: [makeFee({ amount: 52.4, role: 1 }), makeFee({ amount: 61.1, role: 2, context: "À domicile" })],
});

beforeEach(() => {
  serveSession(makeUser());
  server.use(
    http.get("/api/patients/search", () => HttpResponse.json([patient])),
    http.get("/api/patients/7", () => HttpResponse.json(patient)),
    http.get("/api/codes/search", () => HttpResponse.json([suture, visit])),
    http.get("/api/codes/:number", ({ params }) =>
      HttpResponse.json(makeCodeDetail(params.number === "15801" ? visit : suture)),
    ),
  );
});

function captureSaves() {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const handler = async ({ request }: { request: Request }) => {
    calls.push({ method: request.method, path: new URL(request.url).pathname, body: await request.json() });
    return HttpResponse.json(makeClaim({ source_system: "manual" }), { status: 201 });
  };
  server.use(http.post("/api/claims/manual", handler), http.put("/api/claims/manual/:id", handler));
  return calls;
}

// Each pick waits out a debounced search; under a full parallel test run that can take longer
// than findBy*'s default second.
const SLOW = { timeout: 4000 };

async function pickOption(user: ReturnType<typeof renderAt>["user"], field: HTMLElement, name: RegExp) {
  await user.click(field);
  await user.click(await screen.findByRole("option", { name }, SLOW));
}

const codeField = () => screen.getByRole("combobox", { name: "Rechercher un code RAMQ" });

async function pickPatient(user: ReturnType<typeof renderAt>["user"]) {
  await user.type(screen.getByPlaceholderText("Nom ou NAM du patient..."), "Jea");
  await user.click(await screen.findByRole("option", { name: /Jeanne Dupont/ }, SLOW));
}

const renderAt = (route: string) =>
  renderWithProviders(
    <Routes>
      <Route path="/app/facturer" element={<FacturerPage />} />
      <Route path="/app/facturer/:claimId" element={<FacturerPage />} />
      <Route path="/app/facturation" element={<p>Page facturation</p>} />
    </Routes>,
    { route },
  );

describe("FacturerPage", { timeout: 20_000 }, () => {
  it("bills hand-picked codes for a patient, then goes to the claims", async () => {
    const calls = captureSaves();
    const { user } = renderAt("/app/facturer");

    expect(screen.getByText("Choisissez d’abord le patient.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enregistrer la facturation" })).toBeDisabled();

    await pickPatient(user);
    fireEvent.change(screen.getByLabelText("Date du service"), { target: { value: "2026-10-02" } });

    await pickOption(user, codeField(), /15801/);
    await user.selectOptions(screen.getByLabelText("Tarif pour le code 15801"), screen.getByRole("option", { name: /À domicile/ }));
    await pickOption(user, codeField(), /00059/);

    expect(screen.getByText("86.10 $")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Enregistrer la facturation" }));

    expect(await screen.findByText("Page facturation")).toBeInTheDocument();
    expect(calls).toEqual([
      {
        method: "POST",
        path: "/api/claims/manual",
        body: {
          patient_id: 7,
          service_date: "2026-10-02",
          selected_codes: [
            { code: "15801", fee_index: 1 },
            { code: "00059", fee_index: 0 },
          ],
        },
      },
    ]);
  });

  it("adds one of the patient's frequent codes in one click", async () => {
    const searches: URLSearchParams[] = [];
    server.use(
      http.get("/api/codes/search", ({ request }) => {
        searches.push(new URL(request.url).searchParams);
        return HttpResponse.json([suture, visit]);
      }),
    );
    const calls = captureSaves();
    const { user } = renderAt("/app/facturer");
    await pickPatient(user);

    await user.click(await screen.findByRole("button", { name: /Ajouter le code 00059/ }, SLOW));
    // Added: no longer offered, and on the claim.
    expect(screen.queryByRole("button", { name: /Ajouter le code 00059/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retirer le code 00059" })).toBeInTheDocument();
    // The frequent codes are the ones this patient may be billed.
    expect(searches[0].get("patient_id")).toBe("7");
    expect(searches[0].has("q")).toBe(false);

    await user.click(screen.getByRole("button", { name: "Enregistrer la facturation" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toMatchObject({ selected_codes: [{ code: "00059", fee_index: 0 }] });
  });

  it("a removed code is not billed", async () => {
    const calls = captureSaves();
    const { user } = renderAt("/app/facturer");
    await pickPatient(user);
    await pickOption(user, codeField(), /00059/);
    await pickOption(user, codeField(), /15801/);

    await user.click(screen.getByRole("button", { name: "Retirer le code 00059" }));
    await user.click(screen.getByRole("button", { name: "Enregistrer la facturation" }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toMatchObject({ selected_codes: [{ code: "15801", fee_index: 0 }] });
  });

  it("shows the server's refusal and stays on the page", async () => {
    server.use(
      http.post("/api/claims/manual", () =>
        HttpResponse.json({ detail: "Code(s) inexistant(s) ou non admissible(s) pour ce patient : 00059" }, { status: 422 }),
      ),
    );
    const { user } = renderAt("/app/facturer");
    await pickPatient(user);
    await pickOption(user, codeField(), /00059/);
    await user.click(screen.getByRole("button", { name: "Enregistrer la facturation" }));

    expect(await screen.findByText(/non admissible\(s\) pour ce patient : 00059/)).toBeInTheDocument();
  });

  it("edits a draft billed without an encounter: starts from it, and saving replaces it", async () => {
    const calls = captureSaves();
    server.use(
      http.get("/api/claims/12", () =>
        HttpResponse.json(
          makeClaim({
            id: 12,
            patient_id: 7,
            service_date: "2026-09-30",
            source_system: "manual",
            codes: [makeClaimLine({ code: "15801", origin: "manual", confidence: null, fee_amount: 61.1, fee_role: 2, fee_context: "À domicile" })],
          }),
        ),
      ),
    );
    const { user } = renderAt("/app/facturer/12");

    expect(await screen.findByRole("heading", { name: "Modifier une facturation sans rencontre" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Nom ou NAM du patient...")).toHaveValue("Jeanne Dupont");
    expect(screen.getByLabelText("Date du service")).toHaveValue("2026-09-30");
    expect(screen.getByLabelText("Tarif pour le code 15801")).toHaveValue("1");

    await pickOption(user, codeField(), /00059/);
    await user.click(screen.getByRole("button", { name: "Enregistrer les modifications" }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toEqual({
      method: "PUT",
      path: "/api/claims/manual/12",
      body: {
        patient_id: 7,
        service_date: "2026-09-30",
        selected_codes: [
          { code: "15801", fee_index: 1 },
          { code: "00059", fee_index: 0 },
        ],
      },
    });
  });

  it("refuses to edit an encounter's claim here", async () => {
    server.use(http.get("/api/claims/13", () => HttpResponse.json(makeClaim({ id: 13, source_system: "simule" }))));
    renderAt("/app/facturer/13");
    expect(await screen.findByText(/Seule une facturation sans rencontre/)).toBeInTheDocument();
  });
});
