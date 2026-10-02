import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog";

interface ModalProps {
  title: string;
  onClose: () => void;
  footer?: ReactNode;
  // Room for two things side by side (e.g. two notes to compare) instead of one column.
  wide?: boolean;
  children: ReactNode;
}

// Callers conditionally render <Modal> itself (rather than passing an `open` prop), so
// it's always "open" while mounted; Escape-to-close and overlay-click-to-close are handled
// by Radix's Dialog internally (the old component's manual keydown listener is no longer
// needed).
export function Modal({ title, onClose, footer, wide = false, children }: ModalProps) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      {/* shadcn's default dialog caps at sm:max-w-sm (24rem) and has no independent
          scroll region — this app's one modal holds a data table that can grow past the
          viewport, so it's widened to match the original 640px design and given a
          scrollable body with a fixed header/footer. */}
      <DialogContent className={cn("flex max-h-[calc(100vh-3rem)] flex-col sm:max-w-[640px]", wide && "sm:max-w-[1100px]")}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="-mx-4 flex-1 overflow-y-auto px-4">{children}</div>
        {/* This app's one modal footer pairs a status line with a single action button —
            override shadcn's default right-aligned footer to spread them apart, matching
            the original design's space-between layout. */}
        {footer && <DialogFooter className="sm:justify-between">{footer}</DialogFooter>}
      </DialogContent>
    </Dialog>
  );
}
