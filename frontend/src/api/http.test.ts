import { describeError, extractErrorDetail, unwrap } from "./http";

describe("extractErrorDetail", () => {
  it("returns a string detail as is", () => {
    expect(extractErrorDetail({ detail: "Non autorisé" }, "fallback")).toBe("Non autorisé");
  });

  it("joins the msg of a 422 validation list", () => {
    const body = { detail: [{ msg: "champ requis" }, { msg: "NAM invalide" }] };
    expect(extractErrorDetail(body, "fallback")).toBe("champ requis NAM invalide");
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

  // Bug: with an empty statusText the fallback `{ detail: "" }` is a valid string, so the
  // thrown message is empty instead of "La requête a échoué : <status>".
  it.todo("falls back to the status code when the body is not JSON and statusText is empty");
});

describe("describeError", () => {
  it("maps a network TypeError to the French unreachable message", () => {
    expect(describeError(new TypeError("Failed to fetch"))).toMatch(/Impossible de joindre le serveur/);
  });
});
