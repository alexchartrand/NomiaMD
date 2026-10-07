import { useEffect, useMemo, useState } from "react";
import { NotebookPen, Pencil, Search, UserMinus, UserPlus, UserRoundPlus, Users } from "lucide-react";
import { describeError, listRoster, removeFromRoster, addToRoster, type RosterEntry } from "../../api";
import {
  AppPage,
  AppPageHeader,
  Badge,
  Banner,
  Button,
  EmptyState,
  Modal,
  RowActions,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TextField,
  useConfirm,
} from "../../components";
import { formatAge, formatDate, clinicToday } from "../../utils/date";
import { fold } from "../../utils/text";
import { useAuth } from "../../AuthContext";
import { AddExistingDialog } from "./patients/AddExistingDialog";
import { CreatePatientForm } from "./patients/CreatePatientForm";
import { EditPatientDialog } from "./patients/EditPatientDialog";
import { NotesDialog } from "./patients/NotesDialog";
import { useCreatePatientForm } from "./patients/useCreatePatientForm";

// "Create a brand-new patient" is tracked by useCreatePatientForm's own `visible` state.
type Dialog = { kind: "add-existing" } | { kind: "notes"; entry: RosterEntry } | { kind: "edit"; entry: RosterEntry } | null;

function RegistrationBadge({ value }: { value: boolean | null }) {
  if (value === true) return <Badge tone="success">Inscrit</Badge>;
  if (value === false) return <Badge>Non inscrit</Badge>;
  return <Badge tone="warning">Inconnu</Badge>;
}

export default function PatientsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const { confirm, dialog: confirmDialog } = useConfirm();

  const [roster, setRoster] = useState<RosterEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [dialog, setDialog] = useState<Dialog>(null);

  const createPatientForm = useCreatePatientForm({
    onCreated: (patient) => {
      addToRoster({ patient_id: patient.id })
        .then(loadRoster)
        .catch((err) => setListError(describeError(err)));
    },
  });

  function loadRoster() {
    setLoading(true);
    setListError(null);
    listRoster()
      .then(setRoster)
      .catch((err) => setListError(describeError(err)))
      .finally(() => setLoading(false));
  }

  useEffect(loadRoster, []);

  const shown = useMemo(() => {
    const q = fold(query.trim());
    return q ? roster.filter((entry) => fold(`${entry.full_name} ${entry.ramq_number ?? ""}`).includes(q)) : roster;
  }, [roster, query]);

  function closeAndReload() {
    setDialog(null);
    loadRoster();
  }

  async function handleRemove(entry: RosterEntry) {
    const confirmed = await confirm({
      title: "Retirer le patient ?",
      message: `Retirer ${entry.full_name} de votre liste de patients ? Son dossier et ses réclamations restent en place.`,
      confirmLabel: "Retirer",
      tone: "danger",
    });
    if (!confirmed) return;
    try {
      await removeFromRoster(entry.id);
      loadRoster();
    } catch (err) {
      setListError(describeError(err));
    }
  }

  const today = clinicToday();

  return (
    <AppPage>
      {confirmDialog}
      <AppPageHeader
        title="Patients"
        description="Votre liste de patients. Leur âge, leur inscription auprès de vous et leur vulnérabilité déterminent les codes admissibles."
        actions={
          <>
            <Button type="button" variant="secondary" onClick={() => createPatientForm.open()}>
              <UserRoundPlus aria-hidden />
              Créer un nouveau patient
            </Button>
            <Button type="button" onClick={() => setDialog({ kind: "add-existing" })}>
              <UserPlus aria-hidden />
              Ajouter un patient existant
            </Button>
          </>
        }
      />

      <div className="relative mb-4 w-72">
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <TextField
          aria-label="Rechercher un patient"
          className="pl-8"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Nom ou NAM…"
        />
      </div>

      {listError && <Banner tone="error" className="mb-4">{listError}</Banner>}

      {loading ? (
        <div aria-busy="true" aria-label="Chargement des patients" className="flex flex-col gap-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-12 rounded-lg" />
          ))}
        </div>
      ) : roster.length === 0 ? (
        <EmptyState
          icon={Users}
          title="Aucun patient dans votre liste."
          description="Ajoutez un patient déjà connu de la clinique, ou créez-en un nouveau."
        />
      ) : shown.length === 0 ? (
        <EmptyState icon={Search} title="Aucun patient ne correspond à cette recherche." />
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-4">Nom</TableHead>
                <TableHead>NAM</TableHead>
                <TableHead>Date de naissance</TableHead>
                <TableHead>Genre</TableHead>
                <TableHead>Inscription</TableHead>
                <TableHead>Vulnérable</TableHead>
                <TableHead className="w-12" aria-label="Actions" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="max-w-64 pl-4">
                    <span className="block font-semibold">{entry.full_name}</span>
                    {entry.notes && (
                      <span className="block truncate text-xs text-muted-foreground" title={entry.notes}>
                        {entry.notes}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-[0.85rem]">{entry.ramq_number ?? "—"}</TableCell>
                  <TableCell>
                    <span className="tabular-nums">{formatDate(entry.date_of_birth)}</span>
                    <span className="ml-2 text-xs text-muted-foreground">{formatAge(entry.date_of_birth, today)}</span>
                  </TableCell>
                  <TableCell>{entry.gender ?? "—"}</TableCell>
                  <TableCell>
                    <RegistrationBadge value={entry.is_registered_with_current_physician} />
                  </TableCell>
                  <TableCell>{entry.is_vulnerable ? <Badge tone="primary">Oui</Badge> : <span className="text-muted-foreground">Non</span>}</TableCell>
                  <TableCell className="pr-3 text-right">
                    <RowActions
                      label={`Actions — ${entry.full_name}`}
                      actions={[
                        { label: "Notes", icon: NotebookPen, onSelect: () => setDialog({ kind: "notes", entry }) },
                        { label: "Modifier", icon: Pencil, onSelect: () => setDialog({ kind: "edit", entry }), disabled: !isAdmin },
                        { label: "Retirer", icon: UserMinus, danger: true, onSelect: () => handleRemove(entry) },
                      ]}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {dialog?.kind === "add-existing" && <AddExistingDialog onClose={() => setDialog(null)} onAdded={closeAndReload} />}
      {dialog?.kind === "notes" && <NotesDialog entry={dialog.entry} onClose={() => setDialog(null)} onSaved={closeAndReload} />}
      {dialog?.kind === "edit" && (
        <EditPatientDialog entry={dialog.entry} onClose={() => setDialog(null)} onSaved={closeAndReload} />
      )}
      {createPatientForm.visible && (
        <Modal title="Nouveau patient" onClose={createPatientForm.close}>
          <div className="pb-1">
            <CreatePatientForm form={createPatientForm} framed={false} />
          </div>
        </Modal>
      )}
    </AppPage>
  );
}
