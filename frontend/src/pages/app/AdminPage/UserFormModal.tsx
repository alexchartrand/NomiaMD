import { useState, type FormEvent } from "react";
import {
  describeError,
  PHYSICIAN_TYPES,
  REMUNERATION_TYPES,
  type AdminUser,
  type AdminUserCreate,
  type AdminUserFields,
  type PhysicianType,
  type RemunerationType,
  type UserRole,
} from "../../../api";
import { Banner, Button, FormField, Modal, Select, TextField } from "../../../components";
import { ROLE_LABELS } from "./format";

interface UserFormModalProps {
  // Absent: a new account (the email is asked for); present: that account's edit.
  user?: AdminUser;
  onSubmit: (fields: AdminUserCreate) => Promise<void>;
  onClose: () => void;
}

// Create or edit an account: identity, role and the practice facts in effect from today.
export function UserFormModal({ user, onSubmit, onClose }: UserFormModalProps) {
  const [email, setEmail] = useState(user?.email ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [role, setRole] = useState<UserRole>(user?.role ?? "physician");
  const [practiceNumber, setPracticeNumber] = useState(user?.practice_number ?? "");
  const [physicianType, setPhysicianType] = useState<PhysicianType | "">(user?.physician_type ?? "");
  const [panelSize, setPanelSize] = useState(user?.panel_size != null ? String(user.panel_size) : "");
  const [remunerationType, setRemunerationType] = useState<RemunerationType | "">(user?.remuneration_type ?? "");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!fullName.trim() || (!user && !email.trim())) {
      setError("Le courriel et le nom sont obligatoires.");
      return;
    }
    const fields: AdminUserFields = {
      full_name: fullName.trim(),
      role,
      practice_number: practiceNumber.trim() || null,
      physician_type: physicianType || null,
      panel_size: panelSize.trim() === "" ? null : Number(panelSize),
      remuneration_type: remunerationType || null,
    };
    setSubmitting(true);
    try {
      await onSubmit({ ...fields, email: email.trim() });
    } catch (err) {
      setError(describeError(err));
      setSubmitting(false);
    }
  }

  return (
    <Modal title={user ? `Modifier ${user.full_name}` : "Nouvel utilisateur"} onClose={onClose}>
      <form id="admin-user-form" onSubmit={handleSubmit} className="flex flex-col gap-4 pb-2">
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            id="admin-user-email"
            label="Courriel"
            hint={user ? "Le courriel sert d'identifiant et ne se modifie pas." : undefined}
          >
            <TextField
              id="admin-user-email"
              type="email"
              value={email}
              disabled={!!user}
              onChange={(event) => setEmail(event.target.value)}
            />
          </FormField>
          <FormField id="admin-user-name" label="Nom complet">
            <TextField id="admin-user-name" value={fullName} onChange={(event) => setFullName(event.target.value)} />
          </FormField>
          <FormField id="admin-user-role" label="Rôle">
            <Select
              id="admin-user-role"
              containerClassName="max-w-none"
              value={role}
              onChange={(event) => setRole(event.target.value as UserRole)}
            >
              {(Object.keys(ROLE_LABELS) as UserRole[]).map((value) => (
                <option key={value} value={value}>
                  {ROLE_LABELS[value]}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="admin-user-practice-number" label="Numéro de pratique" hint="5 ou 6 chiffres.">
            <TextField
              id="admin-user-practice-number"
              value={practiceNumber}
              onChange={(event) => setPracticeNumber(event.target.value)}
            />
          </FormField>
          <FormField id="admin-user-physician-type" label="Type de pratique">
            <Select
              id="admin-user-physician-type"
              containerClassName="max-w-none"
              value={physicianType}
              onChange={(event) => setPhysicianType(event.target.value as PhysicianType | "")}
            >
              <option value="">—</option>
              {PHYSICIAN_TYPES.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="admin-user-remuneration" label="Mode de rémunération">
            <Select
              id="admin-user-remuneration"
              containerClassName="max-w-none"
              value={remunerationType}
              onChange={(event) => setRemunerationType(event.target.value as RemunerationType | "")}
            >
              <option value="">—</option>
              {REMUNERATION_TYPES.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="admin-user-panel-size" label="Nombre de patients" hint="Clientèle inscrite.">
            <TextField
              id="admin-user-panel-size"
              type="number"
              min={0}
              value={panelSize}
              onChange={(event) => setPanelSize(event.target.value)}
            />
          </FormField>
        </div>
        {!user && (
          <p className="m-0 text-sm text-muted-foreground">
            Un mot de passe temporaire sera généré. L&apos;utilisateur devra le changer à sa première connexion.
          </p>
        )}
        {error && <Banner tone="error">{error}</Banner>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Enregistrement..." : user ? "Enregistrer" : "Créer le compte"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
