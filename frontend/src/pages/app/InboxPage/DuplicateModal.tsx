import { useEffect, useState } from "react";
import {
  confirmDuplicate,
  describeError,
  dismissDuplicate,
  getEncounter,
  type EncounterDetail,
} from "../../../api";
import { Banner, Button, Modal, Spinner } from "../../../components";
import { formatClinicTime } from "../../../utils/date";
import { StatusChip } from "./StatusChip";

interface DuplicateModalProps {
  encounterId: number;
  otherId: number;
  onClose: () => void;
  // Called once the physician answered, so the inbox re-reads its flags.
  onResolved: () => void;
}

// "Doublon possible": the two notes side by side. "Même visite" keeps one and hides the
// other (never billed); "Visites distinctes" clears the flag for good.
export function DuplicateModal({ encounterId, otherId, onClose, onResolved }: DuplicateModalProps) {
  const [pair, setPair] = useState<[EncounterDetail, EncounterDetail] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([getEncounter(encounterId), getEncounter(otherId)])
      .then(setPair)
      .catch((err) => setError(describeError(err)));
  }, [encounterId, otherId]);

  async function answer(action: () => Promise<void>) {
    setSaving(true);
    setError(null);
    try {
      await action();
      onResolved();
      onClose();
    } catch (err) {
      setError(describeError(err));
      setSaving(false);
    }
  }

  return (
    <Modal
      title="Doublon possible"
      wide
      onClose={onClose}
      footer={
        <>
          <span className="text-sm text-muted-foreground">Ces deux notes décrivent-elles la même visite ?</span>
          <Button type="button" variant="secondary" disabled={!pair || saving} onClick={() => answer(() => dismissDuplicate(encounterId))}>
            Visites distinctes
          </Button>
        </>
      }
    >
      {error && <Banner tone="error" className="mb-3">{error}</Banner>}
      {!pair && !error && <Spinner label="Chargement..." />}
      {pair && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {pair.map((encounter, i) => {
            const other = pair[1 - i];
            return (
              <div key={encounter.id} className="flex min-w-0 flex-col gap-2 rounded-lg border border-border p-3">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <StatusChip status={encounter.status} />
                  <span className="font-semibold">{encounter.source_system}</span>
                  <span className="text-muted-foreground">
                    reçue à {formatClinicTime(encounter.received_at)}
                    {encounter.meta.time_start ? ` · début ${encounter.meta.time_start.slice(0, 5)}` : ""}
                  </span>
                </div>
                <pre className="m-0 max-h-[50vh] flex-1 overflow-y-auto rounded-md bg-muted p-3 font-mono text-xs whitespace-pre-wrap">
                  {encounter.note_text}
                </pre>
                <Button
                  type="button"
                  disabled={saving}
                  onClick={() => answer(() => confirmDuplicate(other.id, encounter.id))}
                >
                  Même visite — garder celle-ci
                </Button>
              </div>
            );
          })}
        </div>
      )}
    </Modal>
  );
}
