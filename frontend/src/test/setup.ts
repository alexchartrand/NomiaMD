import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { toast } from "sonner";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

// jsdom lacks ResizeObserver, which Radix primitives (Checkbox, Select, Dialog...) rely on.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// findBy*/waitFor give up after 1 s by default, which a save → navigate → refetch chain can
// overrun when the whole suite runs in parallel on a loaded machine.
configure({ asyncUtilTimeout: 5_000 });

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
  // Sonner keeps its toasts in a module-level store, and a newly mounted <Toaster> shows the
  // ones still active: without this, one test's toast would appear in the next.
  toast.dismiss();
});
afterAll(() => server.close());
