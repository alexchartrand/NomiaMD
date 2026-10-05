import { useAuth } from "../../../AuthContext";
import { Banner, Spinner } from "../../../components";
import { formatLongDate } from "../../../utils/date";
import { ChatCard } from "./ChatCard";
import { KpiTiles } from "./KpiTiles";
import { QuickActions } from "./QuickActions";
import { RecentEncounters } from "./RecentEncounters";
import { TaskList } from "./TaskList";
import { useDashboard } from "./useDashboard";
import { WeeklyActivityChart } from "./WeeklyActivityChart";

// The landing page after login: what's left to do, how billing is going, the latest
// encounters, and the RAMQ assistant on the side.
export default function DashboardPage() {
  const { user } = useAuth();
  const { dashboard, error } = useDashboard();

  return (
    <section className="mx-auto max-w-[1280px]">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold">Bonjour{user ? `, ${user.full_name}` : ""}</h1>
          {dashboard && (
            <p className="mt-1 text-sm text-muted-foreground first-letter:uppercase">{formatLongDate(dashboard.today)}</p>
          )}
        </div>
        <QuickActions />
      </div>

      {error && (
        <div className="mt-6">
          <Banner tone="error">{error}</Banner>
        </div>
      )}
      {dashboard && (
        <div className="mt-6">
          <KpiTiles dashboard={dashboard} />
        </div>
      )}

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-6">
          {!dashboard && !error && <Spinner label="Chargement…" />}
          {dashboard && (
            <>
              <TaskList dashboard={dashboard} />
              <WeeklyActivityChart weeks={dashboard.weekly_activity} />
              <RecentEncounters rows={dashboard.recent_encounters} />
            </>
          )}
        </div>
        <ChatCard />
      </div>
    </section>
  );
}
