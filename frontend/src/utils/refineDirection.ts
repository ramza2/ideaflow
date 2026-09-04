import type { AiSessionStatus, IdeaRefineDirection } from "../types/api";

export const REFINE_DIRECTION_LABELS: Record<IdeaRefineDirection, string> = {
  EXPAND_DETAIL: "더 구체적으로 확장",
  TECHNICAL_IMPLEMENTATION: "기술 구현 관점",
  BUSINESS_PERSPECTIVE: "사업화 관점",
  USER_PERSPECTIVE: "사용자 관점",
  COUNTER_PERSPECTIVE: "반대 관점",
  RISK_ANALYSIS: "위험 분석",
  MINIMUM_VALIDATION: "최소 검증안",
  NEXT_ACTIONS: "다음 실행 항목",
};

export const REFINE_DIRECTION_OPTIONS: {
  direction: IdeaRefineDirection;
  label: string;
}[] = (Object.keys(REFINE_DIRECTION_LABELS) as IdeaRefineDirection[]).map(
  (direction) => ({ direction, label: REFINE_DIRECTION_LABELS[direction] }),
);

export function refineDirectionLabel(
  direction: IdeaRefineDirection | null | undefined,
): string | null {
  if (!direction) return null;
  return REFINE_DIRECTION_LABELS[direction] ?? direction;
}

export const REFINE_STEPPER_STEPS = [
  "발전 방향 선택",
  "AI 분석",
  "발전안 검토",
  "반영 완료",
];

export function refineStepperIndex(status: AiSessionStatus | undefined): number {
  switch (status) {
    case "READY_FOR_REVIEW":
      return 2;
    case "CONFIRMED":
      return 3;
    default:
      return 1;
  }
}
