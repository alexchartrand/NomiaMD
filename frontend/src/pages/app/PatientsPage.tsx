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
import { Banner, Button, Card, Checkbox, Select, TextField, Table } from "../../components";
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
    <section className="page-panel">
      <h1>Patients</h1>

      {editing === null && (
        <Button type="button" onClick={startCreate}>
          Ajouter un patient
        </Button>
      )}

      {editing !== null && (
        <Card>
          <h2>{editing === "new" ? "Nouveau patient" : "Modifier le patient"}</h2>
          <form onSubmit={handleSubmit} className="login-form">
            <label htmlFor="patient-full-name">Nom complet</label>
            <TextField
              id="patient-full-name"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />

            <label htmlFor="patient-ramq-number">Numéro RAMQ (NAM)</label>
            <TextField
              id="patient-ramq-number"
              value={form.ramq_number ?? ""}
              onChange={(e) => setForm({ ...form, ramq_number: e.target.value })}
              placeholder="ABCD 1234 5678"
            />

            <label htmlFor="patient-dob">Date de naissance</label>
            <TextField
              id="patient-dob"
              type="date"
              value={form.date_of_birth}
              onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })}
            />

            <label htmlFor="patient-gender">Genre</label>
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

            <label>
              <Checkbox
                checked={form.is_registered_with_physician}
                onChange={(e) => setForm({ ...form, is_registered_with_physician: e.target.checked })}
              />{" "}
              Inscrit auprès de moi comme médecin de famille
            </label>

            <label>
              <Checkbox
                checked={form.is_vulnerable}
                onChange={(e) => setForm({ ...form, is_vulnerable: e.target.checked })}
              />{" "}
              Clientèle vulnérable
            </label>

            {formError && <Banner tone="error">{formError}</Banner>}

            <div className="table-actions">
              <Button type="submit" disabled={submitting}>
                {submitting ? "Enregistrement..." : "Enregistrer"}
              </Button>
              <Button type="button" variant="secondary" onClick={cancelForm} disabled={submitting}>
                Annuler
              </Button>
            </div>
          </form>
        </Card>
      )}

      {listError && <Banner tone="error">{listError}</Banner>}

      {loading ? (
        <p className="status-inline">Chargement...</p>
      ) : patients.length === 0 ? (
        <p>Aucun patient enregistré.</p>
      ) : (
        <Table>
          <thead>
            <tr>
              <th>Nom</th>
              <th>NAM</th>
              <th>Date de naissance</th>
              <th>Genre</th>
              <th>Inscrit</th>
              <th>Vulnérable</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {patients.map((patient) => (
              <tr key={patient.id}>
                <td>{patient.full_name}</td>
                <td>{patient.ramq_number ?? "—"}</td>
                <td>{formatDate(patient.date_of_birth)}</td>
                <td>{patient.gender ?? "—"}</td>
                <td>{patient.is_registered_with_physician ? "Oui" : "Non"}</td>
                <td>{patient.is_vulnerable ? "Oui" : "Non"}</td>
                <td>
                  <div className="table-actions">
                    <Button type="button" variant="secondary" onClick={() => startEdit(patient)}>
                      Modifier
                    </Button>
                    <Button type="button" variant="danger" onClick={() => handleDelete(patient)}>
                      Supprimer
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </section>
  );
}
