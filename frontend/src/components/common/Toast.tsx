import { Toaster as SonnerToaster, toast as sonnerToast } from "sonner";
import { Check, AlertCircle, Info, AlertTriangle } from "lucide-react";

export function ToastContainer() {
  return (
    <SonnerToaster
      position="bottom-right"
      expand={false}
      richColors={false}
      toastOptions={{
        style: {
          background: "white",
          border: "1px solid rgba(0,0,0,0.08)",
          borderRadius: "12px",
          boxShadow: "0 8px 30px rgba(0,0,0,0.12)",
          color: "#111118",
          fontSize: "14px",
          fontFamily: "'Inter', system-ui, sans-serif",
          padding: "12px 16px",
        },
      }}
    />
  );
}

export const toast = {
  success: (message: string, description?: string) =>
    sonnerToast(message, {
      description,
      icon: <Check className="w-4 h-4 text-[#16a34a]" />,
    }),
  error: (message: string, description?: string) =>
    sonnerToast(message, {
      description,
      icon: <AlertCircle className="w-4 h-4 text-[#dc2626]" />,
    }),
  info: (message: string, description?: string) =>
    sonnerToast(message, {
      description,
      icon: <Info className="w-4 h-4 text-[#4f46e5]" />,
    }),
  warning: (message: string, description?: string) =>
    sonnerToast(message, {
      description,
      icon: <AlertTriangle className="w-4 h-4 text-[#d97706]" />,
    }),
};
