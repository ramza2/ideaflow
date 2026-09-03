import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { clsx } from "clsx";
import { FileInput, PenLine, Sparkles } from "lucide-react";
import { toast } from "../common/Toast";

type Align = "left" | "right";

interface IdeaCreateMenuProps {
  workspaceId: string;
  /** Render prop for the trigger button. Receives open state and toggle handler. */
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode;
  align?: Align;
  className?: string;
}

/**
 * Shared "새 아이디어" creation-method menu used by TopHeader and IdeaListPage.
 * Owns open/close, outside-click, and navigation so entry points stay consistent.
 */
export function IdeaCreateMenu({
  workspaceId,
  trigger,
  align = "right",
  className,
}: IdeaCreateMenuProps) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close if workspace changes while menu is open (avoid stale routes).
  useEffect(() => {
    setOpen(false);
  }, [workspaceId]);

  function toggle() {
    setOpen((prev) => !prev);
  }

  function go(path: string) {
    if (!workspaceId) return;
    navigate(`/w/${workspaceId}${path}`);
    setOpen(false);
  }

  function handleImportClick() {
    setOpen(false);
    toast.info("텍스트·파일 가져오기는 추후 제공됩니다.");
  }

  return (
    <div ref={rootRef} className={clsx("relative", className)}>
      {trigger({ open, toggle })}
      {open && (
        <div
          className={clsx(
            "absolute top-full mt-1 w-52 bg-white rounded-xl border border-[rgba(0,0,0,0.08)] shadow-lg py-1 z-50",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          <button
            type="button"
            onClick={() => go("/ideas/new/ai")}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-[#f5f3ff] group"
          >
            <div className="w-7 h-7 rounded-lg bg-[#ede9fe] flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-[#7c3aed]" />
            </div>
            <div className="text-left">
              <p className="text-sm font-semibold text-[#7c3aed]">AI로 빠르게 등록</p>
              <p className="text-xs text-[#6b6b80]">자연어로 입력</p>
            </div>
          </button>
          <button
            type="button"
            onClick={() => go("/ideas/new")}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-[#f4f4f8]"
          >
            <div className="w-7 h-7 rounded-lg bg-[#f0f0f5] flex items-center justify-center">
              <PenLine className="w-4 h-4 text-[#6b6b80]" />
            </div>
            <p className="text-sm text-[#111118]">직접 등록</p>
          </button>
          <button
            type="button"
            onClick={handleImportClick}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-[#f4f4f8]"
          >
            <div className="w-7 h-7 rounded-lg bg-[#f0f0f5] flex items-center justify-center">
              <FileInput className="w-4 h-4 text-[#6b6b80]" />
            </div>
            <p className="text-sm text-[#111118]">텍스트·파일 가져오기</p>
          </button>
        </div>
      )}
    </div>
  );
}
