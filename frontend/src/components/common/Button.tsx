import { type ReactNode, type ButtonHTMLAttributes } from "react";
import { clsx } from "clsx";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "ai" | "icon";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children?: ReactNode;
  icon?: ReactNode;
}

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-[#4f46e5] text-white hover:bg-[#4338ca] active:bg-[#3730a3] shadow-sm",
  secondary:
    "bg-white text-[#111118] border border-[rgba(0,0,0,0.1)] hover:bg-[#f4f4f8] active:bg-[#ececf2] shadow-sm",
  ghost:
    "bg-transparent text-[#6b6b80] hover:bg-[#f0f0f5] hover:text-[#111118] active:bg-[#e8e8f0]",
  danger:
    "bg-[#dc2626] text-white hover:bg-[#b91c1c] active:bg-[#991b1b] shadow-sm",
  ai: "bg-[#7c3aed] text-white hover:bg-[#6d28d9] active:bg-[#5b21b6] shadow-sm",
  icon: "bg-transparent text-[#6b6b80] hover:bg-[#f0f0f5] hover:text-[#111118] rounded-lg",
};

const sizeClasses: Record<Size, string> = {
  sm: "h-7 px-3 text-xs rounded-md gap-1.5",
  md: "h-8 px-3.5 text-sm rounded-lg gap-2",
  lg: "h-10 px-4 text-sm rounded-lg gap-2",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  children,
  icon,
  className,
  disabled,
  ...props
}: ButtonProps) {
  const isDisabled = disabled || loading;

  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center font-medium transition-colors duration-150 whitespace-nowrap select-none",
        variantClasses[variant],
        variant === "icon" ? "h-8 w-8 p-0" : sizeClasses[size],
        isDisabled && "opacity-50 cursor-not-allowed pointer-events-none",
        className
      )}
      disabled={isDisabled}
      {...props}
    >
      {loading ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
      ) : icon ? (
        <span className="shrink-0">{icon}</span>
      ) : null}
      {children && <span>{children}</span>}
    </button>
  );
}
