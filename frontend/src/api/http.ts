// FastAPI's `detail` is a plain string for hand-raised HTTPExceptions (401, 400, ...) but a
// list of { msg, loc, type } objects for Pydantic validation errors (422) — stringifying
// that list directly (e.g. via `new Error(detail)`) collapses it to "[object Object]".
function extractErrorDetail(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((entry) => (entry && typeof entry === "object" && "msg" in entry ? String(entry.msg) : String(entry)))
      .join(" ");
  }
  return fallback;
}

export async function unwrap<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(extractErrorDetail(body, `La requête a échoué : ${response.status}`));
  }
  return response.json();
}

export async function unwrapVoid(response: Response): Promise<void> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(extractErrorDetail(body, `La requête a échoué : ${response.status}`));
  }
}

// A network-level fetch failure (server unreachable, connection reset) surfaces as a
// TypeError with an opaque browser message ("Failed to fetch") rather than an HTTP error.
export function describeError(err: unknown): string {
  if (err instanceof TypeError) {
    return "Impossible de joindre le serveur. Vérifiez que le serveur est démarré, puis réessayez.";
  }
  return err instanceof Error ? err.message : String(err);
}
