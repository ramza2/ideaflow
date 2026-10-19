"""ModelOps P1-12 prompt token budgeting primitives."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True, slots=True)
class PhaseBudgetPolicy:
    name: str
    output_ratio: float
    min_output_tokens: int


STRUCTURE_POLICY = PhaseBudgetPolicy("STRUCTURE_IDEA", 0.30, 640)
WEB_RESEARCH_POLICY = PhaseBudgetPolicy("WEB_RESEARCH_REFINE", 0.15, 384)
REFINE_POLICY = PhaseBudgetPolicy("REFINE_IDEA", 0.20, 512)


@dataclass(frozen=True, slots=True)
class VerifiedTokenCount:
    prompt_tokens: int
    context_window: int
    deployment_id: str
    route_id: str
    routing_version: int


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    prompt_tokens: int
    context_window: int
    safety_margin_tokens: int
    desired_output_tokens: int
    min_output_tokens: int
    max_tokens: int
    needs_input_shrink: bool
    fits_minimum: bool


def compute_phase_budget(
    *,
    prompt_tokens: int,
    context_window: int,
    hard_output_cap: int,
    policy: PhaseBudgetPolicy,
    thinking_enabled: bool,
) -> BudgetDecision:
    """Compute an output reservation using verified token counts only.

    The hard cap is the existing IdeaFlow per-phase max_tokens. Ratios are
    context-relative and never imply a guessed context window. Thinking keeps
    the same output cap but reserves a larger non-output safety margin because
    reasoning tokens consume the completion budget.
    """
    if prompt_tokens < 0:
        raise ValueError("prompt_tokens must be >= 0")
    if context_window < 1:
        raise ValueError("context_window must be >= 1")
    if hard_output_cap < 1:
        raise ValueError("hard_output_cap must be >= 1")
    if not 0 < policy.output_ratio <= 1:
        raise ValueError("output_ratio must be within (0, 1]")

    min_output = min(hard_output_cap, policy.min_output_tokens)
    ratio_target = max(min_output, int(context_window * policy.output_ratio))
    desired_output = min(hard_output_cap, ratio_target)

    safety_ratio = 0.05 + (0.03 if thinking_enabled else 0.0)
    safety_margin = max(64, ceil(context_window * safety_ratio))
    remaining = context_window - prompt_tokens - safety_margin
    max_tokens = max(0, min(desired_output, remaining))

    return BudgetDecision(
        prompt_tokens=prompt_tokens,
        context_window=context_window,
        safety_margin_tokens=safety_margin,
        desired_output_tokens=desired_output,
        min_output_tokens=min_output,
        max_tokens=max_tokens,
        needs_input_shrink=max_tokens < desired_output,
        fits_minimum=max_tokens >= min_output,
    )
