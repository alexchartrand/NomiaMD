import { Fragment, useEffect, useState } from "react";
import {
  billPdfUrl,
  deleteBill,
  describeError,
  getBill,
  listBills,
  type Bill,
  type BillDetail,
} from "../../../api";
import { Banner, Button, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../../components";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatDate } from "../../../utils/date";

interface BillsTabProps {
  reloadSignal: number;
  onChanged: () => void;
}

export function BillsTab({ reloadSignal, onChanged }: BillsTabProps) {
  const [bills, setBills] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [expandedDetail, setExpandedDetail] = useState<BillDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  function loadBills() {
    setLoading(true);
    setListError(null);
    listBills()
      .then(setBills)
      .catch((err) => setListError(describeError(err)))
      .finally(() => setLoading(false));
  }

  useEffect(loadBills, [reloadSignal]);

  async function toggleExpand(bill: Bill) {
    if (expandedId === bill.id) {
      setExpandedId(null);
      setExpandedDetail(null);
      return;
    }
    setExpandedId(bill.id);
    setExpandedDetail(null);
    setDetailError(null);
    try {
      setExpandedDetail(await getBill(bill.id));
    } catch (err) {
      setDetailError(describeError(err));
    }
  }

  async function handleDelete(bill: Bill) {
    if (
      !window.confirm(
        `Supprimer la facture ${bill.number} ? Les ${bill.record_count} réclamation(s) qu'elle contient redeviendront des brouillons.`,
      )
    )
      return;
    try {
      await deleteBill(bill.id);
      if (expandedId === bill.id) {
        setExpandedId(null);
        setExpandedDetail(null);
      }
      loadBills();
      onChanged();
    } catch (err) {
      setListError(describeError(err));
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">Chargement...</p>;
  if (listError) return <Banner tone="error">{listError}</Banner>;
  if (bills.length === 0) return <p>Aucune facture générée.</p>;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Numéro</TableHead>
          <TableHead>Période</TableHead>
          <TableHead>Générée le</TableHead>
          <TableHead>Facturations</TableHead>
          <TableHead>Total</TableHead>
          <TableHead>Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {bills.map((bill) => (
          <Fragment key={bill.id}>
            <TableRow>
              <TableCell>{bill.number}</TableCell>
              <TableCell>
                {formatDate(bill.start_date)} – {formatDate(bill.end_date)}
              </TableCell>
              <TableCell>{formatDate(bill.generated_at.slice(0, 10))}</TableCell>
              <TableCell>
                {bill.record_count}{" "}
                <Button type="button" variant="link" onClick={() => toggleExpand(bill)}>
                  Détails
                </Button>
              </TableCell>
              <TableCell>{bill.total_amount != null ? `${bill.total_amount.toFixed(2)} $` : "—"}</TableCell>
              <TableCell>
                <div className="flex gap-2">
                  <a
                    className={cn(buttonVariants({ variant: "secondary" }), "border-border")}
                    href={billPdfUrl(bill.id)}
                    download
                  >
                    Télécharger le PDF
                  </a>
                  <Button type="button" variant="danger" onClick={() => handleDelete(bill)}>
                    Supprimer
                  </Button>
                </div>
              </TableCell>
            </TableRow>
            {expandedId === bill.id && (
              <TableRow className="bg-[color:var(--color-primary-tint)] hover:bg-[color:var(--color-primary-tint)]">
                <TableCell colSpan={6}>
                  {detailError && <Banner tone="error">{detailError}</Banner>}
                  {!detailError && !expandedDetail && (
                    <p className="text-sm text-muted-foreground">Chargement...</p>
                  )}
                  {expandedDetail && (
                    <ul className="m-0 space-y-2 pl-5">
                      {expandedDetail.claims.map((c) => (
                        <li key={c.id}>
                          {formatDate(c.service_date)} — {c.patient_full_name} —{" "}
                          {c.codes.map((code) => code.code).join(", ")}
                          {c.total_amount != null && ` — ${c.total_amount.toFixed(2)} $`}
                        </li>
                      ))}
                    </ul>
                  )}
                </TableCell>
              </TableRow>
            )}
          </Fragment>
        ))}
      </TableBody>
    </Table>
  );
}
