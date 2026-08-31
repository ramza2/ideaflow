import { useEffect, useState } from "react";
import { AdminShell } from "../../components/admin/AdminShell";
import { Switch } from "../../components/common/Input";
import { Button } from "../../components/common/Button";
import { InlineAlert } from "../../components/common/EmptyState";
import { toast } from "../../components/common/Toast";
import { getSystemSettings, patchSystemSettings } from "../../api/adminSettings";
import { apiErrorMessage } from "../../api/client";
import type { SystemSettingsResponse } from "../../types/api";

export function AdminSystemSettingsPage() {
  const [settings, setSettings] = useState<SystemSettingsResponse | null>(null);
  const [draft, setDraft] = useState<SystemSettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await getSystemSettings();
      setSettings(data);
      setDraft(data);
    } catch (err) {
      setError(apiErrorMessage(err, "설정을 불러오지 못했습니다."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleSave() {
    if (!draft || !settings) return;
    setSaving(true);
    try {
      const body: Record<string, boolean> = {};
      if (draft.global_llm_enabled !== settings.global_llm_enabled) {
        body.global_llm_enabled = draft.global_llm_enabled;
      }
      if (draft.global_web_search_enabled !== settings.global_web_search_enabled) {
        body.global_web_search_enabled = draft.global_web_search_enabled;
      }
      if (draft.default_team_allow_llm !== settings.default_team_allow_llm) {
        body.default_team_allow_llm = draft.default_team_allow_llm;
      }
      if (draft.default_team_allow_web_search !== settings.default_team_allow_web_search) {
        body.default_team_allow_web_search = draft.default_team_allow_web_search;
      }
      const updated = Object.keys(body).length
        ? await patchSystemSettings(body)
        : settings;
      setSettings(updated);
      setDraft(updated);
      toast.success("설정이 저장되었습니다.");
    } catch (err) {
      toast.error(apiErrorMessage(err, "설정 저장에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  }

  function handleCancel() {
    if (settings) setDraft(settings);
  }

  return (
    <AdminShell title="시스템 설정">
      <div className="px-4 sm:px-8 py-6">
        <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-6 max-w-2xl">
          {loading && <p className="text-sm text-[#6b6b80]">불러오는 중...</p>}
          {error && <InlineAlert type="error" title="오류">{error}</InlineAlert>}
          {draft && !loading && (
            <div className="space-y-8">
              <section className="space-y-4">
                <h3 className="text-base font-bold text-[#111118]">전역 정책</h3>
                <Switch
                  label="전역 AI 기능 허용"
                  checked={draft.global_llm_enabled}
                  onChange={(v) => setDraft({ ...draft, global_llm_enabled: v })}
                />
                <p className="text-xs text-[#6b6b80] -mt-2">
                  끄면 새로운 AI 분석/재시도 요청이 차단됩니다. 이미 진행 중인 작업은 중단하지 않습니다.
                </p>
                <Switch
                  label="전역 웹 검색 허용"
                  checked={draft.global_web_search_enabled}
                  onChange={(v) => setDraft({ ...draft, global_web_search_enabled: v })}
                />
                <p className="text-xs text-[#6b6b80] -mt-2">
                  끄면 새로운 웹 조사 Preview/승인/재시도가 차단됩니다. 이미 저장된 근거는 계속 조회할 수 있습니다.
                </p>
              </section>

              <section className="space-y-4">
                <h3 className="text-base font-bold text-[#111118]">신규 팀 작업공간 기본값</h3>
                <Switch
                  label="신규 팀 작업공간 AI 기본 허용"
                  checked={draft.default_team_allow_llm}
                  onChange={(v) => setDraft({ ...draft, default_team_allow_llm: v })}
                />
                <Switch
                  label="신규 팀 작업공간 웹 검색 기본 허용"
                  checked={draft.default_team_allow_web_search}
                  onChange={(v) => setDraft({ ...draft, default_team_allow_web_search: v })}
                />
                <p className="text-xs text-[#6b6b80]">
                  신규 팀 작업공간 생성 시 기본값입니다. 기존 작업공간에는 영향을 주지 않습니다.
                </p>
              </section>

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="secondary" onClick={handleCancel} disabled={saving}>
                  취소
                </Button>
                <Button variant="primary" loading={saving} onClick={() => void handleSave()}>
                  저장
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </AdminShell>
  );
}
