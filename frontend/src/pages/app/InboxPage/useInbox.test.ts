import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { makeEncounterRow } from "../../../test/factories";
import { server } from "../../../test/server";
import type { EncounterPeriod } from "../../../api";
import { useInbox } from "./useInbox";

const POLL = 15_000;

// Fake timers would also freeze Testing Library's own waitFor (it polls with setInterval),
// so only intervals of the poll's length are captured; `tick()` fires them by hand.
const realSetInterval = globalThis.setInterval;
const realClearInterval = globalThis.clearInterval;
let polls: Map<number, () => void>;
let pollDelays: unknown[];

beforeEach(() => {
  polls = new Map();
  pollDelays = [];
  let nextId = 1_000_000;
  vi.spyOn(globalThis, "setInterval").mockImplementation(((fn: () => void, delay?: number) => {
    if (delay !== POLL) return realSetInterval(fn, delay);
    pollDelays.push(delay);
    polls.set(++nextId, fn);
    return nextId;
  }) as typeof setInterval);
  vi.spyOn(globalThis, "clearInterval").mockImplementation(((id?: number) => {
    if (id !== undefined && polls.delete(id)) return;
    realClearInterval(id);
  }) as typeof clearInterval);
});
afterEach(() => vi.restoreAllMocks());

const tick = () => act(async () => void [...polls.values()].forEach((fn) => fn()));

function serve(rowsFor: (params: URLSearchParams) => ReturnType<typeof makeEncounterRow>[]) {
  const requests: URLSearchParams[] = [];
  server.use(
    http.get("/api/encounters", ({ request }) => {
      const params = new URL(request.url).searchParams;
      requests.push(params);
      return HttpResponse.json(rowsFor(params));
    }),
  );
  return requests;
}

describe("useInbox", () => {
  it("loads the period's encounters and sends its bounds", async () => {
    const requests = serve(() => [makeEncounterRow({ id: 1 })]);
    const { result } = renderHook(() => useInbox({ date_from: "2026-10-05", date_to: "2026-10-11" }));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.rows.map((r) => r.id)).toEqual([1]);
    expect(requests[0].get("date_from")).toBe("2026-10-05");
    expect(requests[0].get("date_to")).toBe("2026-10-11");
  });

  it("sends no bounds for 'all'", async () => {
    const requests = serve(() => []);
    const { result } = renderHook(() => useInbox({}));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect([...requests[0].keys()]).toEqual([]);
  });

  it("reports a server error and an unreachable server", async () => {
    server.use(http.get("/api/encounters", () => HttpResponse.json({ detail: "Erreur interne" }, { status: 500 })));
    const { result } = renderHook(() => useInbox({}));
    await waitFor(() => expect(result.current.error).toBe("Erreur interne"));
    expect(result.current.loading).toBe(false);

    server.use(http.get("/api/encounters", () => HttpResponse.error()));
    await act(() => result.current.reload());
    expect(result.current.error).toMatch(/Impossible de joindre le serveur/);
  });

  it("clears a previous error on a successful reload", async () => {
    server.use(http.get("/api/encounters", () => HttpResponse.json({ detail: "Erreur" }, { status: 500 })));
    const { result } = renderHook(() => useInbox({}));
    await waitFor(() => expect(result.current.error).toBe("Erreur"));
    serve(() => [makeEncounterRow()]);
    await act(() => result.current.reload());
    expect(result.current.error).toBeNull();
    expect(result.current.rows).toHaveLength(1);
  });

  describe("polling", () => {
    it("re-reads on a 15 s interval while a row is 'reçu', then stops once none is", async () => {
      let calls = 0;
      const requests = serve(() => {
        calls += 1;
        return [makeEncounterRow({ status: calls < 3 ? "reçu" : "prêt" })];
      });
      const { result } = renderHook(() => useInbox({}));
      await waitFor(() => expect(result.current.rows[0]?.status).toBe("reçu"));
      expect(pollDelays).toEqual([POLL]);
      expect(polls.size).toBe(1);
      expect(requests).toHaveLength(1);

      await tick();
      await waitFor(() => expect(requests).toHaveLength(2));
      await tick();
      await waitFor(() => expect(result.current.rows[0].status).toBe("prêt"));
      expect(polls.size).toBe(0);
    });

    it("never polls when nothing is waiting", async () => {
      serve(() => [makeEncounterRow({ status: "prêt" })]);
      const { result } = renderHook(() => useInbox({}));
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(polls.size).toBe(0);
    });

    it("stops polling on unmount", async () => {
      serve(() => [makeEncounterRow({ status: "reçu" })]);
      const { result, unmount } = renderHook(() => useInbox({}));
      await waitFor(() => expect(polls.size).toBe(1));
      expect(result.current.rows).toHaveLength(1);
      unmount();
      expect(polls.size).toBe(0);
    });
  });

  describe("changing period", () => {
    it("drops the previous rows and loads the new period", async () => {
      serve((params) => [makeEncounterRow({ id: params.get("date_from") === "2026-10-05" ? 1 : 2 })]);
      const { result, rerender } = renderHook((period: EncounterPeriod) => useInbox(period), {
        initialProps: { date_from: "2026-10-05" } as EncounterPeriod,
      });
      await waitFor(() => expect(result.current.rows.map((r) => r.id)).toEqual([1]));
      rerender({ date_from: "2026-09-28" });
      expect(result.current.rows).toEqual([]);
      expect(result.current.loading).toBe(true);
      await waitFor(() => expect(result.current.rows.map((r) => r.id)).toEqual([2]));
    });

    it("ignores a slow answer for a period the physician has already left", async () => {
      let releaseSlow!: () => void;
      const slowGate = new Promise<void>((resolve) => (releaseSlow = resolve));
      server.use(
        http.get("/api/encounters", async ({ request }) => {
          const from = new URL(request.url).searchParams.get("date_from");
          if (from === "2026-10-05") {
            await slowGate;
            return HttpResponse.json([makeEncounterRow({ id: 1 })]);
          }
          return HttpResponse.json([makeEncounterRow({ id: 2 })]);
        }),
      );
      const { result, rerender } = renderHook((period: EncounterPeriod) => useInbox(period), {
        initialProps: { date_from: "2026-10-05" } as EncounterPeriod,
      });
      rerender({ date_from: "2026-09-28" });
      await waitFor(() => expect(result.current.rows.map((r) => r.id)).toEqual([2]));
      releaseSlow();
      await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
      expect(result.current.rows.map((r) => r.id)).toEqual([2]);
      expect(result.current.loading).toBe(false);
    });
  });
});
