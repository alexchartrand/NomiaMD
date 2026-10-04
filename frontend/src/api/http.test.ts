import { describeError, extractErrorDetail, unwrap, unwrapVoid } from "./http";

describe("extractErrorDetail", () => {
  it("returns a string detail as is", () => {
    expect(extractErrorDetail({ detail: "Non autorisé" }, "fallback")).toBe("Non autorisé");
  });

  it("joins the msg of a 422 validation list", () => {
    const body = { detail: [{ msg: "champ requis" }, { msg: "NAM invalide" }] };
    expect(extractErrorDetail(body, "fallback")).toBe("champ requis NAM invalide");
  });

  it("falls back when the string detail is empty", () => {
    expect(extractErrorDetail({ detail: "" }, "fallback")).toBe("fallback");
  });

  it("falls back when there is no usable detail", () => {
    expect(extractErrorDetail(null, "fallback")).toBe("fallback");
  });
});

describe("unwrap", () => {
  it("uses the status text when the body is not JSON", async () => {
    const response = new Response("oops", { status: 500, statusText: "Server Error" });
    await expect(unwrap(response)).rejects.toThrow("Server Error");
  });

  it("falls back to the status code when the body is not JSON and statusText is empty", async () => {
    const response = new Response("oops", { status: 500, statusText: "" });
    await expect(unwrap(response)).rejects.toThrow("La requête a échoué : 500");
  });

  it("falls back to the status code for unwrapVoid too", async () => {
    const response = new Response("oops", { status: 502, statusText: "" });
    await expect(unwrapVoid(response)).rejects.toThrow("La requête a échoué : 502");
  });
});

describe("describeError", () => {
  it("maps a network TypeError to the French unreachable message", () => {
    expect(describeError(new TypeError("Failed to fetch"))).toMatch(/Impossible de joindre le serveur/);
  });
});
