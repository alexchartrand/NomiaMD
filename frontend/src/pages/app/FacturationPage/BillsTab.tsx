import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, Download, FileSearch, FileText, SearchX, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  billPdfUrl,
  deleteBill,
  describeError,
  getBill,
  listAllBills,
  type Bill,
  type BillDetail,
} from "../../../api";
import {
  Banner,
  Button,
  CodeChips,
  EmptyState,
  PeriodFilter,
  RowActions,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  useConfirm,
} from "../../../components";
import { formatDate } from "../../../utils/date";
import { formatMoney } from "../../../utils/money";
import type { Period } from "../../../utils/periods";

interface BillsTabProps {
  reloadSignal: number;
  onChanged: () => void;
  period: Period;
  onPeriodChange: (period: Period) => void;
}

// A bill belongs to a period when the dates it covers overlap it.
function overlaps(bill: Bill, period: Period): boolean {
  if (period.date_from && bill.end_date < period.date_from) return false;
  if (period.date_to && bill.start_date > period.date_to) return false;
  return true;
}

export function BillsTab({ reloadSignal, onChanged, period, onPeriodChange }: BillsTabProps) {
  const { confirm, dialog } = useConfirm();
  const [bills, setBills] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [expandedDetail, setExpandedDetail] = useState<BillDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  function loadBills() {
    setLoading(true);
    setListError(null);
    setDeleteError(null);
    listAllBills()
      .then(setBills)
      .catch((err) => setListError(describeError(err)))
      .finally(() => setLoading(false));
  }

  useEffect(loadBills, [reloadSignal]);

  const shown = useMemo(() => bills.filter((bill) => overlaps(bill, period)), [bills, period.date_from, period.date_to]);
  const shownTotal = shown.reduce((sum, bill) => sum + (bill.total_amount ?? 0), 0);

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
    const confirmed = await confirm({
      title: `Supprimer la facture ${bill.number} ?`,
      message: `Les ${bill.claim_count} réclamation(s) qu'elle contient redeviendront des brouillons.`,
      confirmLabel: "Supprimer",
      tone: "danger",
    });
    if (!confirmed) return;
    setDeleteError(null);
    try {
      await deleteBill(bill.id);
      if (expandedId === bill.id) {
        setExpandedId(null);
        setExpandedDetail(null);
      }
      loadBills();
      onChanged();
    } catch (err) {
      setDeleteError(describeError(err));
    }
  }

  const periodFilter = (
    <div className="mb-5 rounded-xl border border-border bg-card px-4 py-3">
      <PeriodFilter period={period} onChange={onPeriodChange} idPrefix="bills-period" />
    </div>
  );

  if (loading) {
    return (
      <>
        {periodFilter}
        <div aria-busy="true" aria-label="Chargement des factures" className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-12 rounded-lg" />
          ))}
        </div>
      </>
    );
  }
  if (listError) {
    return (
      <>
        {periodFilter}
        <Banner tone="error">{listError}</Banner>
      </>
    );
  }
  if (shown.length === 0) {
    return (
      <>
        {dialog}
        {periodFilter}
        {bills.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="Aucune facture générée."
            description="Cochez vos réclamations en brouillon pour les regrouper dans une facture, à télécharger en PDF."
          />
        ) : (
          <EmptyState icon={SearchX} title="Aucune facture pour cette période." />
        )}
      </>
    );
  }

  return (
    <>
      {dialog}
      {periodFilter}
      {deleteError && <Banner tone="error" className="mb-4">{deleteError}</Banner>}
      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <Table>
          <TableHeader className="bg-muted/40">
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-10 pl-3" aria-label="Détails" />
              <TableHead>Numéro</TableHead>
              <TableHead>Période</TableHead>
              <TableHead>Générée le</TableHead>
              <TableHead className="text-right">Réclamations</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead className="w-0" aria-label="Actions" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((bill) => {
              const expanded = expandedId === bill.id;
              return (
                <Fragment key={bill.id}>
                  <TableRow
                    className="cursor-pointer"
                    onClick={(event) => {
                      if (!(event.target as HTMLElement).closest("button, a, [role=menuitem]")) void toggleExpand(bill);
                    }}
                  >
                    <TableCell className="pl-3">
                      <button
                        type="button"
                        aria-label="Détails"
                        aria-expanded={expanded}
                        onClick={() => void toggleExpand(bill)}
                        className="inline-flex size-7 cursor-pointer items-center justify-center rounded-md border-none bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground"
                      >
                        <ChevronDown aria-hidden className={cn("size-4 transition-transform", expanded && "rotate-180")} />
                      </button>
                    </TableCell>
                    <TableCell className="font-mono font-semibold">{bill.number}</TableCell>
                    <TableCell className="tabular-nums">
                      {formatDate(bill.start_date)} – {formatDate(bill.end_date)}
                    </TableCell>
                    <TableCell className="tabular-nums">{formatDate(bill.generated_at.slice(0, 10))}</TableCell>
                    <TableCell className="text-right tabular-nums">{bill.claim_count}</TableCell>
                    <TableCell className="text-right font-semibold tabular-nums">
                      {bill.total_amount != null ? formatMoney(bill.total_amount) : "—"}
                    </TableCell>
                    <TableCell className="pr-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button asChild variant="secondary">
                          <a href={billPdfUrl(bill.id)} download aria-label="Télécharger le PDF">
                            <Download aria-hidden />
                            PDF
                          </a>
                        </Button>
                        <RowActions
                          label={`Actions — facture ${bill.number}`}
                          actions={[{ label: "Supprimer", icon: Trash2, danger: true, onSelect: () => handleDelete(bill) }]}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                  {expanded && (
                    <TableRow className="bg-muted/30 hover:bg-muted/30">
                      <TableCell colSpan={7} className="px-6 py-3 whitespace-normal">
                        {detailError && <Banner tone="error">{detailError}</Banner>}
                        {!detailError && !expandedDetail && <Skeleton className="h-16 rounded-lg" />}
                        {expandedDetail && (
                          <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
                            {expandedDetail.claims.map((c) => (
                              <li key={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-1">
                                <span className="w-24 tabular-nums text-muted-foreground">{formatDate(c.service_date)}</span>
                                <span className="min-w-40 font-semibold">{c.patient_full_name}</span>
                                <CodeChips codes={c.codes.map((code) => code.code)} />
                                {c.encounter_id != null && (
                                  <Link
                                    to={`/app/inbox/${c.encounter_id}`}
                                    className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"
                                  >
                                    <FileSearch aria-hidden className="size-3.5" />
                                    Voir la rencontre
                                  </Link>
                                )}
                                {c.total_amount != null && (
                                  <span className="ml-auto font-semibold tabular-nums">{formatMoney(c.total_amount)}</span>
                                )}
                              </li>
                            ))}
                          </ul>
                        )}
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
        <div className="flex items-center justify-between border-t border-border bg-muted/40 px-4 py-2.5 text-sm">
          <span className="text-muted-foreground">
            {shown.length} facture{shown.length > 1 ? "s" : ""}
          </span>
          <span>
            Total <span className="font-semibold tabular-nums">{formatMoney(shownTotal)}</span>
          </span>
        </div>
      </div>
    </>
  );
}
