"""Pure tests for ModelOps P1-12 adaptive token budgeting."""

from app.llm.adaptive_budget import (
    REFINE_POLICY,
    STRUCTURE_POLICY,
    WEB_RESEARCH_POLICY,
    compute_phase_budget,
)


def test_phase_ratios_respect_existing_hard_caps() -> None:
    cases = [
        (STRUCTURE_POLICY, 2500, 2500),
        (WEB_RESEARCH_POLICY, 1200, 1200),
        (REFINE_POLICY, 1600, 1600),
    ]
    for policy, hard_cap, expected in cases:
        decision = compute_phase_budget(
            prompt_tokens=1000,
            context_window=100000,
            hard_output_cap=hard_cap,
            policy=policy,
            thinking_enabled=False,
        )
        assert decision.max_tokens == expected
        assert decision.desired_output_tokens == expected


def test_dynamic_budget_never_exceeds_verified_context() -> None:
    decision = compute_phase_budget(
        prompt_tokens=3200,
        context_window=5000,
        hard_output_cap=2500,
        policy=STRUCTURE_POLICY,
        thinking_enabled=False,
    )
    assert (
        decision.prompt_tokens
        + decision.max_tokens
        + decision.safety_margin_tokens
        <= decision.context_window
    )
    assert decision.needs_input_shrink is True


def test_budget_marks_prompt_that_cannot_preserve_minimum_json_output() -> None:
    decision = compute_phase_budget(
        prompt_tokens=4500,
        context_window=5000,
        hard_output_cap=1200,
        policy=WEB_RESEARCH_POLICY,
        thinking_enabled=False,
    )
    assert decision.fits_minimum is False
    assert decision.max_tokens < decision.min_output_tokens


def test_thinking_reserves_more_safety_without_changing_hard_cap() -> None:
    off = compute_phase_budget(
        prompt_tokens=1000,
        context_window=8192,
        hard_output_cap=1600,
        policy=REFINE_POLICY,
        thinking_enabled=False,
    )
    on = compute_phase_budget(
        prompt_tokens=1000,
        context_window=8192,
        hard_output_cap=1600,
        policy=REFINE_POLICY,
        thinking_enabled=True,
    )
    assert on.safety_margin_tokens > off.safety_margin_tokens
    assert on.desired_output_tokens == off.desired_output_tokens == 1600
