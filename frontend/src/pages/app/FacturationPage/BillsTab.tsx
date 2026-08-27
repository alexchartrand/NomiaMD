import { Fragment, useEffect, useState } from "react";
import {
  billPdfUrl,
  deleteBill,
  describeError,
  getBill,
  listBills,
  type Bill,
  type BillDetail,
} from "../../../api";
import { Banner, Button, Table } from "../../../components";
import { formatDate } from "../../../utils/date";

interface BillsTabProps {
  reloadSignal: number;
  onChanged: () => void;
}

export function BillsTab({ reloadSignal, onChanged }: BillsTabProps) {
  const [bills, setBills] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [expandedDetail, setExpandedDetail] = useState<BillDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  function loadBills() {
    setLoading(true);
    setListError(null);
    listBills()
      .then(setBills)
      .catch((err) => setListError(describeError(err)))
      .finally(() => setLoading(false));
  }

  useEffect(loadBills, [reloadSignal]);

  async function toggleExpand(bill: Bill) {
    if (expandedId === bill.id) {
      setExpandedId(null);
      setExpandedDetail(null);
      return;
    }
    setExpandedId(bill.id);
    setExpandedDetail(null);
    setDetailError(null);
    try {
      setExpandedDetail(await getBill(bill.id));
    } catch (err) {
      setDetailError(describeError(err));
    }
  }

  async function handleDelete(bill: Bill) {
    if (
      !window.confirm(
        `Supprimer la facture ${bill.number} ? Les ${bill.record_count} facturation(s) qu'elle contient redeviendront des brouillons.`,
      )
    )
      return;
    try {
      await deleteBill(bill.id);
      if (expandedId === bill.id) {
        setExpandedId(null);
        setExpandedDetail(null);
      }
      loadBills();
      onChanged();
    } catch (err) {
      setListError(describeError(err));
    }
  }

  if (loading) return <p className="status-inline">Chargement...</p>;
  if (listError) return <Banner tone="error">{listError}</Banner>;
  if (bills.length === 0) return <p>Aucune facture générée.</p>;

  return (
    <Table>
      <thead>
        <tr>
          <th>Numéro</th>
          <th>Période</th>
          <th>Générée le</th>
          <th>Facturations</th>
          <th>Total</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {bills.map((bill) => (
          <Fragment key={bill.id}>
            <tr>
              <td>{bill.number}</td>
              <td>
                {formatDate(bill.start_date)} – {formatDate(bill.end_date)}
              </td>
              <td>{formatDate(bill.generated_at.slice(0, 10))}</td>
              <td>
                {bill.record_count}{" "}
                <Button type="button" variant="link" onClick={() => toggleExpand(bill)}>
                  Détails
                </Button>
              </td>
              <td>{bill.total_amount != null ? `${bill.total_amount.toFixed(2)} $` : "—"}</td>
              <td>
                <div className="table-actions">
                  <a className="btn btn-secondary" href={billPdfUrl(bill.id)} download>
                    Télécharger le PDF
                  </a>
                  <Button type="button" variant="danger" onClick={() => handleDelete(bill)}>
                    Supprimer
                  </Button>
                </div>
              </td>
            </tr>
            {expandedId === bill.id && (
              <tr className="billing-details-row">
                <td colSpan={6}>
                  {detailError && <Banner tone="error">{detailError}</Banner>}
                  {!detailError && !expandedDetail && <p className="status-inline">Chargement...</p>}
                  {expandedDetail && (
                    <ul>
                      {expandedDetail.claims.map((c) => (
                        <li key={c.id}>
                          {formatDate(c.service_date)} — {c.patient_full_name} —{" "}
                          {c.codes.map((code) => code.code).join(", ")}
                          {c.total_amount != null && ` — ${c.total_amount.toFixed(2)} $`}
                        </li>
                      ))}
                    </ul>
                  )}
                </td>
              </tr>
            )}
          </Fragment>
        ))}
      </tbody>
    </Table>
  );
}
