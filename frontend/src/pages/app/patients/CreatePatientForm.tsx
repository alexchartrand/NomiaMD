import { Banner, Button, Card, CardContent, CardHeader, CardTitle, Checkbox, FormField, Select, TextField } from "../../../components";
import { GENDERS, type Gender } from "../../../api";
import type { useCreatePatientForm } from "./useCreatePatientForm";

interface CreatePatientFormProps {
  form: ReturnType<typeof useCreatePatientForm>;
  // In its own card (inline, under an inbox row) or bare (inside a dialog that titles it).
  framed?: boolean;
}

export function CreatePatientForm({ form, framed = true }: CreatePatientFormProps) {
  const fields = (
    <form onSubmit={form.submit} className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="create-full-name" label="Nom complet">
          <TextField
            id="create-full-name"
            value={form.form.full_name}
            onChange={(e) => form.update({ full_name: e.target.value })}
          />
        </FormField>
        <FormField id="create-ramq" label="Numéro RAMQ (NAM)">
          <TextField
            id="create-ramq"
            className="font-mono"
            value={form.form.ramq_number}
            onChange={(e) => form.update({ ramq_number: e.target.value })}
          />
        </FormField>
        <FormField id="create-dob" label="Date de naissance">
          <TextField
            id="create-dob"
            type="date"
            value={form.form.date_of_birth}
            onChange={(e) => form.update({ date_of_birth: e.target.value })}
          />
        </FormField>
        <FormField id="create-gender" label="Genre">
          <Select
            id="create-gender"
            containerClassName="max-w-none"
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
        </FormField>
        <FormField id="create-family-doctor-name" label="Médecin de famille">
          <TextField
            id="create-family-doctor-name"
            value={form.form.family_doctor_name}
            onChange={(e) => form.update({ family_doctor_name: e.target.value })}
          />
        </FormField>
        <FormField
          id="create-family-doctor-practice-number"
          label="Numéro de pratique du médecin de famille"
          hint="Le patient est inscrit auprès de vous si ce numéro est le vôtre."
        >
          <TextField
            id="create-family-doctor-practice-number"
            value={form.form.family_doctor_practice_number}
            onChange={(e) => form.update({ family_doctor_practice_number: e.target.value })}
            placeholder="12345"
          />
        </FormField>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={form.form.is_vulnerable}
          onCheckedChange={(checked) => form.update({ is_vulnerable: checked === true })}
        />
        Clientèle vulnérable
      </label>

      {form.error && <Banner tone="error">{form.error}</Banner>}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={form.close} disabled={form.submitting}>
          Annuler
        </Button>
        <Button type="submit" disabled={form.submitting}>
          {form.submitting ? "Création..." : "Créer le patient"}
        </Button>
      </div>
    </form>
  );
  if (!framed) return fields;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Nouveau patient</CardTitle>
      </CardHeader>
      <CardContent>{fields}</CardContent>
    </Card>
  );
}
