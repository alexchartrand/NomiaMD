import { setupServer } from "msw/node";

// No default handlers: each test declares the endpoints it needs, and an unhandled
// request fails the test (see setup.ts) so nothing silently reaches a real backend.
export const server = setupServer();
