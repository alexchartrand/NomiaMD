import { Fragment, useEffect, useState } from "react";
import { ChevronDown, Download, FileText, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  billPdfUrl,
  deleteBill,
  describeError,
  getBill,
  listBills,
  type Bill,
  type BillDetail,
} from "../../../api";
import {
  Banner,
  Button,
  CodeChips,
  EmptyState,
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

interface BillsTabProps {
  reloadSignal: number;
  onChanged: () => void;
}

export function BillsTab({ reloadSignal, onChanged }: BillsTabProps) {
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

  if (loading) {
    return (
      <div aria-busy="true" aria-label="Chargement des factures" className="flex flex-col gap-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-12 rounded-lg" />
        ))}
      </div>
    );
  }
  if (listError) return <Banner tone="error">{listError}</Banner>;
  if (bills.length === 0) {
    return (
      <>
        {dialog}
        <EmptyState
          icon={FileText}
          title="Aucune facture générée."
          description="Regroupez vos réclamations en brouillon dans une facture, à télécharger en PDF."
        />
      </>
    );
  }

  return (
    <>
      {dialog}
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
            {bills.map((bill) => {
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
      </div>
    </>
  );
}
