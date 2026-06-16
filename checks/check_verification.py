"""
check_verification — Independent verification of a script against its evidence map.

Phase 8 of the hybrid pipeline. An independent model (GLM-5.2 via Z.ai by
default) compares the drafted script to the evidence map and flags claims that
are not traceable to the evidence. Scripts with more than the configured
threshold of high-confidence untraceable claims fail content QA.

This complements (does not duplicate) check_substance's deterministic filler
denylist: substance catches vague attribution patterns lexically; verification
catches invented numbers/dates/quotes/names semantically.

Best-effort: if no verifier key is configured, or the verifier API fails, or no
evidence map is supplied, the check passes with a "skipped" reason rather than
blocking the episode on a second external dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CheckResult:
    """Standard result from any quality check."""
    passed: bool
    reason: str = ""
    metrics: dict = field(default_factory=dict)

    def __bool__(self):
        return self.passed


def run(fixture: dict) -> CheckResult:
    """Run independent verification against a fixture.

    Expects ``fixture["script_text"]`` and ``fixture["evidence"]`` (a list of
    evidence entries). Skips gracefully when either is missing or the verifier
    is unavailable.
    """
    script_text = fixture.get("script_text", "")
    evidence = fixture.get("evidence")

    if not script_text:
        return CheckResult(passed=False, reason="empty script")

    if not evidence:
        return CheckResult(
            passed=True, reason="skipped: no evidence map available"
        )

    # Imported lazily so the check module loads even without the pipeline.
    try:
        from pipeline_stages import verify_script
    except ImportError:
        return CheckResult(
            passed=True, reason="skipped: pipeline_stages unavailable"
        )

    try:
        result = verify_script(script_text, evidence)
    except RuntimeError as e:
        # No key / API failure — best-effort, do not block.
        return CheckResult(passed=True, reason=f"skipped: {e}")
    except ValueError as e:
        # Unparseable verifier output — proceed rather than block.
        return CheckResult(passed=True, reason=f"skipped: {e}")

    high = result["high_confidence"]
    threshold = result["threshold"]
    metrics = {
        "high_confidence": high,
        "threshold": threshold,
        "total_flagged": len(result["claims"]),
        "claims": result["claims"],
    }

    if high > threshold:
        return CheckResult(
            passed=False,
            reason=f"verification_failed: {high} untraceable claims",
            metrics=metrics,
        )

    return CheckResult(
        passed=True,
        reason=(
            f"{high} high-confidence untraceable claims "
            f"(within threshold of {threshold})"
        ),
        metrics=metrics,
    )
