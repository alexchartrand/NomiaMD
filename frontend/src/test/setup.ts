import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { toast } from "sonner";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

// jsdom lacks ResizeObserver, which Radix primitives (Checkbox, Select, Dialog...) rely on.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
  // Sonner keeps its toasts in a module-level store, and a newly mounted <Toaster> shows the
  // ones still active: without this, one test's toast would appear in the next.
  toast.dismiss();
});
afterAll(() => server.close());
