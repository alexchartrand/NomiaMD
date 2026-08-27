import { useEffect, useState, type FormEvent } from "react";
import {
  PHYSICIAN_TYPES,
  REMUNERATION_TYPES,
  describeError,
  updateProfile,
  changePassword,
  type PhysicianType,
  type RemunerationType,
} from "../../api";
import {
  Banner,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Select,
  TextField,
} from "../../components";
import { useAuth } from "../../AuthContext";

export default function ProfilePage() {
  const { user, refreshUser } = useAuth();

  const [fullName, setFullName] = useState("");
  const [physicianType, setPhysicianType] = useState<PhysicianType | "">("");
  const [numberOfPatients, setNumberOfPatients] = useState("");
  const [remunerationType, setRemunerationType] = useState<RemunerationType | "">("");
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSuccess, setProfileSuccess] = useState(false);
  const [profileSubmitting, setProfileSubmitting] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState(false);
  const [passwordSubmitting, setPasswordSubmitting] = useState(false);

  useEffect(() => {
    if (!user) return;
    setFullName(user.full_name);
    setPhysicianType((user.physician_type as PhysicianType | null) ?? "");
    setNumberOfPatients(user.number_of_patients != null ? String(user.number_of_patients) : "");
    setRemunerationType((user.remuneration_type as RemunerationType | null) ?? "");
  }, [user]);

  async function handleProfileSubmit(event: FormEvent) {
    event.preventDefault();
    setProfileError(null);
    setProfileSuccess(false);

    const parsedCount = numberOfPatients.trim() === "" ? null : Number(numberOfPatients);
    if (parsedCount !== null && (Number.isNaN(parsedCount) || parsedCount < 0)) {
      setProfileError("Le nombre de patients doit être un nombre entier positif.");
      return;
    }

    setProfileSubmitting(true);
    try {
      const updated = await updateProfile({
        full_name: fullName,
        physician_type: physicianType === "" ? null : physicianType,
        number_of_patients: parsedCount,
        remuneration_type: remunerationType === "" ? null : remunerationType,
      });
      refreshUser(updated);
      setProfileSuccess(true);
    } catch (err) {
      setProfileError(describeError(err));
    } finally {
      setProfileSubmitting(false);
    }
  }

  async function handlePasswordSubmit(event: FormEvent) {
    event.preventDefault();
    setPasswordError(null);
    setPasswordSuccess(false);

    if (newPassword.length < 8) {
      setPasswordError("Le nouveau mot de passe doit contenir au moins 8 caractères.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("Les nouveaux mots de passe ne correspondent pas.");
      return;
    }

    setPasswordSubmitting(true);
    try {
      await changePassword({ current_password: currentPassword, new_password: newPassword });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordSuccess(true);
    } catch (err) {
      setPasswordError(describeError(err));
    } finally {
      setPasswordSubmitting(false);
    }
  }

  if (!user) return null;

  return (
    <section className="max-w-3xl space-y-6">
      <h1 className="font-heading text-2xl font-semibold">Profil</h1>

      <Card>
        <CardHeader>
          <CardTitle>Renseignements</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleProfileSubmit} className="flex flex-col items-start gap-4">
            <div className="flex w-full max-w-sm flex-col gap-1.5">
              <label htmlFor="profile-email" className="text-sm text-muted-foreground">
                Courriel
              </label>
              <TextField id="profile-email" value={user.email} disabled />
            </div>

            <div className="flex w-full max-w-sm flex-col gap-1.5">
              <label htmlFor="profile-full-name" className="text-sm text-muted-foreground">
                Nom complet
              </label>
              <TextField
                id="profile-full-name"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
              />
            </div>

            <div className="flex w-full max-w-sm flex-col gap-1.5">
              <label htmlFor="profile-physician-type" className="text-sm text-muted-foreground">
                Type de pratique
              </label>
              <Select
                id="profile-physician-type"
                value={physicianType}
                onChange={(event) => setPhysicianType(event.target.value as PhysicianType | "")}
              >
                <option value="">—</option>
                {PHYSICIAN_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </Select>
            </div>

            <div className="flex w-full max-w-sm flex-col gap-1.5">
              <label htmlFor="profile-patient-count" className="text-sm text-muted-foreground">
                Nombre de patients
              </label>
              <TextField
                id="profile-patient-count"
                type="number"
                min={0}
                value={numberOfPatients}
                onChange={(event) => setNumberOfPatients(event.target.value)}
              />
            </div>

            <div className="flex w-full max-w-sm flex-col gap-1.5">
              <label htmlFor="profile-remuneration-type" className="text-sm text-muted-foreground">
                Mode de rémunération
              </label>
              <Select
                id="profile-remuneration-type"
                value={remunerationType}
                onChange={(event) => setRemunerationType(event.target.value as RemunerationType | "")}
              >
                <option value="">—</option>
                {REMUNERATION_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </Select>
            </div>

            {profileError && (
              <Banner tone="error" className="w-full max-w-sm">
                {profileError}
              </Banner>
            )}
            {profileSuccess && (
              <Banner tone="success" className="w-full max-w-sm">
                Profil mis à jour.
              </Banner>
            )}

            <Button type="submit" disabled={profileSubmitting}>
              {profileSubmitting ? "Enregistrement..." : "Enregistrer"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Mot de passe</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handlePasswordSubmit} className="flex flex-col items-start gap-4">
            <div className="flex w-full max-w-sm flex-col gap-1.5">
              <label htmlFor="profile-current-password" className="text-sm text-muted-foreground">
                Mot de passe actuel
              </label>
              <TextField
                id="profile-current-password"
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
              />
            </div>

            <div className="flex w-full max-w-sm flex-col gap-1.5">
              <label htmlFor="profile-new-password" className="text-sm text-muted-foreground">
                Nouveau mot de passe
              </label>
              <TextField
                id="profile-new-password"
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
              />
            </div>

            <div className="flex w-full max-w-sm flex-col gap-1.5">
              <label htmlFor="profile-confirm-password" className="text-sm text-muted-foreground">
                Confirmer le nouveau mot de passe
              </label>
              <TextField
                id="profile-confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
              />
            </div>

            {passwordError && (
              <Banner tone="error" className="w-full max-w-sm">
                {passwordError}
              </Banner>
            )}
            {passwordSuccess && (
              <Banner tone="success" className="w-full max-w-sm">
                Mot de passe modifié.
              </Banner>
            )}

            <Button type="submit" disabled={passwordSubmitting}>
              {passwordSubmitting ? "Enregistrement..." : "Changer le mot de passe"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </section>
  );
}
