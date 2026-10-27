import { useEffect, useState, type FormEvent } from "react";
import { Building2, Pencil, Plus, RotateCcw, Archive } from "lucide-react";
import { toast } from "sonner";
import {
  CARE_SETTING_LABELS,
  SITE_CARE_SETTINGS,
  createWorkSite,
  describeError,
  listWorkSites,
  setWorkSiteActive,
  updateWorkSite,
  type SiteCareSetting,
  type WorkSite,
} from "../../../api";
import {
  Badge,
  Banner,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  FormField,
  Modal,
  RowActions,
  Select,
  Spinner,
  TextField,
} from "../../../components";

// The places the physician works, each with its care setting — what a shift on the schedule
// is attached to, and so what billing reads as where an encounter took place.
export function WorkSitesCard() {
  const [sites, setSites] = useState<WorkSite[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // null: closed · "new": adding · a site: editing it.
  const [editing, setEditing] = useState<WorkSite | "new" | null>(null);

  useEffect(() => {
    listWorkSites(true)
      .then(setSites)
      .catch((err) => setError(describeError(err)));
  }, []);

  function saved(site: WorkSite) {
    setSites((current) => {
      const others = (current ?? []).filter((s) => s.id !== site.id);
      return [...others, site].sort((a, b) => a.name.localeCompare(b.name, "fr"));
    });
  }

  async function toggleActive(site: WorkSite) {
    try {
      saved(await setWorkSiteActive(site.id, !site.is_active));
      toast.success(site.is_active ? "Lieu archivé." : "Lieu réactivé.");
    } catch (err) {
      toast.error(describeError(err));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-heading text-lg font-semibold">Lieux de travail</CardTitle>
        <CardDescription>
          Où vous travaillez. Chaque quart de votre horaire est rattaché à un lieu, dont le milieu de soins oriente le
          choix des codes.
        </CardDescription>
        <CardAction>
          <Button variant="secondary" size="sm" onClick={() => setEditing("new")}>
            <Plus aria-hidden className="size-4" />
            Ajouter
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {error && <Banner tone="error">{error}</Banner>}
        {!error && sites === null && <Spinner />}
        {sites?.length === 0 && (
          <EmptyState
            icon={Building2}
            title="Aucun lieu de travail"
            description="Ajoutez l'urgence, l'unité, le CHSLD ou le GMF où vous travaillez."
          />
        )}
        {sites && sites.length > 0 && (
          <ul className="m-0 flex list-none flex-col divide-y divide-border p-0">
            {sites.map((site) => (
              <li key={site.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className={site.is_active ? "font-medium" : "font-medium text-muted-foreground line-through"}>
                    {site.name}
                  </span>
                  <Badge tone={site.is_active ? "primary" : "neutral"}>{CARE_SETTING_LABELS[site.care_setting]}</Badge>
                  {!site.is_active && <Badge>Archivé</Badge>}
                </div>
                <RowActions
                  label={`Actions — ${site.name}`}
                  actions={[
                    { label: "Modifier", icon: Pencil, onSelect: () => setEditing(site) },
                    site.is_active
                      ? { label: "Archiver", icon: Archive, danger: true, onSelect: () => void toggleActive(site) }
                      : { label: "Réactiver", icon: RotateCcw, onSelect: () => void toggleActive(site) },
                  ]}
                />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
      {editing && (
        <WorkSiteDialog
          site={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(site) => {
            saved(site);
            setEditing(null);
          }}
        />
      )}
    </Card>
  );
}

function WorkSiteDialog({
  site,
  onClose,
  onSaved,
}: {
  site: WorkSite | null;
  onClose: () => void;
  onSaved: (site: WorkSite) => void;
}) {
  const [name, setName] = useState(site?.name ?? "");
  const [careSetting, setCareSetting] = useState<SiteCareSetting>(site?.care_setting ?? "urgence");
  const [etablissement, setEtablissement] = useState(site?.etablissement_number ?? "");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (name.trim() === "") {
      setError("Donnez un nom au lieu.");
      return;
    }
    setError(null);
    setSubmitting(true);
    const payload = {
      name: name.trim(),
      care_setting: careSetting,
      etablissement_number: etablissement.trim() === "" ? null : etablissement.trim(),
    };
    try {
      onSaved(site ? await updateWorkSite(site.id, payload) : await createWorkSite(payload));
    } catch (err) {
      setError(describeError(err));
      setSubmitting(false);
    }
  }

  return (
    <Modal title={site ? "Modifier le lieu" : "Nouveau lieu de travail"} onClose={onClose}>
      <form id="work-site-form" onSubmit={handleSubmit} className="flex flex-col gap-4 pb-1">
        <FormField id="work-site-name" label="Nom">
          <TextField
            id="work-site-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Urgence Hôpital Saint-Luc"
            autoFocus
          />
        </FormField>
        <FormField
          id="work-site-care-setting"
          label="Milieu de soins"
          hint={site ? "Les quarts déjà à l'horaire gardent le milieu avec lequel ils ont été enregistrés." : undefined}
        >
          <Select
            id="work-site-care-setting"
            containerClassName="max-w-none"
            value={careSetting}
            onChange={(event) => setCareSetting(event.target.value as SiteCareSetting)}
          >
            {SITE_CARE_SETTINGS.map((setting) => (
              <option key={setting.value} value={setting.value}>
                {setting.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="work-site-etablissement" label="Numéro d'établissement" hint="Facultatif.">
          <TextField
            id="work-site-etablissement"
            value={etablissement}
            onChange={(event) => setEtablissement(event.target.value)}
          />
        </FormField>
        {error && <Banner tone="error">{error}</Banner>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Enregistrement..." : "Enregistrer"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
