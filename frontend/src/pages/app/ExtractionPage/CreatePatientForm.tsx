import { Banner, Button, Card, Select, TextField } from "../../../components";
import { GENDERS, type Gender } from "../../../api";
import type { useCreatePatientForm } from "./useCreatePatientForm";

interface CreatePatientFormProps {
  form: ReturnType<typeof useCreatePatientForm>;
  dateOfBirthIsEstimated: boolean;
}

export function CreatePatientForm({ form, dateOfBirthIsEstimated }: CreatePatientFormProps) {
  return (
    <Card>
      <h3>Nouveau patient</h3>
      <form onSubmit={form.submit} className="login-form">
        <label htmlFor="create-full-name">Nom complet</label>
        <TextField
          id="create-full-name"
          value={form.form.full_name}
          onChange={(e) => form.update({ full_name: e.target.value })}
        />

        <label htmlFor="create-ramq">Numéro RAMQ (NAM)</label>
        <TextField
          id="create-ramq"
          value={form.form.ramq_number}
          onChange={(e) => form.update({ ramq_number: e.target.value })}
        />

        <label htmlFor="create-dob">Date de naissance</label>
        <TextField
          id="create-dob"
          type="date"
          value={form.form.date_of_birth}
          onChange={(e) => form.update({ date_of_birth: e.target.value })}
        />
        {dateOfBirthIsEstimated && (
          <span className="status-inline">estimée d&rsquo;après l&rsquo;âge — à confirmer</span>
        )}

        <label htmlFor="create-gender">Genre</label>
        <Select
          id="create-gender"
          value={form.form.gender ?? ""}
          onChange={(e) => form.update({ gender: (e.target.value || null) as Gender | null })}
        >
          <option value="">—</option>
          {GENDERS.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </Select>

        {form.error && <Banner tone="error">{form.error}</Banner>}

        <div className="table-actions">
          <Button type="submit" disabled={form.submitting}>
            {form.submitting ? "Création..." : "Créer le patient"}
          </Button>
          <Button type="button" variant="secondary" onClick={form.close} disabled={form.submitting}>
            Annuler
          </Button>
        </div>
      </form>
    </Card>
  );
}
