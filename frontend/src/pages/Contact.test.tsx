import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderWithProviders, serveSession } from "../test/render";
import { server } from "../test/server";
import Contact from "./Contact";

beforeEach(() => serveSession(null));

function serveContact(status = 204) {
  const bodies: Record<string, unknown>[] = [];
  server.use(
    http.post("/api/contact", async ({ request }) => {
      bodies.push((await request.json()) as Record<string, unknown>);
      return status === 204 ? new HttpResponse(null, { status }) : HttpResponse.json({ detail: "Erreur interne" }, { status });
    }),
  );
  return bodies;
}

const renderForm = (route = "/contact") => renderWithProviders(<Contact />, { route });
const submit = () => screen.getByRole("button", { name: "Envoyer la demande" });

async function fillRequired(user: ReturnType<typeof renderForm>["user"]) {
  await user.type(screen.getByLabelText(/^Nom( \*)?$/), "Dr Test");
  await user.type(screen.getByLabelText(/^Courriel/), "dr@clinique.test");
  await user.selectOptions(screen.getByLabelText(/Vous êtes/), "medecin");
  await user.click(screen.getByLabelText(/J.accepte que/));
}

describe("the contact form", () => {
  it("cannot be sent before the Law 25 consent is given", async () => {
    const { user } = renderForm();
    expect(submit()).toBeDisabled();
    await user.click(screen.getByLabelText(/J.accepte que/));
    expect(submit()).toBeEnabled();
    await user.click(screen.getByLabelText(/J.accepte que/));
    expect(submit()).toBeDisabled();
  });

  it("does not send without the required fields (native validation)", async () => {
    const bodies = serveContact();
    const { user } = renderForm();
    await user.click(screen.getByLabelText(/J.accepte que/));
    await user.click(submit());
    expect(bodies).toEqual([]);
  });

  it("sends the request, with empty optional fields as null, and thanks the sender", async () => {
    const bodies = serveContact();
    const { user } = renderForm();
    await fillRequired(user);
    await user.click(submit());
    expect(await screen.findByText("Merci, votre demande est envoyée")).toBeInTheDocument();
    expect(screen.getByText("dr@clinique.test")).toBeInTheDocument();
    expect(bodies).toEqual([
      {
        name: "Dr Test",
        email: "dr@clinique.test",
        phone: null,
        organization: null,
        role: "medecin",
        physician_count: null,
        topic: "demo",
        plan: null,
        message: null,
        consent: true,
        website: "",
      },
    ]);
    expect(screen.getByRole("link", { name: /Retour à l.accueil/ })).toHaveAttribute("href", "/");
  });

  it("sends the optional fields when filled, the doctor count as a number", async () => {
    const bodies = serveContact();
    const { user } = renderForm();
    await fillRequired(user);
    await user.type(screen.getByLabelText("Téléphone"), "514-555-0100");
    await user.type(screen.getByLabelText("Clinique ou organisation"), "GMF Test");
    await user.type(screen.getByLabelText("Nombre de médecins"), "12");
    await user.selectOptions(screen.getByLabelText("Sujet"), "tarifs");
    await user.type(screen.getByLabelText("Message"), "Bonjour");
    await user.click(submit());
    await screen.findByText("Merci, votre demande est envoyée");
    expect(bodies[0]).toMatchObject({
      phone: "514-555-0100",
      organization: "GMF Test",
      physician_count: 12,
      topic: "tarifs",
      message: "Bonjour",
    });
  });

  describe("pre-filled from the link", () => {
    it("takes the subject and plan from the query string", async () => {
      const bodies = serveContact();
      const { user } = renderForm("/contact?sujet=essai&forfait=gratuit");
      expect(screen.getByLabelText("Sujet")).toHaveValue("essai");
      await fillRequired(user);
      await user.click(submit());
      await screen.findByText("Merci, votre demande est envoyée");
      expect(bodies[0]).toMatchObject({ topic: "essai", plan: "gratuit" });
    });

    it("falls back to 'démo' for an unknown subject and drops a malformed plan", async () => {
      const bodies = serveContact();
      const { user } = renderForm("/contact?sujet=nimportequoi&forfait=SOLO%3Cscript%3E");
      expect(screen.getByLabelText("Sujet")).toHaveValue("demo");
      await fillRequired(user);
      await user.click(submit());
      await screen.findByText("Merci, votre demande est envoyée");
      expect(bodies[0]).toMatchObject({ topic: "demo", plan: null });
    });
  });

  describe("honeypot", () => {
    it("is hidden from people and assistive technology, and empty by default", async () => {
      const bodies = serveContact();
      const { user } = renderForm();
      const trap = document.getElementById("contact-website")!;
      expect(trap.closest("[aria-hidden=true]")).not.toBeNull();
      expect(trap).toHaveAttribute("tabindex", "-1");
      await fillRequired(user);
      await user.click(submit());
      await screen.findByText("Merci, votre demande est envoyée");
      expect(bodies[0].website).toBe("");
    });

    it("is passed on as filled, so the server can drop the request", async () => {
      const bodies = serveContact();
      const { user } = renderForm();
      await user.type(document.getElementById("contact-website")!, "http://spam.test");
      await fillRequired(user);
      await user.click(submit());
      await screen.findByText("Merci, votre demande est envoyée");
      expect(bodies[0].website).toBe("http://spam.test");
    });
  });

  describe("errors", () => {
    it("explains the rate limit (429) and keeps the form for another try", async () => {
      server.use(http.post("/api/contact", () => new HttpResponse(null, { status: 429 })));
      const { user } = renderForm();
      await fillRequired(user);
      await user.click(submit());
      expect(await screen.findByText(/Trop de demandes envoyées/)).toBeInTheDocument();
      expect(screen.getByLabelText(/^Nom( \*)?$/)).toHaveValue("Dr Test");
      expect(submit()).toBeEnabled();
    });

    it("shows any other server error", async () => {
      serveContact(500);
      const { user } = renderForm();
      await fillRequired(user);
      await user.click(submit());
      expect(await screen.findByText("Erreur interne")).toBeInTheDocument();
      expect(screen.queryByText("Merci, votre demande est envoyée")).not.toBeInTheDocument();
    });

    it("clears the error on the next attempt", async () => {
      let attempts = 0;
      server.use(
        http.post("/api/contact", () =>
          ++attempts === 1 ? HttpResponse.json({ detail: "Erreur interne" }, { status: 500 }) : new HttpResponse(null, { status: 204 }),
        ),
      );
      const { user } = renderForm();
      await fillRequired(user);
      await user.click(submit());
      await screen.findByText("Erreur interne");
      await user.click(submit());
      expect(await screen.findByText("Merci, votre demande est envoyée")).toBeInTheDocument();
    });
  });

  it("shows the contact email as a mailto link", () => {
    renderForm();
    expect(screen.getByRole("link", { name: /@nomiamd\.com/ })).toHaveAttribute("href", expect.stringMatching(/^mailto:.+@nomiamd\.com$/));
  });
});
