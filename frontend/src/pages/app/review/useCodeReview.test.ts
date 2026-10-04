import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { makeClaim, makeClaimLine, makeExtraction, makeFee, makeProposedCode } from "../../../test/factories";
import { server } from "../../../test/server";
import type { BillingExtractionResponse, Claim } from "../../../api";
import { useCodeReview } from "./useCodeReview";

const dollars = makeProposedCode({ code: "00103", fees: [makeFee({ amount: 50 }), makeFee({ amount: 70, role: 2 })] });
const units = makeProposedCode({ code: "09001", fees: [makeFee({ amount: 8, unit: "unités" })] });
const noFee = makeProposedCode({ code: "99998", fees: [] });
const result = makeExtraction([dollars, units, noFee], { extraction_run_id: 42 });

interface Props {
  result: BillingExtractionResponse | null;
  readOnly?: boolean;
  claim?: Claim | null;
  onSaved?: () => void;
}

function setup(initial: Props = { result }) {
  return renderHook((props: Props) => useCodeReview(props.result, props.readOnly, props.claim ?? null, props.onSaved), {
    initialProps: initial,
  });
}

// Waits for the "extracted" dispatch from the effect to land.
async function loaded(view: ReturnType<typeof setup>) {
  await waitFor(() => expect(view.result.current.state.result).not.toBeNull());
}

function captureClaims() {
  const calls: { method: string; url: URL; body: unknown }[] = [];
  const handler = async ({ request }: { request: Request }) => {
    calls.push({ method: request.method, url: new URL(request.url), body: await request.json() });
    return HttpResponse.json(makeClaim());
  };
  server.use(http.post("/api/claims", handler), http.put("/api/claims/:id", handler));
  return calls;
}

afterEach(() => vi.restoreAllMocks());

describe("totals", () => {
  it("sums dollar fees of the ticked codes, using the default fee first", async () => {
    const view = setup();
    await loaded(view);
    act(() => view.result.current.toggleCode(0));
    expect(view.result.current.totalAmount).toBe(50);
    act(() => view.result.current.selectFee(0, 1));
    expect(view.result.current.totalAmount).toBe(70);
  });

  it("does not count a fee in units toward the dollar total, and flags it as missing a fee", async () => {
    const view = setup();
    await loaded(view);
    act(() => {
      view.result.current.toggleCode(0);
      view.result.current.toggleCode(1);
    });
    expect(view.result.current.totalAmount).toBe(50);
    expect(view.result.current.codesMissingFee).toBe(1);
  });

  it("counts a code without any fee as missing one", async () => {
    const view = setup();
    await loaded(view);
    act(() => view.result.current.toggleCode(2));
    expect(view.result.current.totalAmount).toBe(0);
    expect(view.result.current.codesMissingFee).toBe(1);
  });
});

describe("canSave", () => {
  it("needs a ticked code", async () => {
    const view = setup();
    await loaded(view);
    expect(view.result.current.canSave).toBe(false);
    act(() => view.result.current.toggleCode(0));
    expect(view.result.current.canSave).toBe(true);
  });

  it("needs a service date", async () => {
    const view = setup({ result: makeExtraction([dollars], { encounter_date: null }) });
    await loaded(view);
    act(() => view.result.current.toggleCode(0));
    expect(view.result.current.canSave).toBe(false);
    act(() => view.result.current.changeServiceDate("2026-10-02"));
    expect(view.result.current.canSave).toBe(true);
  });

  it("is false when read-only", async () => {
    const view = setup({ result, readOnly: true });
    await loaded(view);
    act(() => view.result.current.toggleCode(0));
    expect(view.result.current.canSave).toBe(false);
  });

  it("is false for a saved claim until something changes", async () => {
    const claim = makeClaim({ codes: [makeClaimLine({ code: "00103" })] });
    const view = setup({ result, claim });
    await waitFor(() => expect(view.result.current.state.selection.size).toBe(1));
    expect(view.result.current.editing).toBe(true);
    expect(view.result.current.canSave).toBe(false);
    act(() => view.result.current.selectFee(0, 1));
    expect(view.result.current.canSave).toBe(true);
  });
});

describe("save", () => {
  it("creates a claim from the extraction run with the chosen fee", async () => {
    const calls = captureClaims();
    const onSaved = vi.fn();
    const view = setup({ result, onSaved });
    await loaded(view);
    act(() => {
      view.result.current.toggleCode(0);
      view.result.current.selectFee(0, 1);
    });
    await act(() => view.result.current.save());
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].url.searchParams.get("confirm_duplicate")).toBe("false");
    expect(calls[0].body).toEqual({
      extraction_run_id: 42,
      service_date: "2026-10-01",
      selected_codes: [{ code: "00103", fee_index: 1 }],
    });
    expect(view.result.current.state.saved).toBe(true);
    expect(onSaved).toHaveBeenCalledOnce();
  });

  it("sends a null fee index for a code with no fees", async () => {
    const calls = captureClaims();
    const view = setup();
    await loaded(view);
    act(() => view.result.current.toggleCode(2));
    await act(() => view.result.current.save());
    expect(calls[0].body).toMatchObject({ selected_codes: [{ code: "99998", fee_index: null }] });
  });

  it("replaces the existing claim when editing", async () => {
    const calls = captureClaims();
    const claim = makeClaim({ id: 9, codes: [makeClaimLine({ code: "00103" })] });
    const view = setup({ result, claim });
    await waitFor(() => expect(view.result.current.state.selection.size).toBe(1));
    act(() => view.result.current.selectFee(0, 1));
    await act(() => view.result.current.save());
    expect(calls[0].method).toBe("PUT");
    expect(calls[0].url.pathname).toBe("/api/claims/9");
  });

  it("does nothing when nothing is ticked or when read-only", async () => {
    const calls = captureClaims();
    const view = setup({ result, readOnly: true });
    await loaded(view);
    act(() => view.result.current.toggleCode(0));
    await act(() => view.result.current.save());
    expect(calls).toHaveLength(0);
    expect(view.result.current.state.saved).toBe(false);
  });

  it("surfaces a server error and does not call onSaved", async () => {
    server.use(http.post("/api/claims", () => HttpResponse.json({ detail: "Patient introuvable" }, { status: 404 })));
    const onSaved = vi.fn();
    const view = setup({ result, onSaved });
    await loaded(view);
    act(() => view.result.current.toggleCode(0));
    await act(() => view.result.current.save());
    expect(view.result.current.state.saveError).toBe("Patient introuvable");
    expect(view.result.current.state.saving).toBe(false);
    expect(onSaved).not.toHaveBeenCalled();
  });
});

describe("duplicate claim", () => {
  const duplicate = { detail: { code: "duplicate_claim", message: "Déjà facturé." } };

  it("asks for confirmation, then retries with confirm_duplicate=true", async () => {
    const flags: (string | null)[] = [];
    server.use(
      http.post("/api/claims", ({ request }) => {
        const flag = new URL(request.url).searchParams.get("confirm_duplicate");
        flags.push(flag);
        return flag === "true" ? HttpResponse.json(makeClaim()) : HttpResponse.json(duplicate, { status: 409 });
      }),
    );
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const view = setup();
    await loaded(view);
    act(() => view.result.current.toggleCode(0));
    await act(() => view.result.current.save());
    expect(confirm).toHaveBeenCalledWith("Déjà facturé. Enregistrer quand même ?");
    expect(flags).toEqual(["false", "true"]);
    expect(view.result.current.state.saved).toBe(true);
  });

  it("stops without an error when the physician declines", async () => {
    server.use(http.post("/api/claims", () => HttpResponse.json(duplicate, { status: 409 })));
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const view = setup();
    await loaded(view);
    act(() => view.result.current.toggleCode(0));
    await act(() => view.result.current.save());
    expect(view.result.current.state).toMatchObject({ saving: false, saved: false, saveError: null });
  });

  it("does not loop when the confirmed retry is refused as a duplicate again", async () => {
    let attempts = 0;
    server.use(
      http.post("/api/claims", () => {
        attempts += 1;
        return HttpResponse.json(duplicate, { status: 409 });
      }),
    );
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const view = setup();
    await loaded(view);
    act(() => view.result.current.toggleCode(0));
    await act(() => view.result.current.save());
    expect(attempts).toBe(2);
    expect(confirm).toHaveBeenCalledOnce();
    expect(view.result.current.state.saveError).toBe("Déjà facturé.");
  });
});

describe("a new result", () => {
  it("resets the selection", async () => {
    const view = setup();
    await loaded(view);
    act(() => view.result.current.toggleCode(0));
    view.rerender({ result: makeExtraction([units]) });
    await waitFor(() => expect(view.result.current.state.selection.size).toBe(0));
  });

  it("clears when the result goes away", async () => {
    const view = setup();
    await loaded(view);
    view.rerender({ result: null });
    await waitFor(() => expect(view.result.current.state.result).toBeNull());
  });
});
