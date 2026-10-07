import type { Claim } from "./claims";
import { unwrap, unwrapVoid } from "./http";
import { fetchAllPages } from "./paging";

export interface Bill {
  id: number;
  number: string;
  start_date: string; // ISO date (YYYY-MM-DD)
  end_date: string;
  generated_at: string;
  total_amount: number | null;
  claim_count: number;
}

export interface BillDetail extends Bill {
  claims: Claim[];
}

export interface BillCreateInput {
  start_date: string;
  end_date: string;
  claim_ids: number[];
}

export class StaleBillSelectionError extends Error {}

export async function createBill(payload: BillCreateInput): Promise<Bill> {
  const response = await fetch("/api/bills", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (response.status === 409) {
    const body = await response.json().catch(() => null);
    const detail = (body as { detail?: unknown } | null)?.detail;
    const message =
      typeof detail === "string" ? detail : "Certaines facturations ne sont plus disponibles pour cette facture.";
    throw new StaleBillSelectionError(message);
  }

  return unwrap<Bill>(response);
}

export async function listBills(page: { limit?: number; offset?: number } = {}): Promise<Bill[]> {
  const params = new URLSearchParams();
  if (page.limit != null) params.set("limit", String(page.limit));
  if (page.offset != null) params.set("offset", String(page.offset));
  const query = params.toString();
  return unwrap<Bill[]>(await fetch(`/api/bills${query ? `?${query}` : ""}`, { credentials: "same-origin" }));
}

// Every bill, newest first.
export function listAllBills(): Promise<Bill[]> {
  return fetchAllPages((limit, offset) => listBills({ limit, offset }));
}

export async function getBill(id: number): Promise<BillDetail> {
  return unwrap<BillDetail>(await fetch(`/api/bills/${id}`, { credentials: "same-origin" }));
}

export async function deleteBill(id: number): Promise<void> {
  await unwrapVoid(await fetch(`/api/bills/${id}`, { method: "DELETE", credentials: "same-origin" }));
}

// A plain same-origin URL, not a fetch wrapper: the download goes through a native
// <a href download> so the browser handles the binary response and Content-Disposition
// itself — the auth cookie rides along automatically since it's same-origin.
export function billPdfUrl(id: number): string {
  return `/api/bills/${id}/pdf`;
}
