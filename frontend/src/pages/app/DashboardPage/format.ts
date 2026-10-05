// Small display helpers shared by the dashboard's cards.

export function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count > 1 ? pluralForm : singular}`;
}

export function formatMoney(amount: number): string {
  return `${amount.toFixed(2)} $`;
}

// "octobre" for an ISO date.
export function monthName(isoDate: string): string {
  return new Intl.DateTimeFormat("fr-CA", { timeZone: "UTC", month: "long" }).format(new Date(`${isoDate}T00:00:00Z`));
}

// "5 oct." for an ISO date.
export function formatShortDay(isoDate: string): string {
  return new Intl.DateTimeFormat("fr-CA", { timeZone: "UTC", day: "numeric", month: "short" }).format(
    new Date(`${isoDate}T00:00:00Z`),
  );
}

// A pre-filtered inbox over every date (InboxPage/inboxView.ts reads these params).
export function inboxUrl(status: string): string {
  return `/app/inbox?${new URLSearchParams({ all: "1", status })}`;
}
