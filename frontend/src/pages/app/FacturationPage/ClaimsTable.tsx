import { Fragment, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, FileSearch, Pencil, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { MANUAL_SOURCE_SYSTEM, type Claim } from "../../../api";
import {
  Badge,
  Checkbox,
  CodeChips,
  Pagination,
  RowActions,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../../components";
import { usePagination } from "../../../lib/usePagination";
import { formatDate } from "../../../utils/date";
import { formatMoney } from "../../../utils/money";
import { ClaimCodeList } from "./ClaimCodeList";
import { STATUS_LABELS } from "./constants";
import { daysLeft, isAtRisk } from "./deadline";

interface ClaimsTableProps {
  claims: Claim[];
  // Ticked draft ids; a submitted claim is never billable, so never ticked.
  selected: Set<number>;
  onToggle: (id: number) => void;
  onToggleAll: () => void;
  onDelete: (claim: Claim) => void;
  today: string;
  // Stands for the period and filters the claims are listed under: when it changes, the
  // table goes back to its first page.
  filtersKey: string;
  // Under the totals, inside the card: the selection's bar.
  footer?: ReactNode;
}

// How long a draft has left before RAMQ refuses it.
function DeadlineBadge({ serviceDate, today }: { serviceDate: string; today: string }) {
  const left = daysLeft(serviceDate, today);
  if (left < 0) return <Badge tone="danger">Délai dépassé</Badge>;
  const label = left === 0 ? "Dernier jour" : `${left} j restant${left > 1 ? "s" : ""}`;
  return (
    <Badge tone={isAtRisk(left) ? "warning" : "neutral"} title="Délai de facturation RAMQ (90 jours)">
      {label}
    </Badge>
  );
}

export function ClaimsTable({ claims, selected, onToggle, onToggleAll, onDelete, today, filtersKey, footer }: ClaimsTableProps) {
  const navigate = useNavigate();
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const toggleExpanded = (id: number) => setExpandedId(expandedId === id ? null : id);

  const drafts = claims.filter((claim) => claim.status === "brouillon");
  const tickedCount = drafts.filter((claim) => selected.has(claim.id)).length;
  const allTicked = drafts.length > 0 && tickedCount === drafts.length;
  const listedTotal = claims.reduce((sum, claim) => sum + (claim.total_amount ?? 0), 0);
  const pages = usePagination(claims, filtersKey);
  const listRef = useRef<HTMLDivElement>(null);

  return (
    // `clip`, not `hidden`: it rounds the corners without becoming a scroll container, which
    // would keep the footer's sticky bar from sticking to the screen.
    <div ref={listRef} className="scroll-mt-4 overflow-clip rounded-xl border border-border bg-card">
      <Table>
        <TableHeader className="bg-muted/40">
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-10 pl-4">
              {/* Every draft listed, on every page: what "Créer une facture" ticks too. */}
              {drafts.length > 0 && (
                <Checkbox
                  checked={allTicked ? true : tickedCount > 0 ? "indeterminate" : false}
                  onCheckedChange={onToggleAll}
                  aria-label="Sélectionner tous les brouillons"
                />
              )}
            </TableHead>
            <TableHead className="w-10" aria-label="Détails" />
            <TableHead>Date</TableHead>
            <TableHead>Patient</TableHead>
            <TableHead>Codes</TableHead>
            <TableHead className="text-right">Total</TableHead>
            <TableHead>Statut</TableHead>
            <TableHead className="w-12" aria-label="Actions" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {pages.items.map((claim) => {
            const draft = claim.status === "brouillon";
            // Billed without an encounter: edited on the Facturer page (an encounter's claim
            // is edited from its review instead).
            const manual = claim.source_system === MANUAL_SOURCE_SYSTEM;
            const expanded = expandedId === claim.id;
            const ticked = selected.has(claim.id);
            return (
              <Fragment key={claim.id}>
                <TableRow
                  data-state={ticked ? "selected" : undefined}
                  className="cursor-pointer"
                  onClick={(event) => {
                    if (!(event.target as HTMLElement).closest("button, a, [role=menuitem], [data-select-cell]")) toggleExpanded(claim.id);
                  }}
                >
                  {/* The whole cell ticks, not just the box: an easier target down a long list. */}
                  <TableCell
                    data-select-cell
                    className="pl-4"
                    onClick={(event) => {
                      if (draft && !(event.target as HTMLElement).closest("button")) onToggle(claim.id);
                    }}
                  >
                    {draft && (
                      <Checkbox
                        checked={ticked}
                        onCheckedChange={() => onToggle(claim.id)}
                        aria-label={`Sélectionner la réclamation de ${claim.patient_full_name}`}
                      />
                    )}
                  </TableCell>
                  <TableCell>
                    <button
                      type="button"
                      aria-label="Détails"
                      aria-expanded={expanded}
                      onClick={() => toggleExpanded(claim.id)}
                      className="inline-flex size-7 cursor-pointer items-center justify-center rounded-md border-none bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground"
                    >
                      <ChevronDown aria-hidden className={cn("size-4 transition-transform", expanded && "rotate-180")} />
                    </button>
                  </TableCell>
                  <TableCell className="tabular-nums">{formatDate(claim.service_date)}</TableCell>
                  <TableCell>
                    <span className="font-semibold">{claim.patient_full_name}</span>
                    {manual && <Badge className="ml-2">Sans rencontre</Badge>}
                  </TableCell>
                  <TableCell>
                    <CodeChips codes={claim.codes.map((c) => c.code)} />
                  </TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">
                    {claim.total_amount != null ? formatMoney(claim.total_amount) : "—"}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={draft ? "primary" : "success"}>{STATUS_LABELS[claim.status]}</Badge>
                      {draft && <DeadlineBadge serviceDate={claim.service_date} today={today} />}
                    </div>
                  </TableCell>
                  <TableCell className="pr-3 text-right">
                    <RowActions
                      label={`Actions — réclamation de ${claim.patient_full_name}`}
                      actions={[
                        {
                          label: "Voir la rencontre",
                          icon: FileSearch,
                          onSelect: () => navigate(`/app/inbox/${claim.encounter_id}`),
                          disabled: claim.encounter_id == null,
                        },
                        {
                          label: "Modifier",
                          icon: Pencil,
                          onSelect: () => navigate(`/app/facturer/${claim.id}`),
                          disabled: !(manual && draft),
                        },
                        { label: "Supprimer", icon: Trash2, danger: true, onSelect: () => onDelete(claim), disabled: !draft },
                      ]}
                    />
                  </TableCell>
                </TableRow>
                {expanded && (
                  <TableRow className="bg-muted/30 hover:bg-muted/30">
                    <TableCell colSpan={8} className="px-6 py-3 whitespace-normal">
                      <ClaimCodeList codes={claim.codes} />
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
          {claims.length} réclamation{claims.length > 1 ? "s" : ""}
        </span>
        <span>
          Total <span className="font-semibold tabular-nums">{formatMoney(listedTotal)}</span>
        </span>
      </div>
      <Pagination
        {...pages}
        onChange={pages.setPage}
        listRef={listRef}
        className="border-t border-border bg-muted/40 px-4 py-2"
      />
      {footer}
    </div>
  );
}
