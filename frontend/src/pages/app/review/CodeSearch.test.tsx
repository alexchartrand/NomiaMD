import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { makeCodeHit, makeFee } from "../../../test/factories";
import { server } from "../../../test/server";
import type { CodeHit } from "../../../api";
import { CodeSearch } from "./CodeSearch";

function serveSearch(hits: CodeHit[]) {
  const requests: URLSearchParams[] = [];
  server.use(
    http.get("/api/codes/search", ({ request }) => {
      requests.push(new URL(request.url).searchParams);
      return HttpResponse.json(hits);
    }),
  );
  return requests;
}

const suture = makeCodeHit();
const visit = makeCodeHit({
  number: "15801",
  description: "Visite périodique",
  fees: [makeFee({ amount: 52.4 }), makeFee({ amount: 61.1 })],
  needs_confirmation: ["le statut d'inscription du patient"],
});

describe("CodeSearch", () => {
  it("searches for the patient and date, and offers the codes not already on the claim", async () => {
    const requests = serveSearch([suture, visit]);
    const user = userEvent.setup();
    const onPick = vi.fn();
    render(<CodeSearch onPick={onPick} patientId={7} serviceDate="2026-10-01" excludeNumbers={["00059"]} />);

    await user.type(screen.getByRole("combobox"), "vis");
    const option = await screen.findByRole("option", { name: /15801/ });
    expect(screen.queryByRole("option", { name: /00059/ })).not.toBeInTheDocument();
    expect(Object.fromEntries(requests[requests.length - 1])).toEqual({
      q: "vis",
      patient_id: "7",
      service_date: "2026-10-01",
      limit: "20",
    });
    expect(option).toHaveTextContent("52.40 $ (+1 tarif)");
    expect(option).toHaveTextContent("À confirmer : le statut d'inscription du patient");

    await user.click(option);
    expect(onPick).toHaveBeenCalledWith(visit);
  });

  it("offers the most billed codes before anything is typed", async () => {
    const requests = serveSearch([suture]);
    const user = userEvent.setup();
    render(<CodeSearch onPick={vi.fn()} />);

    await user.click(screen.getByRole("combobox"));
    expect(await screen.findByText("Codes fréquents")).toBeInTheDocument();
    expect(requests[requests.length - 1].has("q")).toBe(false);
    expect(requests[requests.length - 1].has("patient_id")).toBe(false);
  });
});
