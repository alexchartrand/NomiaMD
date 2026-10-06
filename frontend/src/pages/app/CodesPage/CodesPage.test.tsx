import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { makeCodeDetail, makeCodeHit, makeFee } from "../../../test/factories";
import { makeUser, renderWithProviders, serveSession } from "../../../test/render";
import { server } from "../../../test/server";
import CodesPage from ".";
import { eligibilityLines } from "./CodeResult";

const visit = makeCodeHit({
  number: "15801",
  description: "Visite périodique",
  header_path: "B — Consultation > Visites",
  fees: [makeFee({ amount: 52.4, lieux: ["cabinet"] })],
});

beforeEach(() => serveSession(makeUser()));

describe("CodesPage", () => {
  it("searches every code, and opens a code's fees, eligibility and when to use it", async () => {
    const queries: URLSearchParams[] = [];
    server.use(
      http.get("/api/codes/search", ({ request }) => {
        queries.push(new URL(request.url).searchParams);
        return HttpResponse.json([visit]);
      }),
      http.get("/api/codes/15801", () =>
        HttpResponse.json(
          makeCodeDetail({
            ...visit,
            when_to_use: ["Visite périodique d'un patient inscrit"],
            rules: ["Une fois par année"],
            eligibility: { ...makeCodeDetail().eligibility, max_panel_size: 499, requires_registered: true },
          }),
        ),
      ),
    );
    const { user } = renderWithProviders(<CodesPage />);

    await user.type(screen.getByRole("searchbox", { name: "Rechercher un code RAMQ" }), "visite");
    await user.click(await screen.findByRole("button", { name: /15801.*Visite périodique/ }));

    expect(await screen.findByText("Visite périodique d'un patient inscrit")).toBeInTheDocument();
    // Rules aren't shown until their extraction is complete.
    expect(screen.queryByText("Une fois par année")).not.toBeInTheDocument();
    expect(screen.getByText("Clientèle inscrite du médecin : 499 patients ou moins")).toBeInTheDocument();
    expect(screen.getByText("Patient inscrit auprès du médecin")).toBeInTheDocument();
    const last = queries[queries.length - 1];
    expect(last.get("q")).toBe("visite");
    expect(last.has("patient_id")).toBe(false);
  });

  it("offers the physician's frequent codes in a dropdown, and opens the one picked", async () => {
    const queries: URLSearchParams[] = [];
    server.use(
      http.get("/api/codes/search", ({ request }) => {
        const params = new URL(request.url).searchParams;
        queries.push(params);
        return HttpResponse.json([visit]);
      }),
      http.get("/api/codes/15801", () => HttpResponse.json(makeCodeDetail({ ...visit, when_to_use: ["Suivi"] }))),
    );
    const { user } = renderWithProviders(<CodesPage />);

    const dropdown = await screen.findByRole("combobox", { name: "Codes fréquents" });
    // The frequent codes: an empty query, for no patient.
    expect(queries[0].has("q")).toBe(false);
    expect(queries[0].has("patient_id")).toBe(false);
    // Nothing is listed until something is searched or picked.
    expect(screen.queryByRole("button", { name: /15801/ })).not.toBeInTheDocument();

    await user.selectOptions(dropdown, "15801");

    expect(screen.getByRole("searchbox", { name: "Rechercher un code RAMQ" })).toHaveValue("15801");
    expect(await screen.findByText("Suivi")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /15801/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("says when nothing matches", async () => {
    server.use(http.get("/api/codes/search", () => HttpResponse.json([])));
    const { user } = renderWithProviders(<CodesPage />);
    await user.type(screen.getByRole("searchbox", { name: "Rechercher un code RAMQ" }), "zzz");
    expect(await screen.findByText("Aucun code trouvé.")).toBeInTheDocument();
  });
});

describe("eligibilityLines", () => {
  it("states each bound the code has, and nothing for the others", () => {
    expect(
      eligibilityLines({
        min_age: 18,
        max_age: 79,
        min_panel_size: null,
        max_panel_size: null,
        requires_registered: false,
        requires_vulnerable: null,
      }),
    ).toEqual(["Âge du patient : de 18 à 79 ans", "Patient non inscrit auprès du médecin"]);
  });
});
