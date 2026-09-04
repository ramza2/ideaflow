import { useEffect, useState } from "react";
import { listCategories } from "../../api/workspaces";
import { apiErrorMessage } from "../../api/client";
import { useWorkspace } from "../../workspace/WorkspaceProvider";
import { InlineAlert } from "../../components/common/EmptyState";
import { WorkspaceSettingsNav } from "../../components/workspace/WorkspaceSettingsNav";
import type { CategoryPublic } from "../../types/api";

export function WorkspaceCategoriesPage() {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? "";
  const [categories, setCategories] = useState<CategoryPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await listCategories(workspaceId);
        if (!cancelled) setCategories(data);
      } catch (err) {
        if (!cancelled) {
          setError(apiErrorMessage(err));
          setCategories([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8f8fb]">
      <WorkspaceSettingsNav />
      <div className="max-w-3xl mx-auto px-4 sm:px-8 py-8 space-y-4">
        <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-6">
          <h2 className="text-base font-bold text-[#111118]">카테고리</h2>
          <p className="text-sm text-[#6b6b80] mt-1">
            현재 카테고리 목록입니다. 카테고리 편집 기능은 아직 제공되지 않습니다.
          </p>
        </div>
        {error && <InlineAlert type="error" title="오류">{error}</InlineAlert>}
        {loading ? (
          <div className="text-sm text-[#6b6b80] px-1">불러오는 중...</div>
        ) : (
          <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-[#f8f8fb] text-left text-[#6b6b80]">
                <tr>
                  <th className="px-4 py-3 font-medium">이름</th>
                  <th className="px-4 py-3 font-medium">슬러그</th>
                  <th className="px-4 py-3 font-medium">순서</th>
                </tr>
              </thead>
              <tbody>
                {categories.map((c) => (
                  <tr key={c.id} className="border-t border-[rgba(0,0,0,0.06)]">
                    <td className="px-4 py-3 text-[#111118] font-medium">{c.name}</td>
                    <td className="px-4 py-3 text-[#6b6b80]">{c.slug}</td>
                    <td className="px-4 py-3 text-[#6b6b80]">{c.sort_order}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
