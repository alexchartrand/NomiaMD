import { MoreHorizontal, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";

export interface RowAction {
  label: string;
  onSelect: () => void;
  icon?: LucideIcon;
  // Destructive: listed last, apart from the others, in red.
  danger?: boolean;
  disabled?: boolean;
}

interface RowActionsProps {
  actions: RowAction[];
  // Names the menu for screen readers: "Actions — Roch D.".
  label?: string;
  className?: string;
}

// The "⋯" menu holding a row's secondary and destructive actions, so a list shows one
// clear primary action per row instead of a cluster of buttons.
export function RowActions({ actions, label = "Plus d'actions", className }: RowActionsProps) {
  const shown = actions.filter((action) => !action.disabled);
  if (shown.length === 0) return null;
  const regular = shown.filter((action) => !action.danger);
  const danger = shown.filter((action) => action.danger);
  const item = (action: RowAction) => (
    <DropdownMenuItem
      key={action.label}
      variant={action.danger ? "destructive" : "default"}
      onSelect={action.onSelect}
      className="cursor-pointer py-1.5"
    >
      {action.icon && <action.icon aria-hidden />}
      {action.label}
    </DropdownMenuItem>
  );
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger
        aria-label={label}
        className={cn(
          "inline-flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-transparent text-muted-foreground transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 data-[state=open]:bg-muted",
          className,
        )}
        // A row that opens on click mustn't open when its menu does.
        onClick={(event) => event.stopPropagation()}
      >
        <MoreHorizontal aria-hidden className="size-4" />
      </DropdownMenuTrigger>
      {/* React events bubble through portals: keep the menu's clicks off the row. */}
      <DropdownMenuContent align="end" className="w-auto min-w-44" onClick={(event) => event.stopPropagation()}>
        {regular.map(item)}
        {regular.length > 0 && danger.length > 0 && <DropdownMenuSeparator />}
        {danger.map(item)}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
