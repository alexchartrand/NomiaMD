import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import type { AdminUser, AuditEvent, SystemReport, UsageBucket, UsageReport } from "../../../api";
import { makeUser, renderWithProviders, serveSession } from "../../../test/render";
import { server } from "../../../test/server";
import AdminPage from ".";

const me = makeUser({ id: 1, role: "admin", full_name: "Admin Test" });

function makeAdminUser(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: 2,
    email: "doc@example.test",
    full_name: "Dr Roy",
    role: "physician",
    is_active: true,
    must_change_password: false,
    practice_number: "12345",
    physician_type: "med_fam",
    panel_size: 900,
    remuneration_type: "mixte",
    created_at: "2026-10-01T12:00:00Z",
    last_login_at: "2026-10-18T13:30:00Z",
    deactivated_at: null,
    encounter_count: 12,
    claim_count: 8,
    ...overrides,
  };
}

function bucket(overrides: Partial<UsageBucket> = {}): UsageBucket {
  return {
    key: "mistral-medium-latest",
    label: "mistral-medium-latest",
    calls: 4,
    input_tokens: 8000,
    output_tokens: 1200,
    cost_usd: "0.0056",
    unpriced_calls: 0,
    errors: 0,
    median_latency_ms: 2100,
    p95_latency_ms: 4800,
    ...overrides,
  };
}

beforeEach(() => serveSession(me));

function renderAdmin(route = "/app/admin") {
  return renderWithProviders(
    <Routes>
      <Route path="/app/admin" element={<AdminPage />} />
    </Routes>,
    { route },
  );
}

function serveUsers(users: AdminUser[]) {
  server.use(http.get("/api/admin/users", () => HttpResponse.json(users)));
}

describe("users tab", () => {
  it("lists the accounts with their state and activity", async () => {
    serveUsers([
      makeAdminUser(),
      makeAdminUser({ id: 3, full_name: "Dr Tremblay", email: "t@example.test", is_active: false }),
      makeAdminUser({ id: 4, full_name: "Dr Nouveau", email: "n@example.test", must_change_password: true }),
    ]);
    renderAdmin();

    const row = (await screen.findByText("Dr Roy")).closest("tr")!;
    expect(within(row).getByText("Actif")).toBeInTheDocument();
    expect(within(row).getByText("12")).toBeInTheDocument();
    expect(within(screen.getByText("Dr Tremblay").closest("tr")!).getByText("Désactivé")).toBeInTheDocument();
    expect(within(screen.getByText("Dr Nouveau").closest("tr")!).getByText("Mot de passe temporaire")).toBeInTheDocument();
  });

  it("filters by name, email or practice number", async () => {
    serveUsers([makeAdminUser(), makeAdminUser({ id: 3, full_name: "Dr Tremblay", email: "t@example.test", practice_number: "99999" })]);
    const { user } = renderAdmin();
    await screen.findByText("Dr Roy");

    await user.type(screen.getByLabelText("Rechercher"), "9999");

    expect(screen.queryByText("Dr Roy")).not.toBeInTheDocument();
    expect(screen.getByText("Dr Tremblay")).toBeInTheDocument();
  });

  it("creates an account and shows its temporary password once", async () => {
    serveUsers([]);
    const bodies: unknown[] = [];
    server.use(
      http.post("/api/admin/users", async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          { user: makeAdminUser({ id: 9, full_name: "Dr Neuf", email: "neuf@example.test", must_change_password: true }), temporary_password: "Tmp-Secret-123456" },
          { status: 201 },
        );
      }),
    );
    const { user } = renderAdmin();
    await screen.findByText("Aucun utilisateur.");

    await user.click(screen.getByRole("button", { name: "Nouvel utilisateur" }));
    await user.type(screen.getByLabelText("Courriel"), "neuf@example.test");
    await user.type(screen.getByLabelText("Nom complet"), "Dr Neuf");
    await user.type(screen.getByLabelText("Nombre de patients"), "500");
    await user.click(screen.getByRole("button", { name: "Créer le compte" }));

    const shown = within(await screen.findByRole("dialog", { name: "Mot de passe temporaire" }));
    expect(shown.getByText("Tmp-Secret-123456")).toBeInTheDocument();
    expect(shown.getByText(/affiché une seule fois/)).toBeInTheDocument();
    expect(bodies).toEqual([
      {
        email: "neuf@example.test",
        full_name: "Dr Neuf",
        role: "physician",
        practice_number: null,
        physician_type: null,
        panel_size: 500,
        remuneration_type: null,
      },
    ]);

    await user.click(screen.getByRole("button", { name: "Terminé" }));
    expect(screen.queryByText("Tmp-Secret-123456")).not.toBeInTheDocument();
    expect(screen.getByText("Dr Neuf")).toBeInTheDocument();
  });

  it("shows the server's refusal in the form", async () => {
    serveUsers([]);
    server.use(
      http.post("/api/admin/users", () =>
        HttpResponse.json({ detail: "Un compte existe déjà avec ce courriel." }, { status: 409 }),
      ),
    );
    const { user } = renderAdmin();
    await screen.findByText("Aucun utilisateur.");

    await user.click(screen.getByRole("button", { name: "Nouvel utilisateur" }));
    await user.type(screen.getByLabelText("Courriel"), "doc@example.test");
    await user.type(screen.getByLabelText("Nom complet"), "Dr Doublon");
    await user.click(screen.getByRole("button", { name: "Créer le compte" }));

    expect(await screen.findByText("Un compte existe déjà avec ce courriel.")).toBeInTheDocument();
  });

  it("deactivates an account after confirming", async () => {
    serveUsers([makeAdminUser()]);
    let deactivated = false;
    server.use(
      http.post("/api/admin/users/2/deactivate", () => {
        deactivated = true;
        return HttpResponse.json(makeAdminUser({ is_active: false, deactivated_at: "2026-10-19T12:00:00Z" }));
      }),
    );
    const { user } = renderAdmin();
    await screen.findByText("Dr Roy");

    await user.click(screen.getByRole("button", { name: "Actions — Dr Roy" }));
    await user.click(await screen.findByRole("menuitem", { name: "Désactiver" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Désactiver" }));

    await waitFor(() => expect(deactivated).toBe(true));
    expect(await screen.findByText("Désactivé")).toBeInTheDocument();
  });

  it("resets a password and shows the new temporary one", async () => {
    serveUsers([makeAdminUser()]);
    server.use(
      http.post("/api/admin/users/2/reset-password", () =>
        HttpResponse.json({ user: makeAdminUser({ must_change_password: true }), temporary_password: "Reset-Pass-987654" }),
      ),
    );
    const { user } = renderAdmin();
    await screen.findByText("Dr Roy");

    await user.click(screen.getByRole("button", { name: "Actions — Dr Roy" }));
    await user.click(await screen.findByRole("menuitem", { name: "Réinitialiser le mot de passe" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Réinitialiser" }));

    const shown = within(await screen.findByRole("dialog", { name: "Mot de passe temporaire" }));
    expect(shown.getByText("Reset-Pass-987654")).toBeInTheDocument();
  });

  it("offers no reset, logout or deactivation on the admin's own account", async () => {
    serveUsers([makeAdminUser({ id: 1, full_name: "Admin Test", role: "admin" })]);
    const { user } = renderAdmin();
    await screen.findByText("(vous)");

    await user.click(screen.getByRole("button", { name: "Actions — Admin Test" }));

    expect(await screen.findByRole("menuitem", { name: "Modifier" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Désactiver" })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Réinitialiser le mot de passe" })).not.toBeInTheDocument();
  });
});

describe("usage tab", () => {
  function report(overrides: Partial<UsageReport> = {}): UsageReport {
    return {
      start: "2026-09-20",
      end: "2026-10-19",
      totals: bucket({ key: "total", label: "Total", calls: 6, cost_usd: "0.0081", unpriced_calls: 1 }),
      extractions: 3,
      cost_per_extraction_usd: "0.0027",
      by_day: [bucket({ key: "2026-10-18", label: "2026-10-18" }), bucket({ key: "2026-10-19", label: "2026-10-19", calls: 2 })],
      group_by: "model",
      breakdown: [bucket(), bucket({ key: "local-model", label: "local-model", calls: 2, unpriced_calls: 2, cost_usd: "0" })],
      ...overrides,
    };
  }

  it("shows the totals and the breakdown, and regroups on request", async () => {
    const groupings: string[] = [];
    server.use(
      http.get("/api/admin/usage", ({ request }) => {
        const groupBy = new URL(request.url).searchParams.get("group_by")!;
        groupings.push(groupBy);
        return HttpResponse.json(
          groupBy === "purpose"
            ? report({ group_by: "purpose", breakdown: [bucket({ key: "billing_codes", label: "billing_codes" })] })
            : report(),
        );
      }),
    );
    const { user } = renderAdmin("/app/admin?tab=utilisation");

    expect(await screen.findByText("1 appel(s) sans prix connu")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    const unpriced = screen.getByText("local-model").closest("tr")!;
    expect(within(unpriced).getByText("—")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Par étape" }));

    expect(await screen.findByText("Choix des codes")).toBeInTheDocument();
    expect(groupings).toEqual(["model", "purpose"]);
  });
});

describe("audit tab", () => {
  it("lists events in words", async () => {
    serveUsers([makeAdminUser()]);
    const events: AuditEvent[] = [
      {
        id: 1,
        created_at: "2026-10-19T13:00:00Z",
        action: "user.updated",
        actor_id: 1,
        actor_name: "Admin Test",
        target_user_id: 2,
        target_name: "Dr Roy",
        details: { fields: ["full_name", "panel_size"] },
        ip: null,
      },
      {
        id: 2,
        created_at: "2026-10-19T12:00:00Z",
        action: "login.failed",
        actor_id: null,
        actor_name: null,
        target_user_id: 2,
        target_name: "Dr Roy",
        details: { reason: "bad_password" },
        ip: "10.0.0.7",
      },
    ];
    server.use(http.get("/api/admin/audit", () => HttpResponse.json(events)));
    renderAdmin("/app/admin?tab=journal");

    const table = within(await screen.findByRole("table"));
    expect(table.getByText("Compte modifié")).toBeInTheDocument();
    expect(table.getByText("Champs : full_name, panel_size")).toBeInTheDocument();
    expect(table.getByText("Connexion refusée")).toBeInTheDocument();
    expect(table.getByText("Mot de passe invalide")).toBeInTheDocument();
    expect(table.getByText("10.0.0.7")).toBeInTheDocument();
  });
});

describe("system tab", () => {
  const system: SystemReport = {
    checked_at: "2026-10-19T14:00:00Z",
    app_env: "development",
    app_version: null,
    database: { ok: true, detail: "sqlite" },
    codes_table: { ok: false, detail: "non initialisée" },
    models: {
      chat_provider: "mistral",
      embedding_provider: "mistral",
      embedding_model: "mistral-embed",
      step_models: { billing_codes: "mistral-medium-latest" },
    },
    row_counts: { users: 3, encounters: 40 },
    failed_extractions: 1,
    encounters_past_purge: 0,
  };

  it("shows the checks, retries a failed extraction and unlocks a login", async () => {
    let retried = 0;
    let unlocked = "";
    server.use(
      http.get("/api/admin/system", () => HttpResponse.json(system)),
      http.get("/api/admin/extraction-failures", () =>
        HttpResponse.json(
          retried
            ? []
            : [
                {
                  encounter_id: 42,
                  user_id: 2,
                  physician_name: "Dr Roy",
                  source_system: "manual",
                  service_date: "2026-10-17",
                  received_at: "2026-10-18T15:00:00Z",
                  error: "RuntimeError: model down",
                },
              ],
        ),
      ),
      http.post("/api/admin/encounters/42/retry", () => {
        retried += 1;
        return new HttpResponse(null, { status: 202 });
      }),
      http.get("/api/admin/lockouts", () =>
        HttpResponse.json([
          {
            email: "doc@example.test",
            failed_attempts: 6,
            last_attempt_at: "2026-10-19T13:55:00Z",
            locked_until: "2026-10-19T14:10:00Z",
            is_locked: true,
            known_account: true,
          },
        ]),
      ),
      http.delete("/api/admin/lockouts/:email", ({ params }) => {
        unlocked = String(params.email);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderAdmin("/app/admin?tab=systeme");

    expect(await screen.findByText("non initialisée")).toBeInTheDocument();
    expect(screen.getByText("Choix des codes")).toBeInTheDocument();
    expect(screen.getByText("RuntimeError: model down")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Relancer" }));
    await waitFor(() => expect(screen.getByText("Aucune extraction en échec.")).toBeInTheDocument());
    expect(retried).toBe(1);

    await user.click(screen.getByRole("button", { name: "Déverrouiller" }));
    await waitFor(() => expect(unlocked).toBe("doc@example.test"));
    expect(screen.getByText("Aucune tentative échouée récente.")).toBeInTheDocument();
  });
});

describe("contact requests tab", () => {
  it("lists the requests", async () => {
    server.use(
      http.get("/api/admin/contact-requests", () =>
        HttpResponse.json([
          {
            id: 1,
            created_at: "2026-10-19T10:00:00Z",
            name: "Clinique du Parc",
            email: "info@parc.test",
            phone: null,
            organization: "GMF du Parc",
            role: "gestionnaire",
            physician_count: 8,
            topic: "demo",
            plan: null,
            message: "Nous aimerions une démo.",
          },
        ]),
      ),
    );
    renderAdmin("/app/admin?tab=contacts");

    expect(await screen.findByText("Clinique du Parc")).toBeInTheDocument();
    expect(screen.getByText("Démo")).toBeInTheDocument();
    expect(screen.getByText("Nous aimerions une démo.")).toBeInTheDocument();
  });
});
