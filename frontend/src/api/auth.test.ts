import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { getCurrentUser } from "./auth";

const user = {
  id: 1,
  email: "doc@example.test",
  full_name: "Doc Test",
  role: "physician",
  physician_type: "med_fam",
  panel_size: null,
  remuneration_type: null,
  practice_number: null,
};

describe("getCurrentUser", () => {
  it("returns the user", async () => {
    server.use(http.get("/api/auth/me", () => HttpResponse.json(user)));
    await expect(getCurrentUser()).resolves.toEqual(user);
  });

  it("returns null on a 401 (logged out)", async () => {
    server.use(http.get("/api/auth/me", () => HttpResponse.json({ detail: "Non authentifié" }, { status: 401 })));
    await expect(getCurrentUser()).resolves.toBeNull();
  });

  it("throws on a server error, so it is not mistaken for a logout", async () => {
    server.use(http.get("/api/auth/me", () => HttpResponse.json({ detail: "Erreur interne" }, { status: 500 })));
    await expect(getCurrentUser()).rejects.toThrow("Erreur interne");
  });
});
