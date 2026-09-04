import { useEffect, useState } from "react";
import { updateWorkspace } from "../../api/workspaces";
import { apiErrorMessage } from "../../api/client";
import { useWorkspace } from "../../workspace/WorkspaceProvider";
import { Button } from "../../components/common/Button";
import { Input } from "../../components/common/Input";
import { InlineAlert } from "../../components/common/EmptyState";
import { toast } from "../../components/common/Toast";
import { WorkspaceSettingsNav } from "../../components/workspace/WorkspaceSettingsNav";

function EffectiveBadge({
  workspaceAllow,
  effective,
  kind,
}: {
  workspaceAllow: boolean;
  effective: boolean;
  kind: "AI" | "웹 검색";
}) {
  if (effective) {
    return <span className="text-xs px-2 py-0.5 rounded-md font-medium bg-[#dcfce7] text-[#16a34a]">사용 가능</span>;
  }
  if (workspaceAllow) {
    return (
      <span className="text-xs px-2 py-0.5 rounded-md font-medium bg-[#fef3c7] text-[#b45309]">
        시스템 정책으로 차단됨
      </span>
    );
  }
  return (
    <span className="text-xs px-2 py-0.5 rounded-md font-medium bg-[#f3f4f6] text-[#6b6b80]">
      작업공간에서 {kind} 비허용
    </span>
  );
}

export function WorkspaceGeneralPage() {
  const { currentWorkspace, refreshWorkspaces } = useWorkspace();
  const isAdmin = currentWorkspace?.current_user_role === "ADMIN";

  const [name, setName] = useState(currentWorkspace?.name ?? "");
  const [allowLlm, setAllowLlm] = useState(currentWorkspace?.allow_llm ?? true);
  const [allowWebSearch, setAllowWebSearch] = useState(currentWorkspace?.allow_web_search ?? true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentWorkspace) return;
    setName(currentWorkspace.name);
    setAllowLlm(currentWorkspace.allow_llm);
    setAllowWebSearch(currentWorkspace.allow_web_search);
  }, [currentWorkspace]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!currentWorkspace || !isAdmin) return;
    const trimmed = name.trim();
    if (!trimmed) {
      setError("작업공간 이름을 입력해 주세요.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateWorkspace(currentWorkspace.id, {
        name: trimmed,
        allow_llm: allowLlm,
        allow_web_search: allowWebSearch,
      });
      await refreshWorkspaces();
      toast.success("작업공간 설정을 저장했습니다.");
    } catch (err) {
      setError(apiErrorMessage(err, "작업공간 설정을 저장하지 못했습니다."));
    } finally {
      setSaving(false);
    }
  }

  if (!currentWorkspace) {
    return (
      <div className="flex-1 overflow-y-auto bg-[#f8f8fb]">
        <WorkspaceSettingsNav />
        <div className="px-8 py-12 text-center text-sm text-[#6b6b80]">작업공간을 불러오는 중...</div>
      </div>
    );
  }

  const dirty =
    name.trim() !== currentWorkspace.name ||
    allowLlm !== currentWorkspace.allow_llm ||
    allowWebSearch !== currentWorkspace.allow_web_search;

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8f8fb]">
      <WorkspaceSettingsNav />
      <div className="max-w-2xl mx-auto px-4 sm:px-8 py-8">
        <form onSubmit={handleSave} className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-6 space-y-5">
          <div>
            <h2 className="text-base font-bold text-[#111118]">일반</h2>
            <p className="text-sm text-[#6b6b80] mt-1">
              {isAdmin
                ? "작업공간 이름과 AI·웹 검색 사용 정책을 관리합니다."
                : "읽기 전용입니다. 변경은 작업공간 관리자만 할 수 있습니다."}
            </p>
          </div>
          {error && <InlineAlert type="error" title="오류">{error}</InlineAlert>}

          {isAdmin ? (
            <Input label="작업공간 이름" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} required />
          ) : (
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-[#111118]">작업공간 이름</label>
              <input
                value={currentWorkspace.name}
                readOnly
                className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f8f8fb] px-3 text-sm text-[#6b6b80]"
              />
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-[#111118]">유형</label>
              <input
                value={currentWorkspace.type === "PERSONAL" ? "개인" : "팀"}
                readOnly
                className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f8f8fb] px-3 text-sm text-[#6b6b80]"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-[#111118]">내 역할</label>
              <input
                value={currentWorkspace.current_user_role}
                readOnly
                className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f8f8fb] px-3 text-sm text-[#6b6b80]"
              />
            </div>
          </div>

          <div className="space-y-4 pt-2 border-t border-[rgba(0,0,0,0.06)]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-[#111118]">작업공간 AI 사용</p>
                <p className="text-xs text-[#6b6b80] mt-1 flex items-center gap-2">
                  실제 적용 상태
                  <EffectiveBadge
                    workspaceAllow={currentWorkspace.allow_llm}
                    effective={currentWorkspace.effective_allow_llm}
                    kind="AI"
                  />
                </p>
              </div>
              <label className="inline-flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={allowLlm}
                  disabled={!isAdmin}
                  onChange={(e) => setAllowLlm(e.target.checked)}
                />
                {allowLlm ? "허용" : "비허용"}
              </label>
            </div>

            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-[#111118]">작업공간 웹 검색 사용</p>
                <p className="text-xs text-[#6b6b80] mt-1 flex items-center gap-2">
                  실제 적용 상태
                  <EffectiveBadge
                    workspaceAllow={currentWorkspace.allow_web_search}
                    effective={currentWorkspace.effective_allow_web_search}
                    kind="웹 검색"
                  />
                </p>
              </div>
              <label className="inline-flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={allowWebSearch}
                  disabled={!isAdmin}
                  onChange={(e) => setAllowWebSearch(e.target.checked)}
                />
                {allowWebSearch ? "허용" : "비허용"}
              </label>
            </div>
            {dirty && (
              <p className="text-xs text-[#b45309]">
                저장 후 실제 적용 상태가 갱신됩니다.
              </p>
            )}
            <p className="text-xs text-[#6b6b80]">
              전역 시스템 설정에서 AI/웹 검색이 차단되면 작업공간에서 허용해도 실제 적용 상태는 차단됩니다.
            </p>
          </div>

          {isAdmin && (
            <div className="pt-2">
              <Button type="submit" disabled={saving || !dirty}>
                {saving ? "저장 중..." : "저장"}
              </Button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
