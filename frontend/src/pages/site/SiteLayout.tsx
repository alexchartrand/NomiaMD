import { Outlet } from "react-router-dom";
import { SiteHeader } from "@/components";
import { ScrollToTop } from "./ScrollToTop";
import { SiteFooter } from "./SiteFooter";

// Shell of every public (marketing) page; the app under /app has its own (AppLayout).
export default function SiteLayout() {
  return (
    <div className="flex min-h-screen flex-col">
      <ScrollToTop />
      <SiteHeader />
      <main className="flex-1">
        <Outlet />
      </main>
      <SiteFooter />
    </div>
  );
}
