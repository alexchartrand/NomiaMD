import { Navigate, Route, Routes } from "react-router-dom";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Pricing from "./pages/Pricing";
import Contact from "./pages/Contact";
import AppLayout from "./pages/app/AppLayout";
import InboxPage from "./pages/app/InboxPage";
import EncounterPage from "./pages/app/EncounterPage";
import AddNotesPage from "./pages/app/AddNotesPage";
import ChatbotPage from "./pages/app/ChatbotPage";
import PatientsPage from "./pages/app/PatientsPage";
import FacturationPage from "./pages/app/FacturationPage";
import ProfilePage from "./pages/app/ProfilePage";
import { RequireAuth } from "./AuthContext";

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/prix" element={<Pricing />} />
      <Route path="/contact" element={<Contact />} />
      <Route
        path="/app"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/app/inbox" replace />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="inbox/:encounterId" element={<EncounterPage />} />
        <Route path="ajouter" element={<AddNotesPage />} />
        <Route path="chat" element={<ChatbotPage />} />
        <Route path="patients" element={<PatientsPage />} />
        <Route path="facturation" element={<FacturationPage />} />
        <Route path="profile" element={<ProfilePage />} />
      </Route>
    </Routes>
  );
}
