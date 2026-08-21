export interface HelpBlock {
  type: "paragraph" | "heading" | "tip" | "warning" | "steps" | "source-legend";
  text?: string;
  items?: string[];
}

export interface HelpArticle {
  id: string;
  categoryId: string;
  title: string;
  summary: string;
  blocks: HelpBlock[];
}

export interface HelpCategory {
  id: string;
  label: string;
  articleIds: string[];
}

export interface FAQItem {
  id: string;
  question: string;
  answer: string;
}

export const HELP_CATEGORIES: HelpCategory[] = [
  {
    id: "getting-started",
    label: "시작하기",
    articleIds: ["ideaflow-intro", "first-idea", "ai-register", "manual-register"],
  },
  {
    id: "idea-management",
    label: "아이디어 관리",
    articleIds: ["idea-stages", "fields-tags", "visibility", "assignee", "reviews"],
  },
  {
    id: "collaboration",
    label: "작업공간 및 협업",
    articleIds: ["workspaces", "invite-members", "user-roles", "comments"],
  },
  {
    id: "ai-features",
    label: "AI 기능",
    articleIds: ["ai-structuring", "ai-draft-review", "web-search", "similar-ideas", "ai-develop"],
  },
  {
    id: "faq",
    label: "FAQ",
    articleIds: ["faq"],
  },
];

export const HELP_ARTICLES: HelpArticle[] = [
  {
    id: "ideaflow-intro",
    categoryId: "getting-started",
    title: "IdeaFlow 소개",
    summary: "IdeaFlow는 팀이 아이디어를 수집, 정리, 검토, 실행하는 전체 과정을 한 곳에서 관리할 수 있는 아이디어 관리 도구입니다.",
    blocks: [
      {
        type: "paragraph",
        text: "IdeaFlow는 팀의 아이디어를 수집하고 정리하는 것부터 검토, 실행까지 전 과정을 한 곳에서 관리할 수 있도록 설계된 아이디어 관리 플랫폼입니다.",
      },
      { type: "heading", text: "핵심 기능" },
      {
        type: "steps",
        items: [
          "자연어로 아이디어 입력 후 AI가 구조화된 항목으로 정리",
          "아이디어를 단계별로 관리 (초안 → 검토 → 검증 → 실행)",
          "팀원과 아이디어를 공유하고 댓글로 피드백",
          "검토함에서 검토 일정 집중 관리",
        ],
      },
      {
        type: "tip",
        text: "AI 기능 없이도 직접 아이디어를 등록하고 관리할 수 있습니다. AI는 선택적으로 사용합니다.",
      },
    ],
  },
  {
    id: "first-idea",
    categoryId: "getting-started",
    title: "첫 아이디어 등록하기",
    summary: "홈 화면의 입력창이나 새 아이디어 버튼을 통해 첫 번째 아이디어를 등록해 보세요.",
    blocks: [
      {
        type: "paragraph",
        text: "IdeaFlow에 첫 아이디어를 등록하는 방법은 두 가지입니다. AI에게 자연어로 전달하거나, 직접 항목을 작성하는 방식 중 선택할 수 있습니다.",
      },
      { type: "heading", text: "AI로 등록하기" },
      {
        type: "steps",
        items: [
          "홈 화면의 텍스트 입력창에 아이디어를 자유롭게 적습니다.",
          "'AI로 정리하기' 버튼을 클릭합니다.",
          "AI가 분석 후 구조화된 초안을 제시합니다.",
          "내용을 확인하고 수정한 뒤 등록합니다.",
        ],
      },
      { type: "heading", text: "직접 등록하기" },
      {
        type: "steps",
        items: [
          "상단 또는 홈의 '직접 등록' 버튼을 클릭합니다.",
          "아이디어 제목, 한 줄 설명, 배경 등을 입력합니다.",
          "'저장' 버튼으로 등록합니다.",
        ],
      },
      {
        type: "tip",
        text: "완성된 문장이 아니어도 됩니다. AI는 키워드 나열이나 단편적인 생각도 구조화할 수 있습니다.",
      },
    ],
  },
  {
    id: "ai-register",
    categoryId: "getting-started",
    title: "AI로 아이디어 등록하기",
    summary: "자연어로 아이디어를 입력하면 AI가 구조화된 항목으로 정리해 드립니다.",
    blocks: [
      {
        type: "paragraph",
        text: "AI 등록 기능은 자유로운 형식의 텍스트를 IdeaFlow의 표준 항목으로 자동 변환합니다. 완성된 문장이 아니어도 됩니다.",
      },
      { type: "heading", text: "진행 흐름" },
      {
        type: "steps",
        items: [
          "아이디어 내용을 자유롭게 입력합니다.",
          "분석 옵션을 선택합니다 (웹 검색 포함 여부, 유사 아이디어 확인 등).",
          "AI가 6단계로 분석을 진행합니다.",
          "외부 정보가 필요한 경우 웹 검색 승인 창이 표시됩니다.",
          "분석 완료 후 초안을 확인하고 수정합니다.",
          "최종 등록합니다.",
        ],
      },
      { type: "source-legend" },
      {
        type: "tip",
        text: "AI 초안의 각 항목에는 정보 출처가 표시됩니다. '확인 필요' 표시가 있는 항목은 내용을 직접 검토하세요.",
      },
    ],
  },
  {
    id: "manual-register",
    categoryId: "getting-started",
    title: "직접 아이디어 등록하기",
    summary: "정해진 항목에 직접 내용을 입력하여 아이디어를 등록합니다.",
    blocks: [
      {
        type: "paragraph",
        text: "직접 등록은 이미 정리된 아이디어를 빠르게 입력하거나, AI 없이 아이디어를 작성하고 싶을 때 사용합니다.",
      },
      { type: "heading", text: "주요 입력 항목" },
      {
        type: "steps",
        items: [
          "아이디어명 (필수)",
          "한 줄 정의",
          "배경과 문제 정의",
          "핵심 개념",
          "분야 및 태그",
          "우선순위, 공개 범위",
          "담당자",
        ],
      },
      {
        type: "tip",
        text: "모든 항목을 채우지 않아도 저장할 수 있습니다. 나중에 이어서 작성하거나 AI에게 보완을 요청할 수 있습니다.",
      },
    ],
  },
  {
    id: "idea-stages",
    categoryId: "idea-management",
    title: "아이디어 단계 이해하기",
    summary: "IdeaFlow에서 아이디어는 초안부터 실행까지 6단계로 관리됩니다.",
    blocks: [
      {
        type: "paragraph",
        text: "아이디어는 다음 단계로 관리됩니다. 단계는 수동으로 변경하거나 검토 완료 시 이동할 수 있습니다.",
      },
      {
        type: "steps",
        items: [
          "초안 — 작성 중이거나 아직 검토되지 않은 상태",
          "검토 중 — 검토자에게 배정되어 검토 진행 중",
          "검증 후보 — 검토 완료, 실행 가치 있음으로 평가됨",
          "실행 중 — 실제 개발 또는 실행이 시작된 상태",
          "보류 — 일시적으로 진행을 멈춘 상태",
          "보관 — 더 이상 진행하지 않는 아이디어",
        ],
      },
      {
        type: "tip",
        text: "보관 상태의 아이디어는 목록에서 기본적으로 숨겨집니다. 필터에서 '보관' 단계를 선택하면 볼 수 있습니다.",
      },
    ],
  },
  {
    id: "fields-tags",
    categoryId: "idea-management",
    title: "분야와 태그",
    summary: "분야는 아이디어의 큰 범주를, 태그는 더 세부적인 키워드를 나타냅니다.",
    blocks: [
      {
        type: "paragraph",
        text: "분야와 태그를 활용하면 아이디어를 체계적으로 분류하고 빠르게 검색할 수 있습니다.",
      },
      { type: "heading", text: "분야" },
      {
        type: "paragraph",
        text: "각 아이디어에 하나의 대표 분야를 지정합니다. 예: 기술/AI, 프로세스 개선, 마케팅, 제품, 연구 등.",
      },
      { type: "heading", text: "태그" },
      {
        type: "paragraph",
        text: "아이디어에 여러 태그를 추가할 수 있습니다. 팀 내에서 일관된 태그를 사용하면 관련 아이디어를 쉽게 묶어볼 수 있습니다.",
      },
      {
        type: "tip",
        text: "AI로 등록 시 분야와 태그를 자동으로 제안합니다. 그대로 사용하거나 수정할 수 있습니다.",
      },
    ],
  },
  {
    id: "visibility",
    categoryId: "idea-management",
    title: "공개 범위",
    summary: "아이디어를 나만 볼 것인지, 팀원과 공유할 것인지 설정합니다.",
    blocks: [
      {
        type: "paragraph",
        text: "아이디어의 공개 범위를 설정하여 접근 권한을 관리할 수 있습니다.",
      },
      {
        type: "steps",
        items: [
          "비공개 — 작성자 본인만 볼 수 있습니다.",
          "작업공간 공유 — 같은 작업공간의 모든 구성원이 볼 수 있습니다.",
          "지정 사용자 공유 — 특정 구성원에게만 접근 권한을 부여합니다.",
        ],
      },
      {
        type: "tip",
        text: "아이디어 등록 후에도 언제든지 공개 범위를 변경할 수 있습니다.",
      },
    ],
  },
  {
    id: "assignee",
    categoryId: "idea-management",
    title: "담당자와 참여자",
    summary: "담당자는 아이디어를 책임지는 구성원이고, 참여자는 협력하는 구성원입니다.",
    blocks: [
      {
        type: "paragraph",
        text: "아이디어에는 담당자와 참여자를 지정할 수 있습니다.",
      },
      { type: "heading", text: "담당자" },
      {
        type: "paragraph",
        text: "아이디어의 진행을 책임지는 구성원입니다. 담당자는 검토함에서 해당 아이디어를 확인할 수 있습니다.",
      },
      { type: "heading", text: "참여자" },
      {
        type: "paragraph",
        text: "아이디어에 함께 참여하는 구성원입니다. 댓글 알림을 받고 협업할 수 있습니다.",
      },
    ],
  },
  {
    id: "reviews",
    categoryId: "idea-management",
    title: "검토함 사용하기",
    summary: "검토가 필요한 아이디어를 한 곳에서 확인하고 처리합니다.",
    blocks: [
      {
        type: "paragraph",
        text: "검토함은 사용자가 검토해야 하는 아이디어를 유형별로 모아 보여줍니다.",
      },
      { type: "heading", text: "검토 탭 유형" },
      {
        type: "steps",
        items: [
          "검토 예정 — 검토일이 다가오는 아이디어",
          "검토일 경과 — 검토일이 지났지만 미처리된 아이디어",
          "내용 보완 필요 — 추가 정보가 필요한 아이디어",
          "다음 단계 후보 — 단계 이동이 권장되는 아이디어",
          "내가 담당 — 담당자로 지정된 아이디어",
          "나를 언급 — 댓글에서 멘션된 아이디어",
        ],
      },
      {
        type: "tip",
        text: "검토 완료 버튼을 클릭하면 검토 메모, 다음 단계, 다음 검토일을 기록하고 처리할 수 있습니다.",
      },
    ],
  },
  {
    id: "workspaces",
    categoryId: "collaboration",
    title: "개인 작업공간과 팀 작업공간",
    summary: "개인 작업공간은 혼자 사용하고, 팀 작업공간은 구성원들이 함께 아이디어를 관리합니다.",
    blocks: [
      {
        type: "paragraph",
        text: "IdeaFlow는 개인과 팀 단위로 분리된 작업공간을 제공합니다.",
      },
      { type: "heading", text: "개인 작업공간" },
      {
        type: "paragraph",
        text: "본인 중심으로 아이디어를 관리합니다. 비공개 아이디어를 보관하거나 혼자 발전시킬 때 활용합니다.",
      },
      { type: "heading", text: "팀 작업공간" },
      {
        type: "paragraph",
        text: "여러 구성원이 아이디어를 공유하고 함께 검토합니다. 구성원 초대, 역할 관리, 검토함 공유 등 협업 기능을 사용할 수 있습니다.",
      },
    ],
  },
  {
    id: "invite-members",
    categoryId: "collaboration",
    title: "구성원 초대",
    summary: "이메일 주소로 팀 구성원을 초대합니다.",
    blocks: [
      {
        type: "paragraph",
        text: "설정 > 구성원 메뉴에서 팀원을 초대할 수 있습니다.",
      },
      {
        type: "steps",
        items: [
          "사이드바에서 '작업공간' 메뉴를 클릭합니다.",
          "'구성원 초대' 버튼을 클릭합니다.",
          "초대할 구성원의 이메일 주소를 입력합니다 (여러 명은 쉼표로 구분).",
          "역할을 선택합니다.",
          "'초대 보내기'를 클릭합니다.",
        ],
      },
      {
        type: "tip",
        text: "초대받은 구성원은 이메일로 초대 링크를 받으며, 수락 후 작업공간에 참여합니다.",
      },
    ],
  },
  {
    id: "user-roles",
    categoryId: "collaboration",
    title: "사용자 역할",
    summary: "작업공간 내 구성원은 관리자, 일반 구성원, 읽기 전용 중 하나의 역할을 가집니다.",
    blocks: [
      {
        type: "steps",
        items: [
          "작업공간 관리자 — 구성원 초대, 역할 변경, 설정 관리 가능",
          "일반 구성원 — 아이디어 등록, 수정, 검토, 댓글 가능",
          "읽기 전용 — 아이디어 조회와 댓글 가능",
        ],
      },
      {
        type: "warning",
        text: "작업공간 관리자는 시스템 설정(LLM, 웹 검색 등)에는 접근할 수 없습니다. 시스템 관리는 별도 시스템 관리자만 가능합니다.",
      },
    ],
  },
  {
    id: "comments",
    categoryId: "collaboration",
    title: "댓글과 검토 메모",
    summary: "댓글로 아이디어에 대한 의견을 남기고, 검토 메모로 공식 검토 내용을 기록합니다.",
    blocks: [
      { type: "heading", text: "댓글" },
      {
        type: "paragraph",
        text: "아이디어 상세 페이지의 '댓글' 탭에서 팀원과 의견을 주고받을 수 있습니다. @멘션으로 특정 구성원에게 알림을 보낼 수 있습니다.",
      },
      { type: "heading", text: "검토 메모" },
      {
        type: "paragraph",
        text: "검토함에서 '검토 완료'를 클릭하면 검토 결과와 메모를 기록할 수 있습니다. 검토 메모는 이력으로 저장됩니다.",
      },
    ],
  },
  {
    id: "ai-structuring",
    categoryId: "ai-features",
    title: "자연어 아이디어 구조화",
    summary: "자유롭게 작성된 아이디어를 AI가 IdeaFlow의 표준 항목으로 자동 정리합니다.",
    blocks: [
      {
        type: "paragraph",
        text: "AI 구조화는 사용자의 자연어 입력을 IdeaFlow 아이디어 항목(제목, 문제, 핵심 개념, 기대 효과 등)으로 변환합니다.",
      },
      { type: "source-legend" },
      {
        type: "tip",
        text: "AI가 생성한 각 항목에는 출처가 표시됩니다. 출처를 확인하면 어떤 내용이 AI의 추론인지 파악할 수 있습니다.",
      },
    ],
  },
  {
    id: "ai-draft-review",
    categoryId: "ai-features",
    title: "AI 초안 검토",
    summary: "AI가 생성한 등록 초안을 항목별로 확인하고 수정한 뒤 최종 등록합니다.",
    blocks: [
      {
        type: "paragraph",
        text: "AI 분석이 완료되면 초안 검토 화면에서 내용을 확인할 수 있습니다.",
      },
      { type: "heading", text: "초안 검토 화면 구성" },
      {
        type: "steps",
        items: [
          "왼쪽: 사용자가 입력한 원문",
          "가운데: AI가 정리한 항목별 초안",
          "오른쪽: 웹 검색 결과 근거 (웹 검색을 사용한 경우)",
        ],
      },
      {
        type: "tip",
        text: "'확인 필요' 표시가 있는 항목은 AI가 정보 부족으로 정확성을 보장하지 못합니다. 반드시 직접 확인하세요.",
      },
      {
        type: "warning",
        text: "AI가 생성한 초안은 자동으로 저장되지 않습니다. 최종 등록 버튼을 클릭해야 아이디어가 등록됩니다.",
      },
    ],
  },
  {
    id: "web-search",
    categoryId: "ai-features",
    title: "웹 검색으로 정보 보완",
    summary: "AI 분석 중 외부 정보가 필요한 경우 웹 검색을 실행하여 근거를 보강합니다.",
    blocks: [
      {
        type: "paragraph",
        text: "AI는 분석 중 외부 정보가 도움이 된다고 판단하면 웹 검색 승인을 요청합니다.",
      },
      { type: "heading", text: "웹 검색 흐름" },
      {
        type: "steps",
        items: [
          "AI가 검색이 필요한 항목과 이유를 표시합니다.",
          "검색 대상(유사 서비스, 기술 사례, 법률, 시장 현황)을 선택합니다.",
          "외부에 전달되는 검색어를 확인하고 수정할 수 있습니다.",
          "'검색 실행'을 클릭하면 웹 검색이 진행됩니다.",
        ],
      },
      {
        type: "warning",
        text: "웹 검색을 실행하면 아이디어 관련 정보가 외부 검색 서비스에 전달됩니다. 민감한 정보는 마스킹되며, 전송 전 내용을 확인할 수 있습니다.",
      },
    ],
  },
  {
    id: "similar-ideas",
    categoryId: "ai-features",
    title: "유사 아이디어 찾기",
    summary: "AI가 새 아이디어와 기존 등록된 아이디어의 유사성을 분석하여 중복을 방지합니다.",
    blocks: [
      {
        type: "paragraph",
        text: "AI는 분석 과정에서 기존 아이디어와의 유사성을 검토합니다. 유사 아이디어가 발견되면 초안 검토 화면에서 알려줍니다.",
      },
      { type: "heading", text: "유사 아이디어 발견 시 선택지" },
      {
        type: "steps",
        items: [
          "별도 아이디어로 등록 — 두 아이디어가 별개라고 판단될 때",
          "기존 아이디어에 추가 — 기존 아이디어에 내용을 합칠 때",
          "두 아이디어 연결 — 관련 아이디어로 연결만 할 때",
          "등록 취소 — 완전한 중복으로 등록하지 않을 때",
        ],
      },
    ],
  },
  {
    id: "ai-develop",
    categoryId: "ai-features",
    title: "AI로 아이디어 발전시키기",
    summary: "등록된 아이디어를 AI와 함께 더 구체적으로 발전시킬 수 있습니다.",
    blocks: [
      {
        type: "paragraph",
        text: "아이디어 상세 페이지에서 AI 패널을 통해 등록된 아이디어를 보완하거나 발전시킬 수 있습니다.",
      },
      {
        type: "steps",
        items: [
          "아이디어 상세 페이지를 열고 오른쪽 AI 패널을 엽니다.",
          "원하는 분석 유형을 선택합니다 (검증 방법 제안, 반대 관점 검토 등).",
          "AI 제안 내용을 검토하고 아이디어에 반영할 부분을 수정합니다.",
        ],
      },
      {
        type: "tip",
        text: "AI 제안은 참고용입니다. 최종 내용은 항상 사용자가 직접 확인하고 수정합니다.",
      },
    ],
  },
];

export const FAQ_ITEMS: FAQItem[] = [
  {
    id: "faq-1",
    question: "AI가 생성한 내용은 자동으로 저장되나요?",
    answer: "아니요. AI가 생성한 초안을 사용자가 검토하고 수정한 뒤 최종 등록해야 저장됩니다.",
  },
  {
    id: "faq-2",
    question: "AI로 등록하지 않고 직접 입력할 수 있나요?",
    answer: "가능합니다. 새 아이디어 메뉴에서 직접 등록을 선택할 수 있으며, 모든 항목을 직접 입력할 수 있습니다.",
  },
  {
    id: "faq-3",
    question: "웹 검색을 항상 실행하나요?",
    answer: "아닙니다. 사용자가 웹 검색을 선택하거나 AI의 웹 검색 요청을 승인한 경우에만 실행합니다.",
  },
  {
    id: "faq-4",
    question: "웹 검색 시 아이디어 원문 전체가 검색 서비스에 전달되나요?",
    answer: "민감정보를 확인하고 가능한 경우 일반화된 검색어를 사용하도록 설계되어 있습니다. 전송 전 전달 내용을 확인하고 수정할 수 있습니다.",
  },
  {
    id: "faq-5",
    question: "비공개 아이디어는 누가 볼 수 있나요?",
    answer: "기본적으로 작성자 본인만 볼 수 있으며, 공개 범위 설정에 따라 특정 구성원 또는 작업공간 전체와 공유할 수 있습니다.",
  },
  {
    id: "faq-6",
    question: "LLM 서버에 문제가 생기면 아이디어를 등록할 수 없나요?",
    answer: "AI 기능을 사용할 수 없더라도 직접 등록과 기존 아이디어 조회·수정은 정상적으로 사용할 수 있습니다.",
  },
  {
    id: "faq-7",
    question: "개인 작업공간과 팀 작업공간의 차이는 무엇인가요?",
    answer: "개인 작업공간은 본인 중심으로 사용하며, 팀 작업공간은 여러 사용자가 아이디어를 공유하고 검토합니다. 팀 작업공간에서는 구성원 초대, 역할 관리 등 협업 기능을 사용할 수 있습니다.",
  },
];
