import { useEffect, useState } from "react";
import { ScrollText } from "lucide-react";
import {
  describeError,
  listAdminUsers,
  listAuditEvents,
  type AdminUser,
  type AuditEvent,
  type AuditFilters,
} from "../../../api";
import {
  Badge,
  Banner,
  Button,
  EmptyState,
  FilterField,
  Select,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  type BadgeTone,
} from "../../../components";
import { AUDIT_ACTION_LABELS, formatDateTime } from "./format";

const PAGE = 100;

function toneOf(action: string): BadgeTone {
  if (action === "login.failed" || action === "user.deactivated") return "danger";
  if (action.startsWith("login.")) return "neutral";
  return "primary";
}

// What an event's details say, in words: the fields edited, a role change, a refusal reason.
function describeDetails(event: AuditEvent): string {
  const details = event.details ?? {};
  if (Array.isArray(details.fields)) return `Champs : ${(details.fields as string[]).join(", ")}`;
  if (typeof details.from === "string" && typeof details.to === "string") return `${details.from} → ${details.to}`;
  if (details.reason === "bad_password") return "Mot de passe invalide";
  if (details.reason === "deactivated") return "Compte désactivé";
  if (typeof details.encounter_id === "number") return `Rencontre nº ${details.encounter_id}`;
  if (typeof details.email === "string") return details.email;
  if (typeof details.role === "string") return `Rôle : ${details.role}`;
  return "";
}

// The append-only account trail: admin actions and login attempts on real accounts.
export function AuditTab() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [filters, setFilters] = useState<AuditFilters>({});
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAdminUsers()
      .then(setUsers)
      .catch(() => setUsers([]));
  }, []);

  useEffect(() => {
    let current = true;
    setEvents(null);
    setError(null);
    listAuditEvents(filters, PAGE, 0)
      .then((page) => {
        if (!current) return;
        setEvents(page);
        setHasMore(page.length === PAGE);
      })
      .catch((err) => current && setError(describeError(err)));
    return () => {
      current = false;
    };
  }, [filters.action, filters.user_id]);

  async function loadMore() {
    if (!events) return;
    try {
      const page = await listAuditEvents(filters, PAGE, events.length);
      setEvents([...events, ...page]);
      setHasMore(page.length === PAGE);
    } catch (err) {
      setError(describeError(err));
    }
  }

  return (
    <>
      <div className="mb-5 flex flex-wrap items-center gap-4 rounded-xl border border-border bg-card px-4 py-3">
        <FilterField htmlFor="audit-action" label="Action">
          <Select
            id="audit-action"
            value={filters.action ?? ""}
            onChange={(event) => setFilters({ ...filters, action: event.target.value || undefined })}
          >
            <option value="">Toutes</option>
            {Object.entries(AUDIT_ACTION_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </FilterField>
        <FilterField htmlFor="audit-user" label="Utilisateur">
          <Select
            id="audit-user"
            value={filters.user_id ?? ""}
            onChange={(event) =>
              setFilters({ ...filters, user_id: event.target.value ? Number(event.target.value) : undefined })
            }
          >
            <option value="">Tous</option>
            {users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.full_name}
              </option>
            ))}
          </Select>
        </FilterField>
      </div>

      {error && <Banner tone="error" className="mb-4">{error}</Banner>}
      {events === null && !error ? (
        <div aria-busy="true" aria-label="Chargement du journal" className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-10 rounded-lg" />
          ))}
        </div>
      ) : events && events.length === 0 ? (
        <EmptyState icon={ScrollText} title="Aucun événement." />
      ) : events ? (
        <>
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-4">Date</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Par</TableHead>
                  <TableHead>Compte visé</TableHead>
                  <TableHead>Détails</TableHead>
                  <TableHead className="pr-4">Adresse IP</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((event) => (
                  <TableRow key={event.id}>
                    <TableCell className="pl-4 tabular-nums">{formatDateTime(event.created_at)}</TableCell>
                    <TableCell>
                      <Badge tone={toneOf(event.action)}>{AUDIT_ACTION_LABELS[event.action] ?? event.action}</Badge>
                    </TableCell>
                    <TableCell>{event.actor_name ?? "—"}</TableCell>
                    <TableCell>{event.target_name ?? "—"}</TableCell>
                    <TableCell className="whitespace-normal text-sm text-muted-foreground">{describeDetails(event)}</TableCell>
                    <TableCell className="pr-4 font-mono text-xs">{event.ip ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {hasMore && (
            <div className="mt-4 flex justify-center">
              <Button type="button" variant="secondary" onClick={loadMore}>
                Afficher plus
              </Button>
            </div>
          )}
        </>
      ) : null}
    </>
  );
}
