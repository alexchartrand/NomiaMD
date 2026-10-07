import { daysBetween } from "../../../utils/date";

// RAMQ's billing deadline, as backend/app/dashboard/deadline.py states it (the rule's owner,
// whose numbers these mirror): a claim must reach the RAMQ within 90 days of its service
// date, and the last 15 of them are a warning.
const DEADLINE_DAYS = 90;
const WARNING_DAYS = 15;

// Negative once the deadline has passed; 0 is the last day.
export function daysLeft(serviceDate: string, today: string): number {
  return DEADLINE_DAYS - daysBetween(serviceDate, today);
}

export function isAtRisk(left: number): boolean {
  return left <= WARNING_DAYS;
}
