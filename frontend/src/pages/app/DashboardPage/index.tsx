import { useAuth } from "../../../AuthContext";
import { AppPage, AppPageHeader, Banner, Skeleton } from "../../../components";
import { formatLongDate } from "../../../utils/date";
import { ChatCard } from "./ChatCard";
import { KpiTiles } from "./KpiTiles";
import { QuickActions } from "./QuickActions";
import { RecentEncounters } from "./RecentEncounters";
import { TaskList } from "./TaskList";
import { useDashboard } from "./useDashboard";
import { WeeklyActivityChart } from "./WeeklyActivityChart";

// The dashboard's shape while it loads, so nothing jumps when it arrives.
function DashboardSkeleton() {
  return (
    <div aria-busy="true" aria-label="Chargement du tableau de bord" className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-[104px] rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-64 rounded-xl" />
      <Skeleton className="h-56 rounded-xl" />
    </div>
  );
}

// The landing page after login: what's left to do, how billing is going, the latest
// encounters, and the RAMQ assistant on the side.
export default function DashboardPage() {
  const { user } = useAuth();
  const { dashboard, error } = useDashboard();

  return (
    <AppPage className="max-w-[1280px]">
      <AppPageHeader
        title={`Bonjour${user ? `, ${user.full_name}` : ""}`}
        documentTitle="Tableau de bord"
        description={
          dashboard ? <span className="inline-block first-letter:uppercase">{formatLongDate(dashboard.today)}</span> : undefined
        }
        actions={<QuickActions />}
      />

      {error && <Banner tone="error">{error}</Banner>}
      {!dashboard && !error && <DashboardSkeleton />}
      {dashboard && <KpiTiles dashboard={dashboard} />}

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex min-w-0 flex-col gap-6">
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
    </AppPage>
  );
}
