import { Link } from "react-router-dom";
import { Button } from "../../../components";

export function QuickActions() {
  return (
    <div className="flex flex-wrap gap-2">
      <Button asChild>
        <Link to="/app/ajouter">Ajouter des notes</Link>
      </Button>
      <Button asChild variant="secondary">
        <Link to="/app/inbox">Boîte de réception</Link>
      </Button>
      <Button asChild variant="secondary">
        <Link to="/app/facturation">Facturation</Link>
      </Button>
    </div>
  );
}
