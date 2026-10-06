import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes, useLocation } from "react-router-dom";
import { makeUser, renderWithProviders, serveSession } from "../../test/render";
import { server } from "../../test/server";
import type { ReceiveOutcome } from "../../api";
import AddNotesPage from "./AddNotesPage";

const outcome = (overrides: Partial<ReceiveOutcome> = {}): ReceiveOutcome => ({
  outcome: "new",
  encounter_id: 1,
  patient_id: 1,
  enqueued: true,
  ...overrides,
});

// Stands in for the inbox: shows where we landed and the "received" summary handed over.
function InboxStub() {
  const location = useLocation();
  const received = (location.state as { received?: unknown } | null)?.received;
  return (
    <>
      <p data-testid="landed">{location.pathname + location.search}</p>
      <p data-testid="received">{JSON.stringify(received)}</p>
    </>
  );
}

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/app/ajouter" element={<AddNotesPage />} />
      <Route path="/app/inbox" element={<InboxStub />} />
    </Routes>,
    { route: "/app/ajouter" },
  );
}

beforeEach(() => {
  serveSession(makeUser());
  // The Epic sandbox demo is off by default (404): its tab stays hidden.
  server.use(http.get("/api/intake/epic-sandbox", () => new HttpResponse(null, { status: 404 })));
});

const submit = () => screen.getByRole("button", { name: "Ajouter aux rencontres" });

describe("pasting notes", () => {
  it("cannot be submitted while empty or blank", async () => {
    const { user } = renderPage();
    expect(submit()).toBeDisabled();
    await user.type(screen.getByLabelText("Notes à ajouter"), "   ");
    expect(submit()).toBeDisabled();
  });

  it("sends the text and the trimmed batch label, then lands on the inbox with a summary", async () => {
    let body: unknown;
    server.use(
      http.post("/api/intake/notes", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json([outcome(), outcome({ encounter_id: 2 }), outcome({ outcome: "duplicate", encounter_id: 3 })]);
      }),
    );
    const { user } = renderPage();
    await user.type(screen.getByLabelText("Notes à ajouter"), "**NAM :** TEST12345678 note");
    await user.type(screen.getByLabelText("Lot (facultatif)"), "  Urgence nuit  ");
    await user.click(submit());
    expect(await screen.findByTestId("landed")).toHaveTextContent("/app/inbox");
    expect(body).toEqual({ text: "**NAM :** TEST12345678 note", batch_label: "Urgence nuit" });
    expect(JSON.parse(screen.getByTestId("received").textContent!)).toEqual({ received: 2, duplicates: 1 });
  });

  it("sends no label when the field is blank", async () => {
    let body: { batch_label?: string | null } = {};
    server.use(
      http.post("/api/intake/notes", async ({ request }) => {
        body = (await request.json()) as typeof body;
        return HttpResponse.json([outcome()]);
      }),
    );
    const { user } = renderPage();
    await user.type(screen.getByLabelText("Notes à ajouter"), "note");
    await user.type(screen.getByLabelText("Lot (facultatif)"), "   ");
    await user.click(submit());
    await screen.findByTestId("landed");
    expect(body.batch_label).toBeNull();
  });

  it("shows the server's error, stays on the page and can be retried", async () => {
    server.use(http.post("/api/intake/notes", () => HttpResponse.json({ detail: "Aucune note reconnue" }, { status: 422 })));
    const { user } = renderPage();
    await user.type(screen.getByLabelText("Notes à ajouter"), "note");
    await user.click(submit());
    expect(await screen.findByText("Aucune note reconnue")).toBeInTheDocument();
    expect(screen.queryByTestId("landed")).not.toBeInTheDocument();
    expect(submit()).toBeEnabled();
  });

  it("is disabled with a progress label while the server works", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    server.use(
      http.post("/api/intake/notes", async () => {
        await gate;
        return HttpResponse.json([outcome()]);
      }),
    );
    const { user } = renderPage();
    await user.type(screen.getByLabelText("Notes à ajouter"), "note");
    await user.click(submit());
    expect(await screen.findByRole("button", { name: "Réception et extraction en cours…" })).toBeDisabled();
    release();
    await screen.findByTestId("landed");
  });
});

describe("uploading a file", () => {
  async function chooseFile(user: ReturnType<typeof renderPage>["user"], file: File) {
    await user.click(screen.getByRole("tab", { name: "Téléverser un fichier" }));
    expect(submit()).toBeDisabled();
    expect(screen.getByText("Aucun fichier choisi")).toBeInTheDocument();
    await user.upload(document.getElementById("notes-file") as HTMLInputElement, file);
  }

  it("uploads the file with the batch label as multipart", async () => {
    // jsdom's FormData doesn't stream into Node's fetch, so the body can't be parsed here:
    // only the multipart content type is checked, not the file or label inside.
    let contentType: string | null = null;
    server.use(
      http.post("/api/intake/upload", async ({ request }) => {
        contentType = request.headers.get("content-type");
        return HttpResponse.json([outcome()]);
      }),
    );
    const { user } = renderPage();
    await chooseFile(user, new File(["**NAM :** TEST12345678 note"], "garde.txt", { type: "text/plain" }));
    expect(screen.getByText("garde.txt")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Lot (facultatif)"), "Garde");
    await user.click(submit());
    expect(await screen.findByTestId("landed")).toHaveTextContent("/app/inbox");
    expect(contentType).toMatch(/^multipart\/form-data/);
    expect(JSON.parse(screen.getByTestId("received").textContent!)).toEqual({ received: 1, duplicates: 0 });
  });

  it("shows the server's error (e.g. a file over 2 Mo)", async () => {
    server.use(http.post("/api/intake/upload", () => HttpResponse.json({ detail: "Fichier trop volumineux" }, { status: 413 })));
    const { user } = renderPage();
    await chooseFile(user, new File(["x"], "gros.txt", { type: "text/plain" }));
    await user.click(submit());
    expect(await screen.findByText("Fichier trop volumineux")).toBeInTheDocument();
  });

  it("keeps the pasted text when switching tabs back", async () => {
    const { user } = renderPage();
    await user.type(screen.getByLabelText("Notes à ajouter"), "ma note");
    await user.click(screen.getByRole("tab", { name: "Téléverser un fichier" }));
    await user.click(screen.getByRole("tab", { name: "Coller" }));
    expect(screen.getByLabelText("Notes à ajouter")).toHaveValue("ma note");
  });
});

describe("Epic sandbox demo", () => {
  it("has no Epic tab when the demo is off (404)", async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(2));
    expect(screen.queryByRole("tab", { name: /Epic/ })).not.toBeInTheDocument();
  });

  it("has no Epic tab when the status call fails", async () => {
    server.use(http.get("/api/intake/epic-sandbox", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    renderPage();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole("tab", { name: /Epic/ })).not.toBeInTheDocument();
  });

  it("imports the sandbox notes and lands on the inbox filtered to that source, on every date", async () => {
    server.use(
      http.get("/api/intake/epic-sandbox", () => HttpResponse.json({ patients: 7 })),
      http.post("/api/intake/epic-sandbox/import", () => HttpResponse.json([outcome(), outcome({ outcome: "duplicate" })])),
    );
    const { user } = renderPage();
    await user.click(await screen.findByRole("tab", { name: /Epic/ }));
    expect(screen.getByText(/des 7 patients fictifs/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Notes à ajouter")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Importer les notes" }));
    expect(await screen.findByTestId("landed")).toHaveTextContent("/app/inbox?all=1&source=epic_sandbox");
    expect(JSON.parse(screen.getByTestId("received").textContent!)).toEqual({ received: 1, duplicates: 1 });
  });

  it("disables the import when the sandbox has no patients", async () => {
    server.use(http.get("/api/intake/epic-sandbox", () => HttpResponse.json({ patients: 0 })));
    const { user } = renderPage();
    await user.click(await screen.findByRole("tab", { name: /Epic/ }));
    expect(screen.getByRole("button", { name: "Importer les notes" })).toBeDisabled();
  });

  it("shows an import failure and stays on the page", async () => {
    server.use(
      http.get("/api/intake/epic-sandbox", () => HttpResponse.json({ patients: 7 })),
      http.post("/api/intake/epic-sandbox/import", () => HttpResponse.json({ detail: "Epic indisponible" }, { status: 502 })),
    );
    const { user } = renderPage();
    await user.click(await screen.findByRole("tab", { name: /Epic/ }));
    await user.click(screen.getByRole("button", { name: "Importer les notes" }));
    expect(await screen.findByText("Epic indisponible")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Importer les notes" })).toBeEnabled();
  });
});
