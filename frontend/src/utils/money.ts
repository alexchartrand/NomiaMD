const MONEY = new Intl.NumberFormat("fr-CA", { style: "currency", currency: "CAD" });

// "1 234,50 $": Quebec French, as the RAMQ and the physician's own statements write it.
export function formatMoney(amount: number): string {
  return MONEY.format(amount);
}
