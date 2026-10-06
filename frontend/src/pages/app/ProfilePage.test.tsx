import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { makeUser, renderWithProviders, serveSession } from "../../test/render";
import { server } from "../../test/server";
import type { UserOut } from "../../api";
import ProfilePage from "./ProfilePage";

const doctor = makeUser({
  full_name: "Dr Test",
  email: "doc@example.test",
  physician_type: "med_fam",
  panel_size: 900,
  remuneration_type: "mixte",
  practice_number: "12345",
});

async function renderProfile(user: UserOut = doctor) {
  serveSession(user);
  const view = renderWithProviders(<ProfilePage />);
  await screen.findByRole("heading", { name: "Profil" });
  // The form is filled from the loaded user by an effect, after the first render.
  await waitFor(() => expect(screen.getByLabelText("Nom complet")).toHaveValue(user.full_name));
  return view;
}

function serveProfileUpdate() {
  const bodies: unknown[] = [];
  server.use(
    http.patch("/api/auth/me", async ({ request }) => {
      const body = (await request.json()) as Partial<UserOut>;
      bodies.push(body);
      return HttpResponse.json({ ...doctor, ...body });
    }),
  );
  return bodies;
}

const saveProfile = () => screen.getAllByRole("button", { name: "Enregistrer" })[0];

describe("profile details", () => {
  it("shows the physician's current details, with the email read-only", async () => {
    await renderProfile();
    expect(screen.getByLabelText("Courriel")).toBeDisabled();
    expect(screen.getByLabelText("Courriel")).toHaveValue("doc@example.test");
    expect(screen.getByLabelText("Nom complet")).toHaveValue("Dr Test");
    expect(screen.getByLabelText("Type de pratique")).toHaveValue("med_fam");
    expect(screen.getByLabelText("Nombre de patients")).toHaveValue(900);
    expect(screen.getByLabelText("Mode de rémunération")).toHaveValue("mixte");
    expect(screen.getByLabelText("Numéro de pratique")).toHaveValue("12345");
  });

  it("shows empty fields for details not entered yet", async () => {
    await renderProfile(makeUser({ physician_type: null, panel_size: null, remuneration_type: null, practice_number: null }));
    expect(screen.getByLabelText("Type de pratique")).toHaveValue("");
    expect(screen.getByLabelText("Nombre de patients")).toHaveValue(null);
    expect(screen.getByLabelText("Numéro de pratique")).toHaveValue("");
  });

  it("saves the changes and confirms", async () => {
    const bodies = serveProfileUpdate();
    const user = (await renderProfile()).user;
    const name = screen.getByLabelText("Nom complet");
    await user.clear(name);
    await user.type(name, "Dre Nouvelle");
    await user.selectOptions(screen.getByLabelText("Mode de rémunération"), "a_l_acte");
    const count = screen.getByLabelText("Nombre de patients");
    await user.clear(count);
    await user.type(count, "1200");
    await user.click(saveProfile());
    expect(await screen.findByText("Profil mis à jour.")).toBeInTheDocument();
    expect(bodies).toEqual([
      { full_name: "Dre Nouvelle", physician_type: "med_fam", panel_size: 1200, remuneration_type: "a_l_acte", practice_number: "12345" },
    ]);
    expect(screen.getByLabelText("Nom complet")).toHaveValue("Dre Nouvelle");
  });

  it("sends blanks as null", async () => {
    const bodies = serveProfileUpdate();
    const user = (await renderProfile()).user;
    await user.selectOptions(screen.getByLabelText("Type de pratique"), "");
    await user.clear(screen.getByLabelText("Nombre de patients"));
    await user.selectOptions(screen.getByLabelText("Mode de rémunération"), "");
    await user.clear(screen.getByLabelText("Numéro de pratique"));
    await user.click(saveProfile());
    await screen.findByText("Profil mis à jour.");
    expect(bodies[0]).toEqual({ full_name: "Dr Test", physician_type: null, panel_size: null, remuneration_type: null, practice_number: null });
  });

  it("accepts a 6-digit practice number, trimmed", async () => {
    const bodies = serveProfileUpdate();
    const user = (await renderProfile()).user;
    const field = screen.getByLabelText("Numéro de pratique");
    await user.clear(field);
    await user.type(field, " 123456 ");
    await user.click(saveProfile());
    await screen.findByText("Profil mis à jour.");
    expect(bodies[0]).toMatchObject({ practice_number: "123456" });
  });

  it.each(["1234", "1234567", "12a45", "12 345"])("refuses the practice number '%s' without calling the server", async (value) => {
    const bodies = serveProfileUpdate();
    const user = (await renderProfile()).user;
    const field = screen.getByLabelText("Numéro de pratique");
    await user.clear(field);
    await user.type(field, value);
    await user.click(saveProfile());
    expect(screen.getByText("Le numéro de pratique doit contenir 5 ou 6 chiffres.")).toBeInTheDocument();
    expect(bodies).toEqual([]);
  });

  // The field's own min={0} stops a negative count in the browser before the app's check
  // (and its message) is reached, so the visible outcome is that nothing is sent.
  it("does not send a negative patient count", async () => {
    const bodies = serveProfileUpdate();
    const user = (await renderProfile()).user;
    const count = screen.getByLabelText("Nombre de patients");
    await user.clear(count);
    await user.type(count, "-5");
    await user.click(saveProfile());
    expect(bodies).toEqual([]);
    expect(screen.queryByText("Profil mis à jour.")).not.toBeInTheDocument();
  });

  it("shows the server's error and no confirmation", async () => {
    server.use(http.patch("/api/auth/me", () => HttpResponse.json({ detail: "Profil invalide" }, { status: 422 })));
    const user = (await renderProfile()).user;
    await user.click(saveProfile());
    expect(await screen.findByText("Profil invalide")).toBeInTheDocument();
    expect(screen.queryByText("Profil mis à jour.")).not.toBeInTheDocument();
  });

  it("clears the previous confirmation on the next attempt", async () => {
    serveProfileUpdate();
    const user = (await renderProfile()).user;
    await user.click(saveProfile());
    await screen.findByText("Profil mis à jour.");
    const field = screen.getByLabelText("Numéro de pratique");
    await user.clear(field);
    await user.type(field, "1");
    await user.click(saveProfile());
    // The toast is dismissed, and slides out.
    await waitFor(() => expect(screen.queryByText("Profil mis à jour.")).not.toBeInTheDocument());
  });
});

describe("password change", () => {
  const fill = async (user: Awaited<ReturnType<typeof renderProfile>>["user"], current: string, next: string, confirm: string) => {
    await user.type(screen.getByLabelText("Mot de passe actuel"), current);
    await user.type(screen.getByLabelText("Nouveau mot de passe"), next);
    await user.type(screen.getByLabelText("Confirmer le nouveau mot de passe"), confirm);
    await user.click(screen.getByRole("button", { name: "Changer le mot de passe" }));
  };

  function servePassword() {
    const bodies: unknown[] = [];
    server.use(
      http.post("/api/auth/me/password", async ({ request }) => {
        bodies.push(await request.json());
        return new HttpResponse(null, { status: 204 });
      }),
    );
    return bodies;
  }

  it("changes the password, confirms and empties the fields", async () => {
    const bodies = servePassword();
    const user = (await renderProfile()).user;
    await fill(user, "ancien-mdp", "nouveau-mdp-1", "nouveau-mdp-1");
    expect(await screen.findByText("Mot de passe modifié.")).toBeInTheDocument();
    expect(bodies).toEqual([{ current_password: "ancien-mdp", new_password: "nouveau-mdp-1" }]);
    for (const label of ["Mot de passe actuel", "Nouveau mot de passe", "Confirmer le nouveau mot de passe"]) {
      expect(screen.getByLabelText(label)).toHaveValue("");
    }
  });

  it("refuses a password under 8 characters", async () => {
    const bodies = servePassword();
    const user = (await renderProfile()).user;
    await fill(user, "ancien-mdp", "court", "court");
    expect(screen.getByText("Le nouveau mot de passe doit contenir au moins 8 caractères.")).toBeInTheDocument();
    expect(bodies).toEqual([]);
  });

  it("refuses when the confirmation differs", async () => {
    const bodies = servePassword();
    const user = (await renderProfile()).user;
    await fill(user, "ancien-mdp", "nouveau-mdp-1", "nouveau-mdp-2");
    expect(screen.getByText("Les nouveaux mots de passe ne correspondent pas.")).toBeInTheDocument();
    expect(bodies).toEqual([]);
  });

  it("shows the server's error (wrong current password) and keeps what was typed", async () => {
    server.use(http.post("/api/auth/me/password", () => HttpResponse.json({ detail: "Mot de passe actuel incorrect" }, { status: 400 })));
    const user = (await renderProfile()).user;
    await fill(user, "mauvais", "nouveau-mdp-1", "nouveau-mdp-1");
    expect(await screen.findByText("Mot de passe actuel incorrect")).toBeInTheDocument();
    expect(screen.queryByText("Mot de passe modifié.")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Mot de passe actuel")).toHaveValue("mauvais"));
  });
});
