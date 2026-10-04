import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { createClaim, DuplicateClaimError, replaceClaim } from "./claims";
import { makeClaim } from "../test/factories";

const payload = { extraction_run_id: 7, service_date: "2026-10-01", selected_codes: [{ code: "00103", fee_index: null }] };

describe("createClaim", () => {
  it("posts the payload with confirm_duplicate=false by default", async () => {
    let seen: { url: string; body: unknown } | undefined;
    server.use(
      http.post("/api/claims", async ({ request }) => {
        seen = { url: request.url, body: await request.json() };
        return HttpResponse.json(makeClaim({ id: 5 }));
      }),
    );
    const claim = await createClaim(payload);
    expect(claim.id).toBe(5);
    expect(new URL(seen!.url).searchParams.get("confirm_duplicate")).toBe("false");
    expect(seen!.body).toEqual(payload);
  });

  it("passes confirm_duplicate=true when confirmed", async () => {
    let flag: string | null = null;
    server.use(
      http.post("/api/claims", ({ request }) => {
        flag = new URL(request.url).searchParams.get("confirm_duplicate");
        return HttpResponse.json(makeClaim());
      }),
    );
    await createClaim(payload, true);
    expect(flag).toBe("true");
  });

  it("throws DuplicateClaimError on a duplicate_claim 409, with the server message", async () => {
    server.use(
      http.post("/api/claims", () =>
        HttpResponse.json({ detail: { code: "duplicate_claim", message: "Déjà facturé." } }, { status: 409 }),
      ),
    );
    const error = await createClaim(payload).catch((e) => e);
    expect(error).toBeInstanceOf(DuplicateClaimError);
    expect(error.message).toBe("Déjà facturé.");
  });

  it("uses a default message when the duplicate 409 carries none", async () => {
    server.use(http.post("/api/claims", () => HttpResponse.json({ detail: { code: "duplicate_claim" } }, { status: 409 })));
    const error = await createClaim(payload).catch((e) => e);
    expect(error).toBeInstanceOf(DuplicateClaimError);
    expect(error.message).toMatch(/existe déjà/);
  });

  it("throws a plain Error on any other 409", async () => {
    server.use(http.post("/api/claims", () => HttpResponse.json({ detail: "Déjà sur une facture." }, { status: 409 })));
    const error = await createClaim(payload).catch((e) => e);
    expect(error).not.toBeInstanceOf(DuplicateClaimError);
    expect(error.message).toBe("Déjà sur une facture.");
  });

  it("falls back to a default message on a 409 without a usable body", async () => {
    server.use(http.post("/api/claims", () => new HttpResponse("nope", { status: 409 })));
    const error = await createClaim(payload).catch((e) => e);
    expect(error.message).toBe("La facturation a été refusée.");
  });

  it("surfaces other errors through unwrap", async () => {
    server.use(http.post("/api/claims", () => HttpResponse.json({ detail: "Interdit" }, { status: 403 })));
    await expect(createClaim(payload)).rejects.toThrow("Interdit");
  });
});

describe("replaceClaim", () => {
  it("PUTs to the claim with confirm_duplicate", async () => {
    let seen: { method: string; url: string } | undefined;
    server.use(
      http.put("/api/claims/:id", ({ request, params }) => {
        seen = { method: request.method, url: request.url };
        return HttpResponse.json(makeClaim({ id: Number(params.id) + 1 }));
      }),
    );
    const claim = await replaceClaim(3, payload, true);
    expect(claim.id).toBe(4);
    expect(new URL(seen!.url).searchParams.get("confirm_duplicate")).toBe("true");
  });

  it("throws DuplicateClaimError on a duplicate_claim 409", async () => {
    server.use(
      http.put("/api/claims/:id", () => HttpResponse.json({ detail: { code: "duplicate_claim" } }, { status: 409 })),
    );
    await expect(replaceClaim(3, payload)).rejects.toBeInstanceOf(DuplicateClaimError);
  });
});
