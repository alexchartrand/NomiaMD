import type { ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components";
import type { ConsultationDigest } from "../../../api";
import { NeedsConfirmation } from "./NeedsConfirmation";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-x-4 gap-y-0.5 sm:grid-cols-[11rem_minmax(0,1fr)]">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="m-0 text-[0.92rem]">{children}</dd>
    </div>
  );
}

function Items({ items }: { items: string[] }) {
  if (items.length === 1) return <>{items[0]}</>;
  return (
    <ul className="m-0 flex list-disc flex-col gap-0.5 pl-4">
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  );
}

// What the note says, in the few facts the codes are checked against: read this, not the
// whole note, to approve. Nothing for a run stored without a readable summary.
export function ConsultationSummary({ summary }: { summary: ConsultationDigest | null | undefined }) {
  if (!summary) return null;
  const referral = summary.referral;
  const referralText = referral ? [referral.requester, referral.reason].filter(Boolean).join(" · ") || "Oui" : null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-heading text-lg font-bold">Résumé de la consultation</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="m-0 leading-relaxed">{summary.short_description}</p>
        <dl aria-label="Éléments de la consultation" className="m-0 flex flex-col gap-2">
          {summary.reason_for_visit && <Row label="Motif">{summary.reason_for_visit}</Row>}
          {referralText && <Row label="Référence reçue">{referralText}</Row>}
          {summary.procedures.length > 0 && (
            <Row label="Actes réalisés">
              <Items items={summary.procedures} />
            </Row>
          )}
          {summary.billable_add_ons.length > 0 && (
            <Row label="Autres éléments facturables">
              <Items items={summary.billable_add_ons} />
            </Row>
          )}
        </dl>
        {summary.open_questions.length > 0 && (
          <section aria-label="À vérifier" className="flex flex-col gap-1.5">
            <h3 className="m-0 font-heading text-sm font-semibold text-muted-foreground">À vérifier</h3>
            <NeedsConfirmation notes={summary.open_questions} />
          </section>
        )}
      </CardContent>
    </Card>
  );
}
