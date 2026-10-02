import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-primary text-primary-foreground hover:brightness-110 active:brightness-95 shadow-sm",
  secondary:
    "bg-surface text-foreground border border-border hover:bg-surface-2 active:bg-muted",
  ghost: "text-muted-foreground hover:bg-surface-2 hover:text-foreground",
  danger:
    "bg-transparent text-danger border border-transparent hover:bg-danger-soft hover:border-danger/30",
};

const SIZES: Record<Size, string> = {
  // 36px and 44px tall: the md size meets the 44px touch target minimum.
  sm: "h-9 px-3 text-sm gap-1.5",
  md: "h-11 px-4 text-sm gap-2",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "sm",
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      className={cn(
        "inline-flex cursor-pointer items-center justify-center rounded-lg font-medium",
        "transition-[background-color,color,filter,border-color] duration-200",
        "disabled:pointer-events-none disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
    >
      {children}
    </button>
  );
}

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Required: an icon alone is never self-describing to a screen reader. */
  label: string;
  children: ReactNode;
}

export function IconButton({ label, className, children, ...props }: IconButtonProps) {
  return (
    <button
      {...props}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex size-9 cursor-pointer items-center justify-center rounded-lg",
        "text-muted-foreground transition-colors duration-200",
        "hover:bg-surface-2 hover:text-foreground",
        "disabled:pointer-events-none disabled:opacity-50",
        className,
      )}
    >
      {children}
    </button>
  );
}
