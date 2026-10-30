import { useEffect, useState, type ReactNode } from "react";
import { CircleCheck, CircleX, LockOpen, RotateCw } from "lucide-react";
import { toast } from "sonner";
import {
  describeError,
  getSystemReport,
  listFailedExtractions,
  listLockouts,
  retryExtraction,
  unlockLogin,
  type DependencyCheck,
  type FailedExtraction,
  type Lockout,
  type SystemReport,
} from "../../../api";
import {
  Badge,
  Banner,
  Button,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../../components";
import { formatDate } from "../../../utils/date";
import { formatCount, formatDateTime, PURPOSE_LABELS } from "./format";

const TABLE_LABELS: Record<string, string> = {
  users: "Utilisateurs",
  patients: "Patients",
  encounters: "Rencontres",
  extraction_runs: "Extractions",
  claims: "Réclamations",
  bills: "Factures",
  contact_requests: "Demandes de contact",
  llm_calls: "Appels IA (détail récent)",
  llm_usage_daily: "Usage IA (totaux par jour)",
  audit_events: "Événements du journal",
};

function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-border bg-card px-5 py-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="m-0 text-base font-semibold">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function Check({ label, check }: { label: string; check: DependencyCheck }) {
  const Icon = check.ok ? CircleCheck : CircleX;
  return (
    <div className="flex items-center gap-2">
      <Icon aria-hidden className={check.ok ? "size-4 text-[color:var(--color-success-text)]" : "size-4 text-[color:var(--color-danger)]"} />
      <span className="font-medium">{label}</span>
      <span className="text-sm text-muted-foreground">{check.detail}</span>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="m-0 text-right font-medium">{value}</dd>
    </div>
  );
}

// What the backend runs on and whether it's healthy, the extractions that failed, and the
// logins locked by repeated failures. Metadata only: no note is ever shown here.
export function SystemTab() {
  const [report, setReport] = useState<SystemReport | null>(null);
  const [failures, setFailures] = useState<FailedExtraction[]>([]);
  const [lockouts, setLockouts] = useState<Lockout[]>([]);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setError(null);
    Promise.all([getSystemReport(), listFailedExtractions(), listLockouts()])
      .then(([nextReport, nextFailures, nextLockouts]) => {
        setReport(nextReport);
        setFailures(nextFailures);
        setLockouts(nextLockouts);
      })
      .catch((err) => setError(describeError(err)));
  }

  useEffect(load, []);

  async function handleRetry(failure: FailedExtraction) {
    try {
      await retryExtraction(failure.encounter_id);
      toast.success(`Extraction de la rencontre nº ${failure.encounter_id} relancée.`);
      setFailures(await listFailedExtractions());
    } catch (err) {
      toast.error(describeError(err));
    }
  }

  async function handleUnlock(lockout: Lockout) {
    try {
      await unlockLogin(lockout.email);
      toast.success(`${lockout.email} déverrouillé.`);
      setLockouts((current) => current.filter((row) => row.email !== lockout.email));
    } catch (err) {
      toast.error(describeError(err));
    }
  }

  if (error) return <Banner tone="error">{error}</Banner>;
  if (!report) {
    return (
      <div aria-busy="true" aria-label="Chargement de l'état du système" className="grid gap-4 md:grid-cols-2">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-40 rounded-xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-5 md:grid-cols-2">
        <Section
          title="État"
          action={
            <Button type="button" variant="ghost" onClick={load}>
              <RotateCw aria-hidden />
              Actualiser
            </Button>
          }
        >
          <div className="flex flex-col gap-2">
            <Check label="Base de données" check={report.database} />
            <Check label="Table des codes RAMQ" check={report.codes_table} />
          </div>
          <dl className="m-0 mt-3 border-t border-border pt-2">
            <Fact label="Environnement" value={report.app_env} />
            <Fact label="Version" value={report.app_version ?? "—"} />
            <Fact label="Vérifié le" value={formatDateTime(report.checked_at)} />
          </dl>
        </Section>

        <Section title="Modèles">
          <dl className="m-0">
            <Fact label="Fournisseur (clavardage)" value={report.models.chat_provider} />
            <Fact
              label="Plongements"
              value={`${report.models.embedding_provider}${report.models.embedding_model ? ` · ${report.models.embedding_model}` : ""}`}
            />
            {Object.entries(report.models.step_models).map(([step, model]) => (
              <Fact key={step} label={PURPOSE_LABELS[step] ?? step} value={<code className="text-xs">{model}</code>} />
            ))}
          </dl>
        </Section>

        <Section title="Données">
          <dl className="m-0">
            {Object.entries(report.row_counts).map(([table, count]) => (
              <Fact key={table} label={TABLE_LABELS[table] ?? table} value={formatCount(count)} />
            ))}
          </dl>
          <dl className="m-0">
            <Fact label="Notes retirées (conservation)" value={formatCount(report.notes_scrubbed)} />
          </dl>
          {report.notes_due_for_scrub > 0 && (
            <Banner tone="warning" className="mt-3">
              {report.notes_due_for_scrub} note(s) ont dépassé leur durée de conservation sans être retirées.
            </Banner>
          )}
        </Section>

        <Section title="Connexions bloquées">
          {lockouts.length === 0 ? (
            <p className="m-0 text-sm text-muted-foreground">Aucune tentative échouée récente.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
              {lockouts.map((lockout) => (
                <li key={lockout.email} className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="m-0 truncate text-sm font-medium">{lockout.email}</p>
                    <p className="m-0 text-xs text-muted-foreground">
                      {lockout.failed_attempts} tentative(s) · dernière {formatDateTime(lockout.last_attempt_at)}
                      {!lockout.known_account && " · aucun compte"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {lockout.is_locked && <Badge tone="danger">Bloqué</Badge>}
                    <Button type="button" variant="secondary" onClick={() => handleUnlock(lockout)}>
                      <LockOpen aria-hidden />
                      Déverrouiller
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <Section title={`Extractions en échec (${failures.length})`}>
        {failures.length === 0 ? (
          <p className="m-0 text-sm text-muted-foreground">Aucune extraction en échec.</p>
        ) : (
          <div className="-mx-5 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-5">Rencontre</TableHead>
                  <TableHead>Médecin</TableHead>
                  <TableHead>Reçue le</TableHead>
                  <TableHead>Date de service</TableHead>
                  <TableHead>Erreur</TableHead>
                  <TableHead className="w-0 pr-5" aria-label="Actions" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {failures.map((failure) => (
                  <TableRow key={failure.encounter_id}>
                    <TableCell className="pl-5 tabular-nums">nº {failure.encounter_id}</TableCell>
                    <TableCell>{failure.physician_name ?? "—"}</TableCell>
                    <TableCell className="tabular-nums">{formatDateTime(failure.received_at)}</TableCell>
                    <TableCell className="tabular-nums">{failure.service_date ? formatDate(failure.service_date) : "—"}</TableCell>
                    <TableCell className="max-w-md whitespace-normal font-mono text-xs">{failure.error}</TableCell>
                    <TableCell className="pr-5">
                      <Button type="button" variant="secondary" onClick={() => handleRetry(failure)}>
                        <RotateCw aria-hidden />
                        Relancer
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>
    </div>
  );
}
