import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { clsx } from "clsx";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  leadingIcon?: React.ReactNode;
  trailingIcon?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, leadingIcon, trailingIcon, className, ...props }, ref) => {
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label className="text-sm font-medium text-[#111118]">{label}</label>
        )}
        <div className="relative">
          {leadingIcon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[#6b6b80]">
              {leadingIcon}
            </div>
          )}
          <input
            ref={ref}
            className={clsx(
              "w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm text-[#111118] placeholder:text-[#9ca3af] transition-colors",
              "focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]",
              error && "border-[#dc2626] focus:ring-[#dc2626]/20 focus:border-[#dc2626]",
              leadingIcon && "pl-9",
              trailingIcon && "pr-9",
              className
            )}
            {...props}
          />
          {trailingIcon && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-[#6b6b80]">
              {trailingIcon}
            </div>
          )}
        </div>
        {error && <p className="text-xs text-[#dc2626]">{error}</p>}
        {helperText && !error && <p className="text-xs text-[#6b6b80]">{helperText}</p>}
      </div>
    );
  }
);
Input.displayName = "Input";

interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
  showCount?: boolean;
  maxLength?: number;
}

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(
  ({ label, error, helperText, showCount, maxLength, className, value, ...props }, ref) => {
    const count = typeof value === "string" ? value.length : 0;
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label className="text-sm font-medium text-[#111118]">{label}</label>
        )}
        <textarea
          ref={ref}
          value={value}
          maxLength={maxLength}
          className={clsx(
            "w-full rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 py-2.5 text-sm text-[#111118] placeholder:text-[#9ca3af] transition-colors resize-none",
            "focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]",
            error && "border-[#dc2626]",
            className
          )}
          {...props}
        />
        <div className="flex justify-between">
          {error ? (
            <p className="text-xs text-[#dc2626]">{error}</p>
          ) : helperText ? (
            <p className="text-xs text-[#6b6b80]">{helperText}</p>
          ) : <span />}
          {showCount && maxLength && (
            <span className="text-xs text-[#6b6b80] font-mono">
              {count}/{maxLength}
            </span>
          )}
        </div>
      </div>
    );
  }
);
TextArea.displayName = "TextArea";

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: { value: string; label: string }[];
}

export function Select({ label, options, className, ...props }: SelectProps) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && <label className="text-sm font-medium text-[#111118]">{label}</label>}
      <select
        className={clsx(
          "h-9 w-full rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm text-[#111118]",
          "focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]",
          className
        )}
        {...props}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

export function Checkbox({
  label,
  className,
  ...props
}: { label?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className={clsx("flex items-center gap-2 cursor-pointer group", className)}>
      <input
        type="checkbox"
        className="w-4 h-4 rounded border-[rgba(0,0,0,0.2)] accent-[#4f46e5] cursor-pointer"
        {...props}
      />
      {label && <span className="text-sm text-[#111118]">{label}</span>}
    </label>
  );
}

export function Switch({
  label,
  checked,
  onChange,
}: {
  label?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2.5 cursor-pointer">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={clsx(
          "relative w-9 h-5 rounded-full transition-colors duration-200",
          checked ? "bg-[#4f46e5]" : "bg-[#cbced4]"
        )}
      >
        <span
          className={clsx(
            "absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow-sm transition-transform duration-200",
            checked && "translate-x-4"
          )}
        />
      </button>
      {label && <span className="text-sm text-[#111118]">{label}</span>}
    </label>
  );
}
