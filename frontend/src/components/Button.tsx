import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";
import { Button as ShadcnButton, type buttonVariants } from "./ui/button";
import type { VariantProps } from "class-variance-authority";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "link";

const VARIANT_MAP: Record<ButtonVariant, VariantProps<typeof buttonVariants>["variant"]> = {
  primary: "default",
  secondary: "secondary",
  ghost: "ghost",
  danger: "destructive",
  link: "link",
};

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
};

export function Button({ variant = "primary", className, ...rest }: ButtonProps) {
  return (
    <ShadcnButton
      variant={VARIANT_MAP[variant]}
      // shadcn's "secondary" variant has no border by default; this app's original
      // secondary button did (white bg + visible border + primary-colored text).
      className={cn(variant === "secondary" && "border-border", className)}
      {...rest}
    />
  );
}
