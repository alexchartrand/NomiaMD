import { useEffect, useState, type FormEvent } from "react";
import {
  GENDERS,
  addToRoster,
  describeError,
  listRoster,
  removeFromRoster,
  updatePatient,
  updateRosterEntry,
  type Gender,
  type Patient,
  type PatientInput,
  type RosterEntry,
} from "../../api";
import {
  Banner,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Checkbox,
  PatientSearchSelect,
  Select,
  TextArea,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components";
import { formatDate } from "../../utils/date";
import { useAuth } from "../../AuthContext";
import { CreatePatientForm } from "./patients/CreatePatientForm";
import { useCreatePatientForm } from "./patients/useCreatePatientForm";

// "Create a brand-new patient" is tracked by useCreatePatientForm's own `visible` state
// instead of a Panel variant here — its cancel path (form.close()) has no way to also
// reset a Panel value, so keeping it independent avoids a stuck-open top-buttons row.
type Panel =
  | { kind: "add-existing" }
  | { kind: "edit-notes"; entry: RosterEntry }
  | { kind: "edit-global"; entry: RosterEntry }
  | null;

const BLANK_GLOBAL_FORM: PatientInput = {
  full_name: "",
  ramq_number: "",
  date_of_birth: "",
  gender: null,
  is_vulnerable: false,
  family_doctor_name: "",
  family_doctor_practice_number: "",
};

function registrationLabel(value: boolean | null): string {
  if (value === true) return "Oui";
  if (value === false) return "Non";
  return "Inconnu";
}

export default function PatientsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [roster, setRoster] = useState<RosterEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [panel, setPanel] = useState<Panel>(null);
  const [panelError, setPanelError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [existingPatient, setExistingPatient] = useState<Patient | null>(null);
  const [notesDraft, setNotesDraft] = useState("");
  const [globalForm, setGlobalForm] = useState<PatientInput>(BLANK_GLOBAL_FORM);

  const createPatientForm = useCreatePatientForm({
    onCreated: (patient) => {
      addToRoster({ patient_id: patient.id })
        .then(() => {
          setPanel(null);
          loadRoster();
        })
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

  function closePanel() {
    setPanel(null);
    setPanelError(null);
    setExistingPatient(null);
    setNotesDraft("");
  }

  function startAddExisting() {
    setExistingPatient(null);
    setNotesDraft("");
    setPanelError(null);
    setPanel({ kind: "add-existing" });
  }

  function startAddNew() {
    createPatientForm.open();
  }

  function startEditNotes(entry: RosterEntry) {
    setNotesDraft(entry.notes ?? "");
    setPanelError(null);
    setPanel({ kind: "edit-notes", entry });
  }

  function startEditGlobal(entry: RosterEntry) {
    setGlobalForm({
      full_name: entry.full_name,
      ramq_number: entry.ramq_number,
      date_of_birth: entry.date_of_birth,
      gender: entry.gender,
      is_vulnerable: entry.is_vulnerable,
      family_doctor_name: entry.family_doctor_name,
      family_doctor_practice_number: entry.family_doctor_practice_number,
    });
    setPanelError(null);
    setPanel({ kind: "edit-global", entry });
  }

  async function handleAddExistingSubmit(event: FormEvent) {
    event.preventDefault();
    if (!existingPatient) {
      setPanelError("Sélectionnez un patient.");
      return;
    }
    setSubmitting(true);
    setPanelError(null);
    try {
      await addToRoster({ patient_id: existingPatient.id, notes: notesDraft.trim() || null });
      closePanel();
      loadRoster();
    } catch (err) {
      setPanelError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEditNotesSubmit(event: FormEvent) {
    event.preventDefault();
    if (panel?.kind !== "edit-notes") return;
    setSubmitting(true);
    setPanelError(null);
    try {
      await updateRosterEntry(panel.entry.id, notesDraft.trim() || null);
      closePanel();
      loadRoster();
    } catch (err) {
      setPanelError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEditGlobalSubmit(event: FormEvent) {
    event.preventDefault();
    if (panel?.kind !== "edit-global") return;
    if (!globalForm.full_name.trim() || !globalForm.date_of_birth) {
      setPanelError("Le nom et la date de naissance sont obligatoires.");
      return;
    }
    setSubmitting(true);
    setPanelError(null);
    try {
      await updatePatient(panel.entry.id, {
        ...globalForm,
        ramq_number: globalForm.ramq_number?.trim() || null,
        family_doctor_name: globalForm.family_doctor_name?.trim() || null,
        family_doctor_practice_number: globalForm.family_doctor_practice_number?.trim() || null,
      });
      closePanel();
      loadRoster();
    } catch (err) {
      setPanelError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRemove(entry: RosterEntry) {
    if (!window.confirm(`Retirer ${entry.full_name} de votre liste de patients ?`)) return;
    try {
      await removeFromRoster(entry.id);
      loadRoster();
    } catch (err) {
      setListError(describeError(err));
    }
  }

  return (
    <section className="max-w-[860px] space-y-6">
      <h1 className="font-heading text-2xl font-semibold">Patients</h1>

      {panel === null && !createPatientForm.visible && (
        <div className="flex gap-2">
          <Button type="button" onClick={startAddExisting}>
            Ajouter un patient existant
          </Button>
          <Button type="button" variant="secondary" onClick={startAddNew}>
            Créer un nouveau patient
          </Button>
        </div>
      )}

      {createPatientForm.visible && <CreatePatientForm form={createPatientForm} />}

      {panel?.kind === "add-existing" && (
        <Card>
          <CardHeader>
            <CardTitle>Ajouter un patient existant</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleAddExistingSubmit} className="flex flex-col items-start gap-4">
              <div className="flex w-full max-w-sm flex-col gap-1.5">
                <label htmlFor="roster-patient-search" className="text-sm text-muted-foreground">
                  Patient
                </label>
                <PatientSearchSelect
                  id="roster-patient-search"
                  selected={existingPatient}
                  onSelect={setExistingPatient}
                />
              </div>
              <div className="flex w-full max-w-sm flex-col gap-1.5">
                <label htmlFor="roster-notes" className="text-sm text-muted-foreground">
                  Notes personnelles
                </label>
                <TextArea id="roster-notes" value={notesDraft} onChange={(e) => setNotesDraft(e.target.value)} />
              </div>
              {panelError && (
                <Banner tone="error" className="w-full max-w-sm">
                  {panelError}
                </Banner>
              )}
              <div className="flex gap-2">
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Ajout..." : "Ajouter"}
                </Button>
                <Button type="button" variant="secondary" onClick={closePanel} disabled={submitting}>
                  Annuler
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {panel?.kind === "edit-notes" && (
        <Card>
          <CardHeader>
            <CardTitle>Notes — {panel.entry.full_name}</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleEditNotesSubmit} className="flex flex-col items-start gap-4">
              <TextArea
                className="w-full max-w-sm"
                value={notesDraft}
                onChange={(e) => setNotesDraft(e.target.value)}
              />
              {panelError && (
                <Banner tone="error" className="w-full max-w-sm">
                  {panelError}
                </Banner>
              )}
              <div className="flex gap-2">
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Enregistrement..." : "Enregistrer"}
                </Button>
                <Button type="button" variant="secondary" onClick={closePanel} disabled={submitting}>
                  Annuler
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {panel?.kind === "edit-global" && (
        <Card>
          <CardHeader>
            <CardTitle>Modifier le patient — {panel.entry.full_name}</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleEditGlobalSubmit} className="flex flex-col items-start gap-4">
              <div className="flex w-full max-w-sm flex-col gap-1.5">
                <label htmlFor="edit-full-name" className="text-sm text-muted-foreground">
                  Nom complet
                </label>
                <TextField
                  id="edit-full-name"
                  value={globalForm.full_name}
                  onChange={(e) => setGlobalForm({ ...globalForm, full_name: e.target.value })}
                />
              </div>

              <div className="flex w-full max-w-sm flex-col gap-1.5">
                <label htmlFor="edit-ramq-number" className="text-sm text-muted-foreground">
                  Numéro RAMQ (NAM)
                </label>
                <TextField
                  id="edit-ramq-number"
                  value={globalForm.ramq_number ?? ""}
                  onChange={(e) => setGlobalForm({ ...globalForm, ramq_number: e.target.value })}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="edit-dob" className="text-sm text-muted-foreground">
                  Date de naissance
                </label>
                <TextField
                  id="edit-dob"
                  type="date"
                  className="w-auto"
                  value={globalForm.date_of_birth}
                  onChange={(e) => setGlobalForm({ ...globalForm, date_of_birth: e.target.value })}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="edit-gender" className="text-sm text-muted-foreground">
                  Genre
                </label>
                <Select
                  id="edit-gender"
                  value={globalForm.gender ?? ""}
                  onChange={(e) => setGlobalForm({ ...globalForm, gender: (e.target.value || null) as Gender | null })}
                >
                  <option value="">—</option>
                  {GENDERS.map((g) => (
                    <option key={g} value={g}>
                      {g}
                    </option>
                  ))}
                </Select>
              </div>

              <div className="flex w-full max-w-sm flex-col gap-1.5">
                <label htmlFor="edit-family-doctor-name" className="text-sm text-muted-foreground">
                  Médecin de famille
                </label>
                <TextField
                  id="edit-family-doctor-name"
                  value={globalForm.family_doctor_name ?? ""}
                  onChange={(e) => setGlobalForm({ ...globalForm, family_doctor_name: e.target.value })}
                />
              </div>

              <div className="flex w-full max-w-sm flex-col gap-1.5">
                <label htmlFor="edit-family-doctor-practice-number" className="text-sm text-muted-foreground">
                  Numéro de pratique du médecin de famille
                </label>
                <TextField
                  id="edit-family-doctor-practice-number"
                  value={globalForm.family_doctor_practice_number ?? ""}
                  onChange={(e) =>
                    setGlobalForm({ ...globalForm, family_doctor_practice_number: e.target.value })
                  }
                  placeholder="12345"
                />
              </div>

              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <Checkbox
                  checked={globalForm.is_vulnerable}
                  onCheckedChange={(checked) => setGlobalForm({ ...globalForm, is_vulnerable: checked === true })}
                />
                Clientèle vulnérable
              </label>

              {panelError && (
                <Banner tone="error" className="w-full max-w-sm">
                  {panelError}
                </Banner>
              )}

              <div className="flex gap-2">
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Enregistrement..." : "Enregistrer"}
                </Button>
                <Button type="button" variant="secondary" onClick={closePanel} disabled={submitting}>
                  Annuler
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {listError && <Banner tone="error">{listError}</Banner>}

      {loading ? (
        <p className="text-sm text-muted-foreground">Chargement...</p>
      ) : roster.length === 0 ? (
        <p>Aucun patient dans votre liste.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nom</TableHead>
              <TableHead>NAM</TableHead>
              <TableHead>Date de naissance</TableHead>
              <TableHead>Genre</TableHead>
              <TableHead>Inscrit</TableHead>
              <TableHead>Vulnérable</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {roster.map((entry) => (
              <TableRow key={entry.id}>
                <TableCell>{entry.full_name}</TableCell>
                <TableCell>{entry.ramq_number ?? "—"}</TableCell>
                <TableCell>{formatDate(entry.date_of_birth)}</TableCell>
                <TableCell>{entry.gender ?? "—"}</TableCell>
                <TableCell>{registrationLabel(entry.is_registered_with_current_physician)}</TableCell>
                <TableCell>{entry.is_vulnerable ? "Oui" : "Non"}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" variant="secondary" onClick={() => startEditNotes(entry)}>
                      Notes
                    </Button>
                    {isAdmin && (
                      <Button type="button" variant="secondary" onClick={() => startEditGlobal(entry)}>
                        Modifier
                      </Button>
                    )}
                    <Button type="button" variant="danger" onClick={() => handleRemove(entry)}>
                      Retirer
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  );
}
