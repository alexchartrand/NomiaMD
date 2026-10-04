import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { makePatient } from "../test/factories";
import { server } from "../test/server";
import type { Patient } from "../api";
import { PatientSearchSelect } from "./PatientSearchSelect";

// Holds the selection the way the real call sites do (the component is controlled).
function Harness({ onSelect, initial = null }: { onSelect: (patient: Patient | null) => void; initial?: Patient | null }) {
  const [selected, setSelected] = useState<Patient | null>(initial);
  return (
    <>
      <PatientSearchSelect
        selected={selected}
        onSelect={(patient) => {
          setSelected(patient);
          onSelect(patient);
        }}
      />
      <button type="button">ailleurs</button>
    </>
  );
}

const dupont = makePatient({ id: 1, full_name: "Jeanne Dupont", ramq_number: "TEST11111111" });
const roy = makePatient({ id: 2, full_name: "Marc Roy", ramq_number: null });

function serveSearch(found: Patient[] | (() => Patient[])) {
  const queries: string[] = [];
  server.use(
    http.get("/api/patients/search", ({ request }) => {
      queries.push(new URL(request.url).searchParams.get("q")!);
      return HttpResponse.json(typeof found === "function" ? found() : found);
    }),
  );
  return queries;
}

const input = () => screen.getByPlaceholderText("Nom ou NAM du patient...");

describe("PatientSearchSelect", () => {
  it("does not search, nor open, below two characters", async () => {
    const queries = serveSearch([dupont]);
    const user = userEvent.setup();
    render(<Harness onSelect={vi.fn()} />);
    await user.type(input(), "D");
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(queries).toEqual([]);
    expect(screen.queryByText("Aucun patient trouvé")).not.toBeInTheDocument();
    await user.type(input(), "   ");
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(queries).toEqual([]);
  });

  it("waits for a pause in typing: one request for the whole query", async () => {
    const queries = serveSearch([dupont]);
    const user = userEvent.setup();
    render(<Harness onSelect={vi.fn()} />);
    await user.type(input(), "Dupont");
    expect(await screen.findByRole("button", { name: /Jeanne Dupont/ })).toBeInTheDocument();
    expect(queries).toEqual(["Dupont"]);
  });

  it("lists the matches with their NAM when there is one", async () => {
    serveSearch([dupont, roy]);
    const user = userEvent.setup();
    render(<Harness onSelect={vi.fn()} />);
    await user.type(input(), "ro");
    expect(await screen.findByRole("button", { name: /Jeanne Dupont.*TEST11111111/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Marc Roy" })).toBeInTheDocument();
  });

  it("shows a searching state, then 'no patient' when nothing matches", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    server.use(
      http.get("/api/patients/search", async () => {
        await gate;
        return HttpResponse.json([]);
      }),
    );
    const user = userEvent.setup();
    render(<Harness onSelect={vi.fn()} />);
    await user.type(input(), "zz");
    expect(await screen.findByText("Recherche...")).toBeInTheDocument();
    release();
    expect(await screen.findByText("Aucun patient trouvé")).toBeInTheDocument();
  });

  it("shows the search error instead of 'no patient'", async () => {
    server.use(http.get("/api/patients/search", () => HttpResponse.json({ detail: "Recherche indisponible" }, { status: 500 })));
    const user = userEvent.setup();
    render(<Harness onSelect={vi.fn()} />);
    await user.type(input(), "zz");
    expect(await screen.findByText("Recherche indisponible")).toBeInTheDocument();
    expect(screen.queryByText("Aucun patient trouvé")).not.toBeInTheDocument();
  });

  it("picking a match selects it, fills the field and closes the list", async () => {
    serveSearch([dupont, roy]);
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSelect={onSelect} />);
    await user.type(input(), "ro");
    await user.click(await screen.findByRole("button", { name: "Marc Roy" }));
    expect(onSelect).toHaveBeenCalledWith(roy);
    expect(input()).toHaveValue("Marc Roy");
    expect(screen.queryByRole("button", { name: /Jeanne Dupont/ })).not.toBeInTheDocument();
  });

  it("editing the field after a pick clears the selection", async () => {
    serveSearch([dupont]);
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSelect={onSelect} initial={dupont} />);
    expect(input()).toHaveValue("Jeanne Dupont");
    await user.type(input(), "x");
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });

  it("does not search again once a patient is selected", async () => {
    const queries = serveSearch([dupont]);
    render(<Harness onSelect={vi.fn()} initial={dupont} />);
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(queries).toEqual([]);
  });

  it("closes the list on a click elsewhere and reopens it on focus", async () => {
    serveSearch([dupont]);
    const user = userEvent.setup();
    render(<Harness onSelect={vi.fn()} />);
    await user.type(input(), "Dup");
    await screen.findByRole("button", { name: /Jeanne Dupont/ });
    await user.click(screen.getByRole("button", { name: "ailleurs" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Jeanne Dupont/ })).not.toBeInTheDocument());
    await user.click(input());
    expect(await screen.findByRole("button", { name: /Jeanne Dupont/ })).toBeInTheDocument();
  });
});
