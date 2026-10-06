import { Route, Routes } from "react-router-dom";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Pricing from "./pages/Pricing";
import Contact from "./pages/Contact";
import Security from "./pages/Security";
import Privacy from "./pages/Privacy";
import SiteLayout from "./pages/site/SiteLayout";
import AppLayout from "./pages/app/AppLayout";
import DashboardPage from "./pages/app/DashboardPage";
import InboxPage from "./pages/app/InboxPage";
import EncounterPage from "./pages/app/EncounterPage";
import AddNotesPage from "./pages/app/AddNotesPage";
import ChatbotPage from "./pages/app/ChatbotPage";
import PatientsPage from "./pages/app/PatientsPage";
import FacturationPage from "./pages/app/FacturationPage";
import FacturerPage from "./pages/app/FacturerPage";
import CodesPage from "./pages/app/CodesPage";
import ProfilePage from "./pages/app/ProfilePage";
import { RequireAuth } from "./AuthContext";

export default function AppRouter() {
  return (
    <Routes>
      <Route element={<SiteLayout />}>
        <Route path="/" element={<Landing />} />
        <Route path="/prix" element={<Pricing />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/securite" element={<Security />} />
        <Route path="/confidentialite" element={<Privacy />} />
      </Route>
      <Route path="/login" element={<Login />} />
      <Route
        path="/app"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="inbox/:encounterId" element={<EncounterPage />} />
        <Route path="ajouter" element={<AddNotesPage />} />
        <Route path="chat" element={<ChatbotPage />} />
        <Route path="patients" element={<PatientsPage />} />
        <Route path="facturation" element={<FacturationPage />} />
        <Route path="facturer" element={<FacturerPage />} />
        <Route path="facturer/:claimId" element={<FacturerPage />} />
        <Route path="codes" element={<CodesPage />} />
        <Route path="profile" element={<ProfilePage />} />
      </Route>
    </Routes>
  );
}
