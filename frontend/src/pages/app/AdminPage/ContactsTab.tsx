import { useEffect, useState } from "react";
import { Mail } from "lucide-react";
import { describeError, listContactRequests, type ContactRequest } from "../../../api";
import { Badge, Banner, Button, EmptyState, Skeleton } from "../../../components";
import { formatDateTime } from "./format";

const PAGE = 50;

// Kept in sync by hand with ContactTopic / ContactRole in backend/app/postgresdb/models.py.
const TOPIC_LABELS: Record<string, string> = {
  demo: "Démo",
  essai: "Essai",
  tarifs: "Tarifs",
  partenariat: "Partenariat",
  autre: "Autre",
};
const ROLE_LABELS: Record<string, string> = {
  medecin: "Médecin",
  gestionnaire: "Gestionnaire de clinique",
  partenaire: "Partenaire",
  autre: "Autre",
};

// What the public site's contact form received, newest first.
export function ContactsTab() {
  const [requests, setRequests] = useState<ContactRequest[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(offset: number) {
    try {
      const page = await listContactRequests(PAGE, offset);
      setRequests((current) => (offset === 0 ? page : [...(current ?? []), ...page]));
      setHasMore(page.length === PAGE);
    } catch (err) {
      setError(describeError(err));
    }
  }

  useEffect(() => {
    void load(0);
  }, []);

  if (error) return <Banner tone="error">{error}</Banner>;
  if (requests === null) {
    return (
      <div aria-busy="true" aria-label="Chargement des demandes" className="flex flex-col gap-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
    );
  }
  if (requests.length === 0) return <EmptyState icon={Mail} title="Aucune demande de contact." />;

  return (
    <>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {requests.map((request) => (
          <li key={request.id} className="rounded-xl border border-border bg-card px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <p className="m-0 font-semibold">{request.name}</p>
                <Badge tone="primary">{TOPIC_LABELS[request.topic] ?? request.topic}</Badge>
                {request.plan && <Badge>{request.plan}</Badge>}
              </div>
              <span className="text-xs text-muted-foreground tabular-nums">{formatDateTime(request.created_at)}</span>
            </div>
            <p className="m-0 mt-1 text-sm text-muted-foreground">
              <a href={`mailto:${request.email}`}>{request.email}</a>
              {request.phone && ` · ${request.phone}`}
              {` · ${ROLE_LABELS[request.role] ?? request.role}`}
              {request.organization && ` · ${request.organization}`}
              {request.physician_count != null && ` · ${request.physician_count} médecin(s)`}
            </p>
            {request.message && <p className="m-0 mt-2 whitespace-pre-line text-sm">{request.message}</p>}
          </li>
        ))}
      </ul>
      {hasMore && (
        <div className="mt-4 flex justify-center">
          <Button type="button" variant="secondary" onClick={() => load(requests.length)}>
            Afficher plus
          </Button>
        </div>
      )}
    </>
  );
}
