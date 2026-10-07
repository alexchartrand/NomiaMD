import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { CalendarDays, Clock, Cake, FileText, HeartHandshake, Layers, UserCheck } from "lucide-react";
import type { EncounterDetail } from "../../../api";
import { clinicDayOf, formatAge, formatClinicTime, formatDate } from "../../../utils/date";
import { sourceLabel } from "../../../utils/sources";

function Fact({ icon: Icon, label, children }: { icon: LucideIcon; label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <Icon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      <dt className="sr-only">{label}</dt>
      <dd className="m-0 truncate text-sm">{children}</dd>
    </div>
  );
}

function registrationText(registered: boolean | null): string {
  if (registered === true) return "Inscrit auprès de vous";
  if (registered === false) return "Non inscrit auprès de vous";
  return "Inscription inconnue";
}

// The visit (when, from where) and the patient facts its billing context was built from —
// what decided which codes were offered, read from the file, never from the note.
export function EncounterFacts({ encounter }: { encounter: EncounterDetail }) {
  const patient = encounter.patient;
  const day = encounter.service_date ?? clinicDayOf(encounter.received_at);
  return (
    <div className="flex flex-wrap items-stretch gap-x-8 gap-y-3 rounded-xl border border-border bg-card px-4 py-3">
      <dl aria-label="Rencontre" className="m-0 flex flex-wrap items-center gap-x-5 gap-y-2">
        <Fact icon={CalendarDays} label="Date du service">
          {encounter.service_date ? formatDate(encounter.service_date) : "Date à préciser"}
        </Fact>
        <Fact icon={Clock} label="Reçue à">
          Reçue à {formatClinicTime(encounter.received_at)}
        </Fact>
        <Fact icon={FileText} label="Source">
          {sourceLabel(encounter.source_system)}
        </Fact>
        {encounter.batch_label && (
          <Fact icon={Layers} label="Lot">
            {encounter.batch_label}
          </Fact>
        )}
      </dl>
      {patient && (
        <dl
          aria-label="Contexte de facturation"
          title="Tiré du dossier du patient et de votre profil : détermine les codes admissibles."
          className="m-0 flex flex-wrap items-center gap-x-5 gap-y-2 border-border sm:border-l sm:pl-8"
        >
          <Fact icon={Cake} label="Âge au jour du service">
            {formatAge(patient.date_of_birth, day)}
          </Fact>
          <Fact icon={UserCheck} label="Inscription">
            {registrationText(patient.is_registered)}
          </Fact>
          <Fact icon={HeartHandshake} label="Vulnérabilité">
            {patient.is_vulnerable ? "Clientèle vulnérable" : "Non vulnérable"}
          </Fact>
        </dl>
      )}
    </div>
  );
}
