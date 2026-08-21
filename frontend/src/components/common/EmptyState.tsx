import type { ReactNode } from "react";
import { clsx } from "clsx";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={clsx("flex flex-col items-center justify-center py-16 text-center", className)}>
      {icon && (
        <div className="w-12 h-12 rounded-2xl bg-[#f0f0f5] flex items-center justify-center text-[#9ca3af] mb-4">
          {icon}
        </div>
      )}
      <p className="text-sm font-medium text-[#111118] mb-1">{title}</p>
      {description && <p className="text-sm text-[#6b6b80] max-w-xs">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

interface InlineAlertProps {
  type: "info" | "success" | "warning" | "error";
  title?: string;
  children: ReactNode;
}

const alertClasses = {
  info: "bg-[#eff6ff] border-[#bfdbfe] text-[#1d4ed8]",
  success: "bg-[#f0fdf4] border-[#bbf7d0] text-[#15803d]",
  warning: "bg-[#fffbeb] border-[#fde68a] text-[#b45309]",
  error: "bg-[#fef2f2] border-[#fecaca] text-[#b91c1c]",
};

export function InlineAlert({ type, title, children }: InlineAlertProps) {
  return (
    <div className={clsx("rounded-lg border px-4 py-3 text-sm", alertClasses[type])}>
      {title && <p className="font-medium mb-0.5">{title}</p>}
      <p className="opacity-90">{children}</p>
    </div>
  );
}

interface ProgressStepperProps {
  steps: string[];
  current: number;
}

export function ProgressStepper({ steps, current }: ProgressStepperProps) {
  return (
    <div className="flex items-center">
      {steps.map((step, i) => (
        <div key={step} className="flex items-center">
          <div className="flex items-center gap-2">
            <div
              className={clsx(
                "w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold transition-colors",
                i < current && "bg-[#4f46e5] text-white",
                i === current && "bg-[#4f46e5] text-white ring-2 ring-[#4f46e5]/20",
                i > current && "bg-[#f0f0f5] text-[#6b6b80]"
              )}
            >
              {i < current ? "✓" : i + 1}
            </div>
            <span
              className={clsx(
                "text-sm font-medium hidden sm:block",
                i <= current ? "text-[#111118]" : "text-[#6b6b80]"
              )}
            >
              {step}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div
              className={clsx(
                "h-px w-8 mx-2 sm:w-12",
                i < current ? "bg-[#4f46e5]" : "bg-[#e8e8f0]"
              )}
            />
          )}
        </div>
      ))}
    </div>
  );
}
