import { useEffect, useState, type FormEvent } from "react";
import {
  PHYSICIAN_TYPES,
  describeError,
  updateProfile,
  changePassword,
  type PhysicianType,
} from "../../api";
import { Banner, Button, Card, Select, TextField } from "../../components";
import { useAuth } from "../../AuthContext";

export default function ProfilePage() {
  const { user, refreshUser } = useAuth();

  const [fullName, setFullName] = useState("");
  const [physicianType, setPhysicianType] = useState<PhysicianType | "">("");
  const [numberOfPatients, setNumberOfPatients] = useState("");
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
    <section className="page-panel">
      <h1>Profil</h1>

      <Card>
        <h2>Renseignements</h2>
        <form onSubmit={handleProfileSubmit} className="login-form">
          <label htmlFor="profile-email">Courriel</label>
          <TextField id="profile-email" value={user.email} disabled />

          <label htmlFor="profile-full-name">Nom complet</label>
          <TextField
            id="profile-full-name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
          />

          <label htmlFor="profile-physician-type">Type de pratique</label>
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

          <label htmlFor="profile-patient-count">Nombre de patients</label>
          <TextField
            id="profile-patient-count"
            type="number"
            min={0}
            value={numberOfPatients}
            onChange={(event) => setNumberOfPatients(event.target.value)}
          />

          {profileError && <Banner tone="error">{profileError}</Banner>}
          {profileSuccess && <Banner tone="success">Profil mis à jour.</Banner>}

          <Button type="submit" disabled={profileSubmitting}>
            {profileSubmitting ? "Enregistrement..." : "Enregistrer"}
          </Button>
        </form>
      </Card>

      <Card>
        <h2>Mot de passe</h2>
        <form onSubmit={handlePasswordSubmit} className="login-form">
          <label htmlFor="profile-current-password">Mot de passe actuel</label>
          <TextField
            id="profile-current-password"
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
          />

          <label htmlFor="profile-new-password">Nouveau mot de passe</label>
          <TextField
            id="profile-new-password"
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />

          <label htmlFor="profile-confirm-password">Confirmer le nouveau mot de passe</label>
          <TextField
            id="profile-confirm-password"
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />

          {passwordError && <Banner tone="error">{passwordError}</Banner>}
          {passwordSuccess && <Banner tone="success">Mot de passe modifié.</Banner>}

          <Button type="submit" disabled={passwordSubmitting}>
            {passwordSubmitting ? "Enregistrement..." : "Changer le mot de passe"}
          </Button>
        </form>
      </Card>
    </section>
  );
}
