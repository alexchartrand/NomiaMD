import { useState } from "react";
import { Check, Copy } from "lucide-react";
import type { TemporaryPassword } from "../../../api";
import { Banner, Button, Modal } from "../../../components";

// The one time a temporary password is visible: the admin hands it to the user, who must
// replace it at their first login.
export function TemporaryPasswordModal({ issued, onClose }: { issued: TemporaryPassword; onClose: () => void }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(issued.temporary_password);
      setCopied(true);
    } catch {
      // No clipboard access (insecure context): the password stays selectable on screen.
    }
  }

  return (
    <Modal title="Mot de passe temporaire" onClose={onClose}>
      <div className="flex flex-col gap-4 pb-2">
        <p className="m-0 text-sm">
          Transmettez ce mot de passe à <strong>{issued.user.full_name}</strong> ({issued.user.email}) par un canal sûr.
          Il devra le changer à sa première connexion.
        </p>
        <div className="flex items-center gap-2">
          <code
            aria-label="Mot de passe temporaire"
            className="flex-1 rounded-lg border border-border bg-muted px-3 py-2 font-mono text-base select-all"
          >
            {issued.temporary_password}
          </code>
          <Button type="button" variant="secondary" onClick={copy}>
            {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
            {copied ? "Copié" : "Copier"}
          </Button>
        </div>
        <Banner tone="warning">Ce mot de passe est affiché une seule fois. Il ne pourra plus être consulté.</Banner>
        <div className="flex justify-end">
          <Button type="button" onClick={onClose}>
            Terminé
          </Button>
        </div>
      </div>
    </Modal>
  );
}
