import { Outlet } from "react-router-dom";
import { BookOpen, Inbox, LayoutDashboard, MessagesSquare, ReceiptText, Users } from "lucide-react";
import { NavItem, NavSection, Sidebar } from "../../components";
import { RamqChatProvider } from "../../chat/RamqChatProvider";
import { useInboxCount } from "./shell/useNavCounts";
import { UserMenu } from "./shell/UserMenu";

export default function AppLayout() {
  const inboxCount = useInboxCount();

  return (
    // The page scrolls inside the content column, not the window: the sidebar stays put and
    // `sticky` elements (the review's save bar, the dashboard's assistant) stick to the screen.
    <div className="flex h-dvh">
      <Sidebar footer={<UserMenu />}>
        <NavSection>
          <NavItem to="/app" end icon={LayoutDashboard}>
            Tableau de bord
          </NavItem>
          <NavItem to="/app/inbox" icon={Inbox} count={inboxCount}>
            Rencontres
          </NavItem>
          <NavItem to="/app/facturation" icon={ReceiptText} alsoActiveOn={["/app/facturer"]}>
            Facturation
          </NavItem>
          <NavItem to="/app/patients" icon={Users}>
            Patients
          </NavItem>
        </NavSection>
        <NavSection title="Référence RAMQ">
          <NavItem to="/app/codes" icon={BookOpen}>
            Codes RAMQ
          </NavItem>
          <NavItem to="/app/chat" icon={MessagesSquare}>
            Assistant RAMQ
          </NavItem>
        </NavSection>
      </Sidebar>
      {/* Padded inside the scroll container, not on it: `sticky` offsets count from its padding edge. */}
      <div className="min-w-0 flex-1 overflow-y-auto">
        <div className="px-8 py-8">
          <RamqChatProvider>
            <Outlet />
          </RamqChatProvider>
        </div>
      </div>
    </div>
  );
}
