"""Topic-aware embedding provider for offline ranking evaluation only."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable

from app.core.config import Settings

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "meeting": ("회의록", "회의", "미팅", "회의 내용", "회의 자동", "회의 정리", "미팅 노트"),
    "medical_write": (
        "진료 기록",
        "의료 문서",
        "병원 기록",
        "의무기록 작성",
        "환자 기록 작성",
        "환자 기록 자동",
        "의사가 반복",
        "진료",
        "병원 업무",
    ),
    "medical_search": ("환자 기록 검색", "의무기록 검색", "차트 검색", "환자 검색", "기록 검색"),
    "inventory": ("재고", "재고 부족", "발주", "재고가 떨어", "재고 알림", "입고", "출고"),
    "ocr": ("OCR", "문자 인식", "문서 스캔", "스캔 문서", "이미지 텍스트"),
    "automation": ("자동화", "업무 자동화", "내부 업무", "업무 효율", "반복 업무", "효율화"),
    "ai_doc": ("AI 문서", "문서 처리", "LLM", "문서 요약", "문서 분류"),
    "crm": ("CRM", "고객 관리", "영업 파이프라인", "리드"),
    "hr": ("인사", "채용", "온보딩", "휴가", "HR"),
    "logistics": ("물류", "배송", "운송", "창고", "라스트마일"),
    "finance": ("회계", "정산", "세금", "청구서", "경비"),
    "education": ("교육", "학습", "강의", "퀴즈", "커리큘럼"),
    "retail": ("매장", "리테일", "포스", "고객 동선", "프로모션"),
    "generic": ("플랫폼", "서비스", "시스템", "앱"),
}

_CODE_RE = re.compile(r"\[(SR-[A-Z0-9-]+)\]")


def _l2_normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def _topic_centroid(topic: str, dimension: int, topic_index: int) -> list[float]:
    values = [0.0] * dimension
    primary = topic_index % max(dimension // 2, 1)
    values[primary] = 1.0
    digest = hashlib.sha256(f"topic:{topic}".encode()).digest()
    for i in range(8):
        idx = (primary + 3 + i * 7) % dimension
        values[idx] += 0.05 * ((digest[i % len(digest)] / 255.0) * 2 - 1)
    return _l2_normalize(values)


def _noise_vector(text: str, dimension: int, scale: float = 0.08) -> list[float]:
    digest = hashlib.sha256(f"noise:{text}".encode()).digest()
    values: list[float] = []
    idx = 0
    while len(values) < dimension:
        chunk = digest[idx % len(digest) : (idx % len(digest)) + 4]
        if len(chunk) < 4:
            digest = hashlib.sha256(digest).digest()
            idx = 0
            continue
        raw = int.from_bytes(chunk.ljust(4, b"\x00")[:4], "big")
        values.append(((raw / 2**32) * 2 - 1) * scale)
        idx += 4
    return values


def detect_topic_weights(text: str) -> dict[str, float]:
    lowered = text.casefold()
    weights: dict[str, float] = {}
    for topic, phrases in TOPIC_KEYWORDS.items():
        score = 0.0
        for phrase in phrases:
            if phrase.casefold() in lowered:
                score += 1.0 + 0.15 * max(len(phrase) - 2, 0)
        if score:
            weights[topic] = score
    if not weights:
        weights["generic"] = 1.0
    return weights


def text_to_topic_vector(text: str, *, dimension: int) -> list[float]:
    weights = detect_topic_weights(text)
    topics = list(TOPIC_KEYWORDS.keys())
    mixed = [0.0] * dimension
    total_w = sum(weights.values()) or 1.0
    for topic, weight in weights.items():
        idx = topics.index(topic) if topic in topics else 0
        centroid = _topic_centroid(topic, dimension, idx)
        scale = weight / total_w
        for i, v in enumerate(centroid):
            mixed[i] += v * scale
    for i, v in enumerate(_noise_vector(text, dimension)):
        mixed[i] += v
    return _l2_normalize(mixed)


class TopicAwareEvalEmbeddingProvider:
    """Eval-only provider: topic centroids + light text noise."""

    provider_name = "topic_eval"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.model_name = settings.embedding_model_name

    def close(self) -> None:
        return None

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        dim = self._settings.embedding_dimension
        return [text_to_topic_vector(t, dimension=dim) for t in texts]


def extract_idea_code(title: str) -> str | None:
    match = _CODE_RE.search(title or "")
    return match.group(1) if match else None


def codes_from_titles(titles: Iterable[str]) -> list[str]:
    out: list[str] = []
    for title in titles:
        code = extract_idea_code(title)
        if code:
            out.append(code)
    return out
