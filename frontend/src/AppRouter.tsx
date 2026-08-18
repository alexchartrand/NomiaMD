import { Navigate, Route, Routes } from "react-router-dom";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Pricing from "./pages/Pricing";
import Contact from "./pages/Contact";
import AppLayout from "./pages/app/AppLayout";
import ExtractionPage from "./pages/app/ExtractionPage";
import ChatbotPage from "./pages/app/ChatbotPage";

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/prix" element={<Pricing />} />
      <Route path="/contact" element={<Contact />} />
      <Route path="/app" element={<AppLayout />}>
        <Route index element={<Navigate to="/app/extraction" replace />} />
        <Route path="extraction" element={<ExtractionPage />} />
        <Route path="chat" element={<ChatbotPage />} />
      </Route>
    </Routes>
  );
}
