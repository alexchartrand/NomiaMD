import { Banner, Button, Card, CardContent, CardHeader, CardTitle, Checkbox, Select, TextField } from "../../../components";
import { GENDERS, type Gender } from "../../../api";
import type { useCreatePatientForm } from "./useCreatePatientForm";

interface CreatePatientFormProps {
  form: ReturnType<typeof useCreatePatientForm>;
}

export function CreatePatientForm({ form }: CreatePatientFormProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Nouveau patient</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.submit} className="flex flex-col items-start gap-4">
          <div className="flex w-full max-w-sm flex-col gap-1.5">
            <label htmlFor="create-full-name" className="text-sm text-muted-foreground">
              Nom complet
            </label>
            <TextField
              id="create-full-name"
              value={form.form.full_name}
              onChange={(e) => form.update({ full_name: e.target.value })}
            />
          </div>

          <div className="flex w-full max-w-sm flex-col gap-1.5">
            <label htmlFor="create-ramq" className="text-sm text-muted-foreground">
              Numéro RAMQ (NAM)
            </label>
            <TextField
              id="create-ramq"
              value={form.form.ramq_number}
              onChange={(e) => form.update({ ramq_number: e.target.value })}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="create-dob" className="text-sm text-muted-foreground">
              Date de naissance
            </label>
            <TextField
              id="create-dob"
              type="date"
              className="w-auto"
              value={form.form.date_of_birth}
              onChange={(e) => form.update({ date_of_birth: e.target.value })}
            />
          </div>

          <div className="flex w-full max-w-sm flex-col gap-1.5">
            <label htmlFor="create-gender" className="text-sm text-muted-foreground">
              Genre
            </label>
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
          </div>

          <div className="flex w-full max-w-sm flex-col gap-1.5">
            <label htmlFor="create-family-doctor-name" className="text-sm text-muted-foreground">
              Médecin de famille
            </label>
            <TextField
              id="create-family-doctor-name"
              value={form.form.family_doctor_name}
              onChange={(e) => form.update({ family_doctor_name: e.target.value })}
            />
          </div>

          <div className="flex w-full max-w-sm flex-col gap-1.5">
            <label htmlFor="create-family-doctor-practice-number" className="text-sm text-muted-foreground">
              Numéro de pratique du médecin de famille
            </label>
            <TextField
              id="create-family-doctor-practice-number"
              value={form.form.family_doctor_practice_number}
              onChange={(e) => form.update({ family_doctor_practice_number: e.target.value })}
              placeholder="12345"
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <Checkbox
              checked={form.form.is_vulnerable}
              onCheckedChange={(checked) => form.update({ is_vulnerable: checked === true })}
            />
            Clientèle vulnérable
          </label>

          {form.error && (
            <Banner tone="error" className="w-full max-w-sm">
              {form.error}
            </Banner>
          )}

          <div className="flex gap-2">
            <Button type="submit" disabled={form.submitting}>
              {form.submitting ? "Création..." : "Créer le patient"}
            </Button>
            <Button type="button" variant="secondary" onClick={form.close} disabled={form.submitting}>
              Annuler
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
