import { type ReactNode } from "react";
import { Trash2 } from "lucide-react";
import { CARE_SETTING_LABELS, type ShiftClaim } from "../../../api";
import {
  Badge,
  Checkbox,
  RowActions,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../../components";
import { formatDate } from "../../../utils/date";
import { formatMoney } from "../../../utils/money";
import { STATUS_LABELS } from "./constants";

interface ShiftClaimsTableProps {
  claims: ShiftClaim[];
  selected: Set<number>;
  onToggle: (id: number) => void;
  onDelete: (claim: ShiftClaim) => void;
  footer?: ReactNode;
}

const hhmm = (time: string) => time.slice(0, 5);

// The shifts' own claims (09791, 19953…): billed for the hours worked, no patient. Saved
// from the shift on the schedule; ticked and billed here with the patients' claims.
export function ShiftClaimsTable({ claims, selected, onToggle, onDelete, footer }: ShiftClaimsTableProps) {
  const total = claims.reduce((sum, claim) => sum + (claim.total_amount ?? 0), 0);
  return (
    <section aria-label="Réclamations de quart" className="overflow-clip rounded-xl border border-border bg-card">
      <h3 className="m-0 border-b border-border px-4 py-2.5 font-heading text-base font-semibold">Quarts</h3>
      <Table>
        <TableHeader className="bg-muted/40">
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-10 pl-4" aria-label="Sélection" />
            <TableHead>Date</TableHead>
            <TableHead>Quart</TableHead>
            <TableHead>Codes</TableHead>
            <TableHead className="text-right">Total</TableHead>
            <TableHead>Statut</TableHead>
            <TableHead className="w-12" aria-label="Actions" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {claims.map((claim) => {
            const draft = claim.status === "brouillon";
            const label = `${claim.work_site_name}, ${hhmm(claim.start_time)}–${hhmm(claim.end_time)}`;
            return (
              <TableRow key={claim.id} data-state={selected.has(claim.id) ? "selected" : undefined}>
                <TableCell className="pl-4">
                  {draft && (
                    <Checkbox
                      checked={selected.has(claim.id)}
                      onCheckedChange={() => onToggle(claim.id)}
                      aria-label={`Sélectionner le quart ${label}`}
                    />
                  )}
                </TableCell>
                <TableCell className="tabular-nums">{formatDate(claim.service_date)}</TableCell>
                <TableCell>
                  <span className="font-semibold">{claim.work_site_name}</span>{" "}
                  <span className="text-sm text-muted-foreground">
                    {CARE_SETTING_LABELS[claim.care_setting]}, {hhmm(claim.start_time)}–{hhmm(claim.end_time)}
                    {claim.ends_next_day && " +1"}
                  </span>
                </TableCell>
                <TableCell>
                  <span className="flex flex-wrap gap-1">
                    {claim.codes.map((code) => (
                      <Badge
                        key={code.code}
                        tone="neutral"
                        title={`${code.description} — secteur ${code.secteur_dispensation} (${code.secteur_dispensation_label})`}
                      >
                        {code.code} · {code.hours} h
                      </Badge>
                    ))}
                  </span>
                </TableCell>
                <TableCell className="text-right font-semibold tabular-nums">
                  {claim.total_amount != null ? formatMoney(claim.total_amount) : "—"}
                </TableCell>
                <TableCell>
                  <Badge tone={draft ? "primary" : "success"}>{STATUS_LABELS[claim.status]}</Badge>
                </TableCell>
                <TableCell className="pr-3 text-right">
                  <RowActions
                    label={`Actions — quart ${label}`}
                    actions={[
                      { label: "Supprimer", icon: Trash2, danger: true, onSelect: () => onDelete(claim), disabled: !draft },
                    ]}
                  />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <div className="flex items-center justify-between border-t border-border bg-muted/40 px-4 py-2.5 text-sm">
        <span className="text-muted-foreground">
          {claims.length} quart{claims.length > 1 ? "s" : ""}
        </span>
        <span>
          Total <span className="font-semibold tabular-nums">{formatMoney(total)}</span>
        </span>
      </div>
      {footer}
    </section>
  );
}
