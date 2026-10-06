import { FilePlus2, ReceiptText } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "../../../components";

// The two ways work starts: notes in, or a claim with no note at all. Everything else is in
// the sidebar.
export function QuickActions() {
  return (
    <>
      <Button asChild variant="secondary">
        <Link to="/app/facturer">
          <ReceiptText aria-hidden />
          Facturer sans rencontre
        </Link>
      </Button>
      <Button asChild>
        <Link to="/app/ajouter">
          <FilePlus2 aria-hidden />
          Ajouter des notes
        </Link>
      </Button>
    </>
  );
}
