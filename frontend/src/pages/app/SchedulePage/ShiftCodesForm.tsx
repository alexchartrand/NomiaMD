import { useState } from "react";
import { toast } from "sonner";
import { describeError, saveShiftClaim, type GardeOption, type ShiftBilling, type ShiftClaim } from "../../../api";
import { Badge, Banner, Button, Checkbox, FormField, Select, TextField } from "../../../components";
import { formatMoney } from "../../../utils/money";

interface ShiftCodesFormProps {
  billing: ShiftBilling;
  onSaved: (claim: ShiftClaim) => void;
  // The physician picked another garde option: the billing is read again under it.
  onGardeOptionChange: (option: GardeOption) => void;
}

// Hours as typed: the field may be blank or invalid while the physician edits it.
type Draft = Record<string, { checked: boolean; hours: string }>;

// Whole hours, 1 to 24; null otherwise.
function parseHours(raw: string): number | null {
  const hours = Number(raw);
  return raw.trim() !== "" && Number.isInteger(hours) && hours >= 1 && hours <= 24 ? hours : null;
}

// Starts from the claim when there is one under the same garde option, else from what the
// shift's rules suggest.
function initialDraft(billing: ShiftBilling): Draft {
  const source = billing.claim?.garde_option === billing.garde_option ? billing.claim.codes : billing.suggested;
  return Object.fromEntries(
    billing.available_codes.map((code) => {
      const line = source.find((l) => l.code === code.code);
      return [code.code, { checked: line != null, hours: String(line?.hours ?? code.quart_hours) }];
    }),
  );
}

// The shift's own codes — billed for the hours worked, no patient — ticked as suggested,
// hours editable, saved as the shift's draft claim. Fees are the server's: the total here
// is indicative.
export function ShiftCodesForm({ billing, onSaved, onGardeOptionChange }: ShiftCodesFormProps) {
  const [draft, setDraft] = useState<Draft>(() => initialDraft(billing));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const billed = billing.claim?.status === "soumis";
  const suggested = new Set(billing.suggested.map((line) => line.code));

  if (billing.available_codes.length === 0 && billing.garde_choices.length === 0) {
    return <p className="m-0 text-sm text-muted-foreground">Aucun code de quart pour ce type de lieu.</p>;
  }

  const lines = billing.available_codes.filter((code) => draft[code.code].checked);
  const valid = lines.every((code) => parseHours(draft[code.code].hours) !== null);
  const total = lines.reduce((sum, code) => sum + (code.hourly_fee ?? 0) * (parseHours(draft[code.code].hours) ?? 0), 0);

  function update(code: string, change: Partial<Draft[string]>) {
    setDraft((prev) => ({ ...prev, [code]: { ...prev[code], ...change } }));
  }

  async function save() {
    setError(null);
    setSaving(true);
    try {
      const claim = await saveShiftClaim(
        billing.shift.id,
        lines.map((code) => ({ code: code.code, hours: parseHours(draft[code.code].hours)! })),
        billing.garde_option,
      );
      toast.success("Réclamation du quart enregistrée.");
      onSaved(claim);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {billed && <Banner tone="success">Réclamation facturée. Pour la modifier, annulez d'abord sa facture.</Banner>}
      {billing.garde_choices.length > 0 && (
        <FormField label="Garde sur place (P.G. 1.4)" id="garde-option">
          <Select
            id="garde-option"
            containerClassName="max-w-none"
            value={billing.garde_option}
            disabled={billed}
            onChange={(event) => onGardeOptionChange(event.target.value as GardeOption)}
          >
            {billing.garde_choices.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </Select>
        </FormField>
      )}
      {billing.garde_option !== "acte" && (
        <Banner tone="warning">
          Avec le forfait, les services rendus aux patients pendant la période sont payés à 101 % de 0 h à 8 h (MOD=097)
          et à 53,2 % de 20 h à 24 h (MOD=096) : ajoutez ce modificateur à leurs réclamations.
        </Banner>
      )}
      {billing.suggested.length === 0 && !billing.claim && (
        <p className="m-0 text-sm text-muted-foreground">Ce quart ne donne droit à aucun supplément selon ses heures.</p>
      )}
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {billing.available_codes.map((code) => {
          const line = draft[code.code];
          return (
            <li key={code.code} className="flex items-start gap-3 rounded-lg border border-border p-3">
              <Checkbox
                id={`shift-code-${code.code}`}
                checked={line.checked}
                disabled={billed}
                onCheckedChange={(checked) => update(code.code, { checked: checked === true })}
                aria-label={`Code ${code.code}`}
                className="mt-0.5"
              />
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <label htmlFor={`shift-code-${code.code}`} className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{code.code}</span>
                  {suggested.has(code.code) && (
                    <Badge tone="primary" className="text-[0.7rem]">
                      Suggéré
                    </Badge>
                  )}
                </label>
                <span className="text-sm">{code.description}</span>
                <span className="text-xs text-muted-foreground">
                  Secteur {code.secteur_dispensation} — {code.secteur_dispensation_label} · {code.source}
                </span>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <TextField
                  type="number"
                  min={1}
                  max={24}
                  step={1}
                  aria-label={`Heures, code ${code.code}`}
                  value={line.hours}
                  disabled={billed || !line.checked}
                  aria-invalid={line.checked && parseHours(line.hours) === null}
                  onChange={(event) => update(code.code, { hours: event.target.value })}
                  className="w-16"
                />
                <span className="text-sm text-muted-foreground">h</span>
              </div>
            </li>
          );
        })}
      </ul>
      {error && <Banner tone="error">{error}</Banner>}
      {!billed && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-sm text-muted-foreground">
            Total indicatif <strong className="text-foreground tabular-nums">{formatMoney(total)}</strong>
          </span>
          <Button type="button" onClick={save} disabled={saving || lines.length === 0 || !valid}>
            {saving ? "Enregistrement..." : billing.claim ? "Mettre à jour la réclamation" : "Enregistrer la réclamation"}
          </Button>
        </div>
      )}
    </div>
  );
}
