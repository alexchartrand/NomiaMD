import { useCallback, useState, type ReactNode } from "react";
import { Button } from "./Button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog";

export interface ConfirmOptions {
  title: string;
  message: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  // "danger" for an action that can't be undone.
  tone?: "primary" | "danger";
}

interface ConfirmDialogProps extends ConfirmOptions {
  onAnswer: (confirmed: boolean) => void;
}

// A yes/no question in the app's own chrome, in place of the browser's window.confirm.
// Escape, the overlay and "Annuler" all answer no.
export function ConfirmDialog({ title, message, confirmLabel, cancelLabel = "Annuler", tone = "primary", onAnswer }: ConfirmDialogProps) {
  return (
    <Dialog open onOpenChange={(open) => !open && onAnswer(false)}>
      <DialogContent showCloseButton={false} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{message}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={() => onAnswer(false)}>
            {cancelLabel}
          </Button>
          <Button type="button" variant={tone} onClick={() => onAnswer(true)}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// `confirm(options)` opens the dialog and resolves with the answer; render `dialog` once,
// anywhere in the caller's tree.
export function useConfirm(): { confirm: (options: ConfirmOptions) => Promise<boolean>; dialog: ReactNode } {
  const [pending, setPending] = useState<{ options: ConfirmOptions; resolve: (confirmed: boolean) => void } | null>(null);

  const confirm = useCallback(
    (options: ConfirmOptions) => new Promise<boolean>((resolve) => setPending({ options, resolve })),
    [],
  );

  const dialog = pending && (
    <ConfirmDialog
      {...pending.options}
      onAnswer={(confirmed) => {
        pending.resolve(confirmed);
        setPending(null);
      }}
    />
  );
  return { confirm, dialog };
}
