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
import { toast } from "sonner";
import {
  AppPage,
  AppPageHeader,
  Banner,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  FormField,
  Select,
  TextField,
} from "../../components";
import { useAuth } from "../../AuthContext";

export default function ProfilePage() {
  const { user, refreshUser } = useAuth();

  const [fullName, setFullName] = useState("");
  const [physicianType, setPhysicianType] = useState<PhysicianType | "">("");
  const [panelSize, setPanelSize] = useState("");
  const [remunerationType, setRemunerationType] = useState<RemunerationType | "">("");
  const [practiceNumber, setPracticeNumber] = useState("");
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSubmitting, setProfileSubmitting] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSubmitting, setPasswordSubmitting] = useState(false);

  useEffect(() => {
    if (!user) return;
    setFullName(user.full_name);
    setPhysicianType(user.physician_type ?? "");
    setPanelSize(user.panel_size != null ? String(user.panel_size) : "");
    setRemunerationType(user.remuneration_type ?? "");
    setPracticeNumber(user.practice_number ?? "");
  }, [user]);

  async function handleProfileSubmit(event: FormEvent) {
    event.preventDefault();
    setProfileError(null);
    // A new attempt: the last one's confirmation no longer says anything.
    toast.dismiss("profile-saved");

    const parsedCount = panelSize.trim() === "" ? null : Number(panelSize);
    if (parsedCount !== null && (Number.isNaN(parsedCount) || parsedCount < 0)) {
      setProfileError("Le nombre de patients doit être un nombre entier positif.");
      return;
    }

    const trimmedPracticeNumber = practiceNumber.trim();
    if (trimmedPracticeNumber !== "" && !/^\d{5,6}$/.test(trimmedPracticeNumber)) {
      setProfileError("Le numéro de pratique doit contenir 5 ou 6 chiffres.");
      return;
    }

    setProfileSubmitting(true);
    try {
      const updated = await updateProfile({
        full_name: fullName,
        physician_type: physicianType === "" ? null : physicianType,
        panel_size: parsedCount,
        remuneration_type: remunerationType === "" ? null : remunerationType,
        practice_number: trimmedPracticeNumber === "" ? null : trimmedPracticeNumber,
      });
      refreshUser(updated);
      toast.success("Profil mis à jour.", { id: "profile-saved" });
    } catch (err) {
      setProfileError(describeError(err));
    } finally {
      setProfileSubmitting(false);
    }
  }

  async function handlePasswordSubmit(event: FormEvent) {
    event.preventDefault();
    setPasswordError(null);
    toast.dismiss("password-changed");

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
      toast.success("Mot de passe modifié.", { id: "password-changed" });
    } catch (err) {
      setPasswordError(describeError(err));
    } finally {
      setPasswordSubmitting(false);
    }
  }

  if (!user) return null;

  return (
    <AppPage width="narrow">
      <AppPageHeader title="Profil" description="Vos coordonnées et vos faits de pratique, à jour pour que les bons codes vous soient proposés." />

      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="font-heading text-lg font-semibold">Renseignements</CardTitle>
            <CardDescription>
              Le type de pratique, la taille de votre clientèle inscrite et votre numéro de pratique déterminent les codes
              admissibles. Chaque modification s&apos;applique à partir d&apos;aujourd&apos;hui.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleProfileSubmit} className="flex flex-col gap-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField id="profile-email" label="Courriel">
                  <TextField id="profile-email" value={user.email} disabled />
                </FormField>
                <FormField id="profile-full-name" label="Nom complet">
                  <TextField id="profile-full-name" value={fullName} onChange={(event) => setFullName(event.target.value)} />
                </FormField>
                <FormField id="profile-physician-type" label="Type de pratique">
                  <Select
                    id="profile-physician-type"
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
                <FormField id="profile-remuneration-type" label="Mode de rémunération">
                  <Select
                    id="profile-remuneration-type"
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
                <FormField id="profile-patient-count" label="Nombre de patients" hint="Votre clientèle inscrite.">
                  <TextField
                    id="profile-patient-count"
                    type="number"
                    min={0}
                    value={panelSize}
                    onChange={(event) => setPanelSize(event.target.value)}
                  />
                </FormField>
                <FormField
                  id="profile-practice-number"
                  label="Numéro de pratique"
                  hint="5 ou 6 chiffres. Vos patients inscrits sont ceux dont le médecin de famille porte ce numéro."
                >
                  <TextField
                    id="profile-practice-number"
                    value={practiceNumber}
                    onChange={(event) => setPracticeNumber(event.target.value)}
                    placeholder="12345"
                  />
                </FormField>
              </div>

              {profileError && <Banner tone="error">{profileError}</Banner>}

              <div className="flex justify-end">
                <Button type="submit" disabled={profileSubmitting}>
                  {profileSubmitting ? "Enregistrement..." : "Enregistrer"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="font-heading text-lg font-semibold">Mot de passe</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handlePasswordSubmit} className="flex flex-col gap-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField id="profile-current-password" label="Mot de passe actuel" className="sm:col-span-2 sm:max-w-[calc(50%-0.5rem)]">
                  <TextField
                    id="profile-current-password"
                    type="password"
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                  />
                </FormField>
                <FormField id="profile-new-password" label="Nouveau mot de passe" hint="Au moins 8 caractères.">
                  <TextField
                    id="profile-new-password"
                    type="password"
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                  />
                </FormField>
                <FormField id="profile-confirm-password" label="Confirmer le nouveau mot de passe">
                  <TextField
                    id="profile-confirm-password"
                    type="password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                  />
                </FormField>
              </div>

              {passwordError && <Banner tone="error">{passwordError}</Banner>}

              <div className="flex justify-end">
                <Button type="submit" disabled={passwordSubmitting}>
                  {passwordSubmitting ? "Enregistrement..." : "Changer le mot de passe"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </AppPage>
  );
}
