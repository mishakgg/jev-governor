"""Deterministic baseline policy (det-1): recipes, gates, suppression.

The policy selects one recipe ID plus structured rationale. It never returns
executable commands, never widens permissions, and never bypasses an exhausted
budget or an explicit pause. Execution (if any) is a separate gated step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

POLICY_VERSION = "det-1"

RECIPES = ("CONTINUE", "ECONOMICAL_CONTINUE", "ESCALATE_DIAGNOSIS", "VERIFY_NOW", "PAUSE_REPLAN")


@dataclass
class PolicyContext:
    permitted: list[str] = field(default_factory=lambda: list(RECIPES))
    budget: dict[str, Any] = field(default_factory=dict)
    economical_available: str | None = None  # configured cheaper target, else None
    diagnostics_remaining: bool = True
    last_selected: str | None = None
    last_codes: list[str] = field(default_factory=list)
    new_events_since_last: bool = True
    advisory: bool = True


@dataclass
class Decision:
    selected: str | None
    rationale_codes: list[str]
    evidence_refs: list[str]
    uncertainty: float  # 0 (confident) .. 1 (maximal)
    abstained: bool = False
    suppressed: bool = False
    advisory: bool = True
    intended_config: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


def _budget_fraction(features: dict[str, Any], budget: dict[str, Any]) -> float | None:
    max_total = budget.get("max_total_tokens")
    if not isinstance(max_total, int | float) or max_total <= 0:
        return None
    used = (features.get("total_input_tokens", 0) or 0) + (
        features.get("total_output_tokens", 0) or 0
    )
    return used / max_total


def decide(
    features: dict[str, Any],
    ctx: PolicyContext,
    evidence_refs: list[str] | None = None,
) -> Decision:
    refs = list(evidence_refs or [])
    permitted = [r for r in ctx.permitted if r in RECIPES] or list(RECIPES)

    def pick(
        recipe: str | None,
        codes: list[str],
        uncertainty: float,
        reason: str,
        abstained: bool = False,
        intended: dict[str, Any] | None = None,
    ) -> Decision:
        selected = recipe
        final_codes = list(codes)
        if recipe is not None and recipe not in permitted:
            # Unsupported-action fallback: degrade to an allowed recipe.
            selected = "PAUSE_REPLAN" if "PAUSE_REPLAN" in permitted else permitted[0]
            final_codes = ["unsupported-action-fallback", *codes]
            uncertainty = max(uncertainty, 0.6)
        suppressed = (
            selected is not None
            and selected == ctx.last_selected
            and final_codes == ctx.last_codes
            and not ctx.new_events_since_last
        )
        return Decision(
            selected=selected,
            rationale_codes=final_codes,
            evidence_refs=refs,
            uncertainty=round(min(max(uncertainty, 0.0), 1.0), 3),
            abstained=abstained,
            suppressed=suppressed,
            advisory=ctx.advisory,
            intended_config=intended or {},
            reason=reason,
        )

    # 1. Budget gate: an exhausted budget is unresolved, never success, and no
    #    fallback (including Jev) may bypass it.
    fraction = _budget_fraction(features, ctx.budget)
    if fraction is not None and fraction >= 1.0:
        return pick(
            "PAUSE_REPLAN",
            ["budget-exhausted"],
            0.1,
            "Observed usage reached the configured budget. Preserve state and "
            "replan; this outcome is unresolved, not success.",
        )

    loop = (
        (features.get("same_assert_after_distinct_patches", 0) or 0) >= 2
        and (features.get("new_diagnostics_since_last_patch", 0) or 0) == 0
        and not features.get("hypothesis_changed", False)
    )
    jev_pattern = features.get("jev_failure_pattern")
    if jev_pattern == "possible_repeated_attempt":
        loop = loop or (
            (features.get("same_assert_after_distinct_patches", 0) or 0) >= 1
            and (features.get("new_diagnostics_since_last_patch", 0) or 0) == 0
        )

    # 2. Repeated-failure loop.
    if loop and (features.get("n_failed_now", 0) or 0) > 0:
        if ctx.diagnostics_remaining and "ESCALATE_DIAGNOSIS" in permitted:
            return pick(
                "ESCALATE_DIAGNOSIS",
                ["repeated-failure-loop", "no-new-diagnostics"],
                0.3,
                "The same check failed after distinct patches with no new "
                "diagnostic evidence. Run one focused approved diagnostic "
                "instead of repeating the patch.",
            )
        return pick(
            "PAUSE_REPLAN",
            ["repeated-failure-loop", "diagnostics-exhausted"],
            0.35,
            "The same check keeps failing after distinct patches and no "
            "further diagnostics are available. Preserve the patch and replan.",
        )

    # 3. Failed checks with fresh diagnostics available -> verify the fix path.
    if (features.get("n_failed_now", 0) or 0) > 0 and (
        features.get("new_diagnostics_since_last_patch", 0) or 0
    ) > 0:
        return pick(
            "VERIFY_NOW",
            ["failed-checks", "new-diagnostics-available"],
            0.3,
            "Failures are recorded but new diagnostic evidence exists. Run the "
            "registered check to confirm the current state before more edits.",
        )

    # 4. Stale evidence: earlier passes were invalidated by a later patch and
    #    nothing fresh confirms the current state.
    if (
        (features.get("n_remaining", 0) or 0) > 0
        and (features.get("n_stale_checks", 0) or 0) > 0
        and (features.get("n_fresh_pass_checks", 0) or 0) == 0
        and (features.get("n_failed_now", 0) or 0) == 0
    ):
        return pick(
            "VERIFY_NOW",
            ["evidence-stale", "no-fresh-confirmation"],
            0.3,
            "Prior checks passed but a later patch changed the evaluated "
            "state, so that evidence is stale. Re-run the registered check "
            "against the current patch.",
        )

    # 5. Productive expensive investigation: high spend with new evidence or a
    #    changed hypothesis is progress, not waste. Never auto-pause for cost.
    expensive = (features.get("total_input_tokens", 0) or 0) + (
        features.get("total_output_tokens", 0) or 0
    )
    productive = (
        features.get("hypothesis_changed", False)
        or (features.get("new_diagnostics_since_last_patch", 0) or 0) > 0
        or jev_pattern == "meaningful_investigation"
    )
    if expensive >= 20_000 and productive and (features.get("n_failed_now", 0) or 0) == 0:
        return pick(
            "CONTINUE",
            ["productive-investigation", "high-spend-with-new-evidence"],
            0.4,
            "Spend is high but new diagnostics or a changed hypothesis show "
            "movement. Continue the current configuration for one more "
            "bounded segment.",
        )

    # 6. Failed checks with no other signal -> diagnose before verifying.
    if (features.get("n_failed_now", 0) or 0) > 0:
        if ctx.diagnostics_remaining:
            return pick(
                "ESCALATE_DIAGNOSIS",
                ["failed-checks", "diagnose-first"],
                0.45,
                "Checks fail without a clear cause. Gather one focused "
                "diagnostic before the next patch.",
            )
        return pick(
            "VERIFY_NOW",
            ["failed-checks", "confirm-state"],
            0.5,
            "Checks fail. Re-run the registered check to confirm the current "
            "state on the latest patch.",
        )

    # 7. Remaining work, steady state -> economical if configured, else continue.
    if (features.get("n_remaining", 0) or 0) > 0:
        if ctx.economical_available and "ECONOMICAL_CONTINUE" in permitted:
            return pick(
                "ECONOMICAL_CONTINUE",
                ["steady-progress", "cheaper-config-available"],
                0.4,
                "Progress is steady with no failure signal. An approved "
                "cheaper configuration is available for the next segment.",
                intended={"target": ctx.economical_available},
            )
        return pick(
            "CONTINUE",
            ["steady-progress"],
            0.4,
            "No failure or budget signal. Continue the current configuration "
            "for the next bounded segment.",
        )

    # 8. Nothing remaining and nothing failed: confirm terminal state by check.
    if not features.get("n_requirements"):
        return pick(
            None,
            ["insufficient-evidence"],
            0.9,
            "No requirements are recorded, so no recommendation is warranted. "
            "Record explicit requirements first.",
            abstained=True,
        )
    return pick(
        "VERIFY_NOW",
        ["all-covered-confirm-terminal"],
        0.35,
        "All requirements appear covered. Run the registered acceptance "
        "checks to confirm the terminal state.",
    )
