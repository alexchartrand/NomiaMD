import { Fragment, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, FileStack, Pencil, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  deleteClaim,
  describeError,
  listClaims,
  listRoster,
  MANUAL_SOURCE_SYSTEM,
  type Claim,
  type ClaimFilters,
  type ClaimStatus,
  type Patient,
} from "../../../api";
import {
  Badge,
  Banner,
  CodeChips,
  EmptyState,
  RowActions,
  SegmentedControl,
  Select,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TextField,
  useConfirm,
} from "../../../components";
import { formatDate } from "../../../utils/date";
import { formatMoney } from "../../../utils/money";
import { ClaimCodeList } from "./ClaimCodeList";
import { STATUS_LABELS } from "./constants";

export type StatusFilter = ClaimStatus | "";

const STATUS_SEGMENTS: { id: StatusFilter | "tous"; label: string }[] = [
  { id: "tous", label: "Toutes" },
  { id: "brouillon", label: "Brouillons" },
  { id: "soumis", label: "Soumises" },
];

interface RecordsTabProps {
  reloadSignal: number;
  // Kept in the URL by the page, so the dashboard can link to the drafts.
  status: StatusFilter;
  onStatusChange: (status: StatusFilter) => void;
}

export function RecordsTab({ reloadSignal, status, onStatusChange }: RecordsTabProps) {
  const navigate = useNavigate();
  const { confirm, dialog } = useConfirm();
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientFilter, setPatientFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    // Roster-scoped, not every known patient: claims are no longer roster-gated (see
    // app/postgresdb/models.py's Patient), so a patient billed here but never added to
    // "my patients" won't appear in this filter dropdown yet — a known minor gap.
    listRoster()
      .then(setPatients)
      .catch((err) => setListError(describeError(err)));
  }, []);

  function loadClaims() {
    setLoading(true);
    setListError(null);
    const filters: ClaimFilters = {};
    if (patientFilter) filters.patient_id = Number(patientFilter);
    if (dateFrom) filters.date_from = dateFrom;
    if (dateTo) filters.date_to = dateTo;
    if (status) filters.status = status;

    listClaims(filters)
      .then(setClaims)
      .catch((err) => setListError(describeError(err)))
      .finally(() => setLoading(false));
  }

  // reloadSignal changes after a bill is generated/deleted on the other tab — claims may
  // have moved between "brouillon" and "soumis" without this tab knowing.
  useEffect(loadClaims, [patientFilter, dateFrom, dateTo, status, reloadSignal]);

  async function handleDelete(claim: Claim) {
    const confirmed = await confirm({
      title: "Supprimer la réclamation ?",
      message: `La réclamation de ${claim.patient_full_name} du ${formatDate(claim.service_date)} sera supprimée. Cette action est irréversible.`,
      confirmLabel: "Supprimer",
      tone: "danger",
    });
    if (!confirmed) return;
    try {
      await deleteClaim(claim.id);
      loadClaims();
    } catch (err) {
      setListError(describeError(err));
    }
  }

  const toggle = (id: number) => setExpandedId(expandedId === id ? null : id);
  const listedTotal = claims.reduce((sum, claim) => sum + (claim.total_amount ?? 0), 0);
  const filtered = Boolean(patientFilter || dateFrom || dateTo || status);

  return (
    <>
      {dialog}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl
          ariaLabel="Statut"
          segments={STATUS_SEGMENTS}
          value={status || "tous"}
          onChange={(id) => onStatusChange(id === "tous" ? "" : id)}
        />
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <Select
            id="filter-patient"
            aria-label="Patient"
            containerClassName="w-52"
            value={patientFilter}
            onChange={(e) => setPatientFilter(e.target.value)}
          >
            <option value="">Tous les patients</option>
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.full_name}
              </option>
            ))}
          </Select>
          <label htmlFor="filter-date-from" className="text-sm text-muted-foreground">
            Du
          </label>
          <TextField
            id="filter-date-from"
            type="date"
            className="w-auto"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
          <label htmlFor="filter-date-to" className="text-sm text-muted-foreground">
            Au
          </label>
          <TextField
            id="filter-date-to"
            type="date"
            className="w-auto"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </div>
      </div>

      {listError && <Banner tone="error" className="mb-4">{listError}</Banner>}

      {loading ? (
        <div aria-busy="true" aria-label="Chargement des réclamations" className="flex flex-col gap-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-12 rounded-lg" />
          ))}
        </div>
      ) : claims.length === 0 ? (
        <EmptyState
          icon={FileStack}
          title="Aucune réclamation enregistrée."
          description={
            filtered
              ? "Aucune réclamation ne correspond à ces filtres."
              : "Les réclamations apparaissent ici dès que vous enregistrez la révision d'une rencontre."
          }
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-10 pl-3" aria-label="Détails" />
                <TableHead>Date</TableHead>
                <TableHead>Patient</TableHead>
                <TableHead>Codes</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead>Statut</TableHead>
                <TableHead className="w-12" aria-label="Actions" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {claims.map((claim) => {
                const deletable = claim.status === "brouillon";
                // Billed without an encounter: edited on the Facturer page (an encounter's claim
                // is edited from its review instead).
                const manual = claim.source_system === MANUAL_SOURCE_SYSTEM;
                const expanded = expandedId === claim.id;
                return (
                  <Fragment key={claim.id}>
                    <TableRow
                      className="cursor-pointer"
                      onClick={(event) => {
                        if (!(event.target as HTMLElement).closest("button, a, [role=menuitem]")) toggle(claim.id);
                      }}
                    >
                      <TableCell className="pl-3">
                        <button
                          type="button"
                          aria-label="Détails"
                          aria-expanded={expanded}
                          onClick={() => toggle(claim.id)}
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
                        <Badge tone={claim.status === "soumis" ? "success" : "primary"}>{STATUS_LABELS[claim.status]}</Badge>
                      </TableCell>
                      <TableCell className="pr-3 text-right">
                        <RowActions
                          label={`Actions — réclamation de ${claim.patient_full_name}`}
                          actions={[
                            {
                              label: "Modifier",
                              icon: Pencil,
                              onSelect: () => navigate(`/app/facturer/${claim.id}`),
                              disabled: !(manual && deletable),
                            },
                            { label: "Supprimer", icon: Trash2, danger: true, onSelect: () => handleDelete(claim), disabled: !deletable },
                          ]}
                        />
                      </TableCell>
                    </TableRow>
                    {expanded && (
                      <TableRow className="bg-muted/30 hover:bg-muted/30">
                        <TableCell colSpan={7} className="px-6 py-3 whitespace-normal">
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
        </div>
      )}
    </>
  );
}
