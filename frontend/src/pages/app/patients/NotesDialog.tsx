import { useState, type FormEvent } from "react";
import { describeError, updateRosterEntry, type RosterEntry } from "../../../api";
import { Banner, Button, Modal, TextArea } from "../../../components";

interface NotesDialogProps {
  entry: RosterEntry;
  onClose: () => void;
  onSaved: () => void;
}

// The physician's own note on a patient of their list (never shared, never read by billing).
export function NotesDialog({ entry, onClose, onSaved }: NotesDialogProps) {
  const [draft, setDraft] = useState(entry.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await updateRosterEntry(entry.id, draft.trim() || null);
      onSaved();
    } catch (err) {
      setError(describeError(err));
      setSubmitting(false);
    }
  }

  return (
    <Modal title={`Notes — ${entry.full_name}`} onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 pb-1">
        <TextArea
          aria-label="Notes personnelles"
          className="min-h-32 w-full font-sans"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Visibles par vous seul."
        />
        {error && <Banner tone="error">{error}</Banner>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={submitting}>
            Annuler
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Enregistrement..." : "Enregistrer"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
