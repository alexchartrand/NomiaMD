import { useEffect, useState, type FormEvent } from "react";
import {
  GENDERS,
  createPatient,
  deletePatient,
  describeError,
  listPatients,
  updatePatient,
  type Gender,
  type Patient,
  type PatientInput,
} from "../../api";
import {
  Banner,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Checkbox,
  Select,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components";
import { formatDate } from "../../utils/date";

const BLANK_FORM: PatientInput = {
  full_name: "",
  ramq_number: "",
  date_of_birth: "",
  gender: null,
  is_registered_with_physician: false,
  is_vulnerable: false,
};

export default function PatientsPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [editing, setEditing] = useState<Patient | "new" | null>(null);
  const [form, setForm] = useState<PatientInput>(BLANK_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function loadPatients() {
    setLoading(true);
    setListError(null);
    listPatients()
      .then(setPatients)
      .catch((err) => setListError(describeError(err)))
      .finally(() => setLoading(false));
  }

  useEffect(loadPatients, []);

  function startCreate() {
    setForm(BLANK_FORM);
    setFormError(null);
    setEditing("new");
  }

  function startEdit(patient: Patient) {
    setForm({
      full_name: patient.full_name,
      ramq_number: patient.ramq_number,
      date_of_birth: patient.date_of_birth,
      gender: patient.gender,
      is_registered_with_physician: patient.is_registered_with_physician,
      is_vulnerable: patient.is_vulnerable,
    });
    setFormError(null);
    setEditing(patient);
  }

  function cancelForm() {
    setEditing(null);
    setFormError(null);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);

    if (!form.full_name.trim()) {
      setFormError("Le nom est obligatoire.");
      return;
    }
    if (!form.date_of_birth) {
      setFormError("La date de naissance est obligatoire.");
      return;
    }

    const payload: PatientInput = {
      ...form,
      ramq_number: form.ramq_number?.trim() || null,
    };

    setSubmitting(true);
    try {
      if (editing === "new") {
        await createPatient(payload);
      } else if (editing) {
        await updatePatient(editing.id, payload);
      }
      setEditing(null);
      loadPatients();
    } catch (err) {
      setFormError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(patient: Patient) {
    if (!window.confirm(`Supprimer ${patient.full_name} ? Cette action est irréversible.`)) return;
    try {
      await deletePatient(patient.id);
      loadPatients();
    } catch (err) {
      setListError(describeError(err));
    }
  }

  return (
    <section className="max-w-[860px] space-y-6">
      <h1 className="font-heading text-2xl font-semibold">Patients</h1>

      {editing === null && (
        <Button type="button" onClick={startCreate}>
          Ajouter un patient
        </Button>
      )}

      {editing !== null && (
        <Card>
          <CardHeader>
            <CardTitle>{editing === "new" ? "Nouveau patient" : "Modifier le patient"}</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="flex flex-col items-start gap-4">
              <div className="flex w-full max-w-sm flex-col gap-1.5">
                <label htmlFor="patient-full-name" className="text-sm text-muted-foreground">
                  Nom complet
                </label>
                <TextField
                  id="patient-full-name"
                  value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                />
              </div>

              <div className="flex w-full max-w-sm flex-col gap-1.5">
                <label htmlFor="patient-ramq-number" className="text-sm text-muted-foreground">
                  Numéro RAMQ (NAM)
                </label>
                <TextField
                  id="patient-ramq-number"
                  value={form.ramq_number ?? ""}
                  onChange={(e) => setForm({ ...form, ramq_number: e.target.value })}
                  placeholder="ABCD 1234 5678"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="patient-dob" className="text-sm text-muted-foreground">
                  Date de naissance
                </label>
                <TextField
                  id="patient-dob"
                  type="date"
                  className="w-auto"
                  value={form.date_of_birth}
                  onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="patient-gender" className="text-sm text-muted-foreground">
                  Genre
                </label>
                <Select
                  id="patient-gender"
                  value={form.gender ?? ""}
                  onChange={(e) => setForm({ ...form, gender: (e.target.value || null) as Gender | null })}
                >
                  <option value="">—</option>
                  {GENDERS.map((g) => (
                    <option key={g} value={g}>
                      {g}
                    </option>
                  ))}
                </Select>
              </div>

              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <Checkbox
                  checked={form.is_registered_with_physician}
                  onCheckedChange={(checked) =>
                    setForm({ ...form, is_registered_with_physician: checked === true })
                  }
                />
                Inscrit auprès de moi comme médecin de famille
              </label>

              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <Checkbox
                  checked={form.is_vulnerable}
                  onCheckedChange={(checked) => setForm({ ...form, is_vulnerable: checked === true })}
                />
                Clientèle vulnérable
              </label>

              {formError && (
                <Banner tone="error" className="w-full max-w-sm">
                  {formError}
                </Banner>
              )}

              <div className="flex gap-2">
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Enregistrement..." : "Enregistrer"}
                </Button>
                <Button type="button" variant="secondary" onClick={cancelForm} disabled={submitting}>
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
      ) : patients.length === 0 ? (
        <p>Aucun patient enregistré.</p>
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
            {patients.map((patient) => (
              <TableRow key={patient.id}>
                <TableCell>{patient.full_name}</TableCell>
                <TableCell>{patient.ramq_number ?? "—"}</TableCell>
                <TableCell>{formatDate(patient.date_of_birth)}</TableCell>
                <TableCell>{patient.gender ?? "—"}</TableCell>
                <TableCell>{patient.is_registered_with_physician ? "Oui" : "Non"}</TableCell>
                <TableCell>{patient.is_vulnerable ? "Oui" : "Non"}</TableCell>
                <TableCell>
                  <div className="flex gap-2">
                    <Button type="button" variant="secondary" onClick={() => startEdit(patient)}>
                      Modifier
                    </Button>
                    <Button type="button" variant="danger" onClick={() => handleDelete(patient)}>
                      Supprimer
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
