import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { makePatient } from "../../test/factories";
import { makeUser, renderWithProviders, serveSession } from "../../test/render";
import { server } from "../../test/server";
import type { RosterEntry } from "../../api";
import PatientsPage from "./PatientsPage";

const entry = (overrides: Partial<RosterEntry> = {}): RosterEntry => ({ ...makePatient(), notes: null, ...overrides });

const jeanne = entry({
  id: 1,
  full_name: "Jeanne Dupont",
  ramq_number: "TEST11111111",
  date_of_birth: "1980-05-01",
  gender: "F",
  is_vulnerable: true,
  is_registered_with_current_physician: true,
  notes: "Allergique à la pénicilline",
});
const marc = entry({
  id: 2,
  full_name: "Marc Roy",
  ramq_number: null,
  date_of_birth: "1975-12-24",
  gender: null,
  is_vulnerable: false,
  is_registered_with_current_physician: false,
});
const lise = entry({ id: 3, full_name: "Lise Tremblay", is_registered_with_current_physician: null });

// A stateful roster, so reloads after a change show it.
function serveRoster(initial: RosterEntry[]) {
  let roster = initial;
  let loads = 0;
  server.use(
    http.get("/api/patients", () => {
      loads += 1;
      return HttpResponse.json(roster);
    }),
  );
  return { set: (next: RosterEntry[]) => (roster = next), loads: () => loads };
}

function renderPage(role: "physician" | "admin" = "physician") {
  serveSession(makeUser({ role }));
  return renderWithProviders(<PatientsPage />);
}

const rowOf = (name: string) => screen.getByText(name).closest("tr")!;

// A row's ⋯ menu, then one of its items.
async function pickRowAction(user: ReturnType<typeof renderPage>["user"], name: string, item: string) {
  await user.click(await screen.findByRole("button", { name: `Actions — ${name}` }));
  await user.click(await screen.findByRole("menuitem", { name: item }));
}

async function answer(user: ReturnType<typeof renderPage>["user"], label: "Retirer" | "Annuler") {
  const dialog = await screen.findByRole("dialog", { name: "Retirer le patient ?" });
  await user.click(within(dialog).getByRole("button", { name: label }));
}

describe("the roster", () => {
  it("lists the physician's patients with their details", async () => {
    serveRoster([jeanne, marc, lise]);
    renderPage();
    const row = within(await screen.findByText("Jeanne Dupont").then((el) => el.closest("tr")!));
    expect(row.getByText("TEST11111111")).toBeInTheDocument();
    expect(row.getByText("01/05/1980")).toBeInTheDocument();
    expect(row.getByText("F")).toBeInTheDocument();
    const cells = (name: string) => within(rowOf(name)).getAllByRole("cell").map((c) => c.textContent);
    // The name with the physician's note under it, the birth date with the age beside it.
    expect(cells("Jeanne Dupont")[0]).toBe("Jeanne DupontAllergique à la pénicilline");
    expect(cells("Jeanne Dupont")[2]).toMatch(/^01\/05\/1980\d+ ans$/);
    expect(cells("Jeanne Dupont").slice(3, 6)).toEqual(["F", "Inscrit", "Oui"]);
    expect(cells("Marc Roy").slice(0, 2)).toEqual(["Marc Roy", "—"]);
    expect(cells("Marc Roy").slice(3, 6)).toEqual(["—", "Non inscrit", "Non"]);
    expect(cells("Lise Tremblay")[4]).toBe("Inconnu");
  });

  it("searches the list by name or NAM, ignoring accents", async () => {
    serveRoster([jeanne, marc]);
    const { user } = renderPage();
    await screen.findByText("Jeanne Dupont");
    await user.type(screen.getByLabelText("Rechercher un patient"), "tést1111");
    expect(screen.queryByText("Marc Roy")).not.toBeInTheDocument();
    expect(screen.getByText("Jeanne Dupont")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Rechercher un patient"));
    await user.type(screen.getByLabelText("Rechercher un patient"), "zzz");
    expect(screen.getByText("Aucun patient ne correspond à cette recherche.")).toBeInTheDocument();
  });

  it("says when the list is empty", async () => {
    serveRoster([]);
    renderPage();
    expect(await screen.findByText("Aucun patient dans votre liste.")).toBeInTheDocument();
  });

  it("shows the server's error", async () => {
    server.use(http.get("/api/patients", () => HttpResponse.json({ detail: "Erreur interne" }, { status: 500 })));
    renderPage();
    expect(await screen.findByText("Erreur interne")).toBeInTheDocument();
  });
});

describe("removing a patient from the list", () => {
  it("asks first, deletes the roster entry and re-reads the list", async () => {
    const roster = serveRoster([jeanne, marc]);
    let removed = "";
    server.use(
      http.delete("/api/patients/roster/:id", ({ params }) => {
        removed = String(params.id);
        roster.set([marc]);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderPage();
    await pickRowAction(user, "Jeanne Dupont", "Retirer");
    expect(await screen.findByText(/Retirer Jeanne Dupont de votre liste de patients \?/)).toBeInTheDocument();
    await answer(user, "Retirer");
    await waitFor(() => expect(screen.queryByText("Jeanne Dupont")).not.toBeInTheDocument());
    expect(removed).toBe("1");
    expect(screen.getByText("Marc Roy")).toBeInTheDocument();
  });

  it("does nothing when the physician declines", async () => {
    serveRoster([jeanne]);
    const onDelete = vi.fn();
    server.use(http.delete("/api/patients/roster/:id", () => (onDelete(), new HttpResponse(null, { status: 204 }))));
    const { user } = renderPage();
    await pickRowAction(user, "Jeanne Dupont", "Retirer");
    await answer(user, "Annuler");
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("shows the server's refusal", async () => {
    serveRoster([jeanne]);
    server.use(http.delete("/api/patients/roster/:id", () => HttpResponse.json({ detail: "Retrait impossible" }, { status: 409 })));
    const { user } = renderPage();
    await pickRowAction(user, "Jeanne Dupont", "Retirer");
    await answer(user, "Retirer");
    expect(await screen.findByText("Retrait impossible")).toBeInTheDocument();
  });
});

describe("personal notes", () => {
  it("opens with the current notes and saves the trimmed text", async () => {
    const roster = serveRoster([jeanne]);
    let call: { id: string; body: unknown } | undefined;
    server.use(
      http.patch("/api/patients/roster/:id", async ({ request, params }) => {
        call = { id: String(params.id), body: await request.json() };
        roster.set([{ ...jeanne, notes: "Nouvelle note" }]);
        return HttpResponse.json({ ...jeanne, notes: "Nouvelle note" });
      }),
    );
    const { user } = renderPage();
    await pickRowAction(user, "Jeanne Dupont", "Notes");
    expect(screen.getByText("Notes — Jeanne Dupont")).toBeInTheDocument();
    const notes = screen.getByRole("textbox");
    expect(notes).toHaveValue("Allergique à la pénicilline");
    await user.clear(notes);
    await user.type(notes, "  Nouvelle note  ");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(screen.queryByText("Notes — Jeanne Dupont")).not.toBeInTheDocument());
    expect(call).toEqual({ id: "1", body: { notes: "Nouvelle note" } });
  });

  it("clears the notes (null) when emptied", async () => {
    serveRoster([jeanne]);
    let body: unknown;
    server.use(
      http.patch("/api/patients/roster/:id", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(jeanne);
      }),
    );
    const { user } = renderPage();
    await pickRowAction(user, "Jeanne Dupont", "Notes");
    await user.clear(screen.getByRole("textbox"));
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(body).toEqual({ notes: null }));
  });

  it("shows an error and keeps the dialog open; cancel closes it", async () => {
    serveRoster([jeanne]);
    server.use(http.patch("/api/patients/roster/:id", () => HttpResponse.json({ detail: "Refusé" }, { status: 403 })));
    const { user } = renderPage();
    await pickRowAction(user, "Jeanne Dupont", "Notes");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(await screen.findByText("Refusé")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Annuler" }));
    expect(screen.queryByText("Notes — Jeanne Dupont")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ajouter un patient existant" })).toBeInTheDocument();
  });
});

describe("editing the shared patient record (admin only)", () => {
  it("is not offered to a physician", async () => {
    serveRoster([jeanne]);
    const { user } = renderPage("physician");
    await user.click(await screen.findByRole("button", { name: "Actions — Jeanne Dupont" }));
    expect(await screen.findByRole("menuitem", { name: "Notes" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Modifier" })).not.toBeInTheDocument();
  });

  it("is offered to an admin, prefilled, and saves trimmed values with blanks as null", async () => {
    serveRoster([jeanne]);
    let call: { id: string; body: unknown } | undefined;
    server.use(
      http.patch("/api/patients/:id", async ({ request, params }) => {
        call = { id: String(params.id), body: await request.json() };
        return HttpResponse.json(jeanne);
      }),
    );
    const { user } = renderPage("admin");
    await pickRowAction(user, "Jeanne Dupont", "Modifier");
    expect(screen.getByLabelText("Nom complet")).toHaveValue("Jeanne Dupont");
    expect(screen.getByLabelText("Numéro RAMQ (NAM)")).toHaveValue("TEST11111111");
    expect(screen.getByLabelText("Date de naissance")).toHaveValue("1980-05-01");
    expect(screen.getByLabelText("Genre")).toHaveValue("F");
    const name = screen.getByLabelText("Nom complet");
    await user.clear(name);
    await user.type(name, "  Jeanne Dupont-Roy ");
    await user.clear(screen.getByLabelText("Numéro RAMQ (NAM)"));
    await user.type(screen.getByLabelText("Médecin de famille"), "   ");
    await user.selectOptions(screen.getByLabelText("Genre"), "Autre");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(call).toBeDefined());
    expect(call).toEqual({
      id: "1",
      body: {
        full_name: "Jeanne Dupont-Roy",
        ramq_number: null,
        date_of_birth: "1980-05-01",
        gender: "Autre",
        is_vulnerable: true,
        family_doctor_name: null,
        family_doctor_practice_number: null,
      },
    });
    await waitFor(() => expect(screen.queryByText(/Modifier le patient/)).not.toBeInTheDocument());
  });

  it("requires a name and a date of birth, without calling the server", async () => {
    serveRoster([jeanne]);
    const onPatch = vi.fn();
    server.use(http.patch("/api/patients/:id", () => (onPatch(), HttpResponse.json(jeanne))));
    const { user } = renderPage("admin");
    await pickRowAction(user, "Jeanne Dupont", "Modifier");
    await user.clear(screen.getByLabelText("Nom complet"));
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(screen.getByText("Le nom et la date de naissance sont obligatoires.")).toBeInTheDocument();
    expect(onPatch).not.toHaveBeenCalled();
  });

  it("shows the server's error", async () => {
    serveRoster([jeanne]);
    server.use(http.patch("/api/patients/:id", () => HttpResponse.json({ detail: "NAM déjà utilisé" }, { status: 409 })));
    const { user } = renderPage("admin");
    await pickRowAction(user, "Jeanne Dupont", "Modifier");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(await screen.findByText("NAM déjà utilisé")).toBeInTheDocument();
  });
});

describe("adding an existing patient", () => {
  function serveSearchFor(found: RosterEntry[]) {
    server.use(http.get("/api/patients/search", () => HttpResponse.json(found)));
  }

  it("requires picking a patient first", async () => {
    serveRoster([]);
    const { user } = renderPage();
    await user.click(await screen.findByRole("button", { name: "Ajouter un patient existant" }));
    await user.click(screen.getByRole("button", { name: "Ajouter" }));
    expect(screen.getByText("Sélectionnez un patient.")).toBeInTheDocument();
  });

  it("searches, picks, adds with the notes and re-reads the list", async () => {
    const roster = serveRoster([]);
    serveSearchFor([jeanne]);
    let body: unknown;
    server.use(
      http.post("/api/patients/roster", async ({ request }) => {
        body = await request.json();
        roster.set([jeanne]);
        return HttpResponse.json(jeanne);
      }),
    );
    const { user } = renderPage();
    await user.click(await screen.findByRole("button", { name: "Ajouter un patient existant" }));
    await user.type(screen.getByLabelText("Patient"), "Dupont");
    await user.click(await screen.findByRole("option", { name: /Jeanne Dupont/ }));
    await user.type(screen.getByLabelText("Notes personnelles"), "  suivi annuel ");
    await user.click(screen.getByRole("button", { name: "Ajouter" }));
    expect(await screen.findByText("TEST11111111")).toBeInTheDocument();
    expect(body).toEqual({ patient_id: 1, notes: "suivi annuel" });
    expect(screen.queryByLabelText("Notes personnelles")).not.toBeInTheDocument();
  });

  it("shows the server's error and can be cancelled", async () => {
    serveRoster([]);
    serveSearchFor([jeanne]);
    server.use(http.post("/api/patients/roster", () => HttpResponse.json({ detail: "Déjà dans votre liste" }, { status: 409 })));
    const { user } = renderPage();
    await user.click(await screen.findByRole("button", { name: "Ajouter un patient existant" }));
    await user.type(screen.getByLabelText("Patient"), "Dupont");
    await user.click(await screen.findByRole("option", { name: /Jeanne Dupont/ }));
    await user.click(screen.getByRole("button", { name: "Ajouter" }));
    expect(await screen.findByText("Déjà dans votre liste")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Annuler" }));
    expect(screen.queryByLabelText("Notes personnelles")).not.toBeInTheDocument();
  });
});

describe("creating a new patient", () => {
  async function fill(user: ReturnType<typeof renderPage>["user"]) {
    await user.click(await screen.findByRole("button", { name: "Créer un nouveau patient" }));
    await user.type(screen.getByLabelText("Nom complet"), "Nouveau Patient");
    await user.type(screen.getByLabelText("Date de naissance"), "1990-02-03");
  }

  it("opens in a dialog over the page, and cancel closes it", async () => {
    serveRoster([]);
    const { user } = renderPage();
    await user.click(await screen.findByRole("button", { name: "Créer un nouveau patient" }));
    expect(screen.getByText("Nouveau patient")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ajouter un patient existant" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Annuler" }));
    expect(screen.getByRole("button", { name: "Créer un nouveau patient" })).toBeInTheDocument();
  });

  it("creates the patient, adds it to the list, and re-reads the roster", async () => {
    const roster = serveRoster([]);
    const created = entry({ id: 9, full_name: "Nouveau Patient" });
    let posted: unknown;
    let rostered: unknown;
    server.use(
      http.post("/api/patients", async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(created);
      }),
      http.post("/api/patients/roster", async ({ request }) => {
        rostered = await request.json();
        roster.set([created]);
        return HttpResponse.json(created);
      }),
    );
    const { user } = renderPage();
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Créer le patient" }));
    expect(await screen.findByText("Nouveau Patient", { selector: "td span" })).toBeInTheDocument();
    expect(posted).toMatchObject({ full_name: "Nouveau Patient", date_of_birth: "1990-02-03", ramq_number: null });
    expect(rostered).toEqual({ patient_id: 9 });
    expect(screen.queryByText("Nouveau patient")).not.toBeInTheDocument();
  });

  it("shows the creation error and keeps the form", async () => {
    serveRoster([]);
    server.use(http.post("/api/patients", () => HttpResponse.json({ detail: "NAM déjà utilisé" }, { status: 409 })));
    const { user } = renderPage();
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Créer le patient" }));
    expect(await screen.findByText("NAM déjà utilisé")).toBeInTheDocument();
    expect(screen.getByLabelText("Nom complet")).toHaveValue("Nouveau Patient");
  });

  it("reports a failure to add the new patient to the list", async () => {
    serveRoster([]);
    server.use(
      http.post("/api/patients", () => HttpResponse.json(entry({ id: 9, full_name: "Nouveau Patient" }))),
      http.post("/api/patients/roster", () => HttpResponse.json({ detail: "Liste indisponible" }, { status: 500 })),
    );
    const { user } = renderPage();
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Créer le patient" }));
    expect(await screen.findByText("Liste indisponible")).toBeInTheDocument();
  });
});
