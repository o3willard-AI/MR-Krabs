#!/usr/bin/env python3
"""PipelineMonitor — Orchestrator self-awareness for MR-Krabs.

Tracks summaries from every role (coder, judge, planner) across the
escalation pipeline and periodically asks meta-questions:

    "Does the summary from the last N actions seem reasonable if
     the MR-Krabs loop is functioning as prescribed?"
    "Should I throw a warning or claim there is an error to the Principal?"

When anomalies are detected, the monitor emits warnings or errors that
the orchestrator can surface to the Principal Agent instead of silently
spinning through tiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(Enum):
    OK = "ok"
    WARN = "warn"
    ERROR = "error"


@dataclass
class ActionRecord:
    """A single action from any role in the pipeline."""
    role: str
    tier: str
    attempt: int
    action_type: str  # "coder_output", "judge_verdict", "escalation", "salvage"
    summary: Dict[str, Any] = field(default_factory=dict)
    anomaly_flags: List[str] = field(default_factory=list)


@dataclass
class HealthCheck:
    """Result of a self-interrogation cycle."""
    severity: Severity
    assessment: str
    anomalies: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    escalate_to_principal: bool = False


class PipelineMonitor:
    """Tracks pipeline health across all tiers and roles.

    The monitor holds a sliding window of the last N actions and can
    self-interrogate to detect when the pipeline is malfunctioning.
    """

    # ── Configuration ────────────────────────────────────────────────
    WINDOW_SIZE = 8               # actions to track
    MAX_CONSECUTIVE_TRUNCATIONS = 3  # trigger warning
    MAX_CONSECUTIVE_LOW_SCORES = 3   # trigger error (all < 0.5)
    MAX_OUTPUT_CHARS_SANE = 50_000   # suspicious if coder output exceeds this
    MIN_OUTPUT_CHARS_SANE = 10       # suspicious if coder output is below this
    MAX_EMPTY_OUTPUTS = 2            # consecutive empty outputs → error
    JUDGE_SCORE_DEGRADING = 0.1      # per-attempt score drop → degradation

    def __init__(self) -> None:
        self.actions: List[ActionRecord] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.principal_escalations: List[str] = []

    # ── Recording ────────────────────────────────────────────────────

    def record(
        self,
        role: str,
        tier: str,
        attempt: int,
        action_type: str,
        summary: Optional[Dict[str, Any]] = None,
        anomaly_flags: Optional[List[str]] = None,
    ) -> None:
        """Record an action from the pipeline."""
        self.actions.append(ActionRecord(
            role=role,
            tier=tier,
            attempt=attempt,
            action_type=action_type,
            summary=summary or {},
            anomaly_flags=anomaly_flags or [],
        ))
        # Trim to window
        if len(self.actions) > self.WINDOW_SIZE:
            self.actions = self.actions[-self.WINDOW_SIZE:]

    # ── Self-Interrogation ───────────────────────────────────────────

    def check_health(self) -> HealthCheck:
        """Run all health checks and return an assessment.

        Called by the orchestrator after each tier attempt or at
        escalation boundaries. The orchestrator should surface
        ERROR-level anomalies to the Principal.
        """
        anomalies: List[str] = []
        recommendations: List[str] = []
        severity = Severity.OK

        # ── Check 1: Consecutive truncations ─────────────────────
        trunc_count = 0
        for action in reversed(self.actions):
            if "truncated" in action.anomaly_flags:
                trunc_count += 1
            else:
                break
        if trunc_count >= self.MAX_CONSECUTIVE_TRUNCATIONS:
            msg = (f"{trunc_count} consecutive truncated coder outputs — "
                   f"PI may be producing malformed JSONL, or the task "
                   f"exceeds PI's single-invocation capacity")
            anomalies.append(msg)
            recommendations.append(
                "Split the task into smaller sub-tasks (<3 files, <3KB spec each). "
                "Check PI system prompt for output format expectations."
            )
            severity = Severity.ERROR

        # ── Check 2: Consecutive very low judge scores ───────────
        low_score_count = 0
        for action in reversed(self.actions):
            if action.action_type == "judge_verdict":
                score = action.summary.get("score", 1.0)
                if score < 0.5:
                    low_score_count += 1
                else:
                    break
        if low_score_count >= self.MAX_CONSECUTIVE_LOW_SCORES:
            msg = (f"{low_score_count} consecutive judge scores below 0.5 — "
                   f"coder output is consistently poor quality or the "
                   f"Judge is misconfigured")
            anomalies.append(msg)
            recommendations.append(
                "Verify the Judge model is a reasoning-capable LLM and its "
                "evaluation criteria match the task type. Consider using a "
                "larger/higher-quality Judge model."
            )
            severity = Severity.ERROR

        # ── Check 3: Score degradation across attempts ───────────
        judge_scores = []
        for action in self.actions:
            if action.action_type == "judge_verdict":
                score = action.summary.get("score")
                if score is not None:
                    judge_scores.append(score)
        if len(judge_scores) >= 3:
            # Check if scores are trending down
            recent = judge_scores[-3:]
            if recent[0] > 0 and all(
                recent[i] - recent[i + 1] >= self.JUDGE_SCORE_DEGRADING
                for i in range(len(recent) - 1)
            ):
                msg = (f"Judge scores degrading: {recent} — "
                       f"coaching feedback may be counterproductive")
                anomalies.append(msg)
                recommendations.append(
                    "The coder may be over-correcting based on Judge feedback. "
                    "Consider resetting the feedback string and retrying from "
                    "the original task spec."
                )
                if severity == Severity.OK:
                    severity = Severity.WARN

        # ── Check 4: Suspicious coder output size ────────────────
        for action in self.actions[-4:]:
            if action.action_type == "coder_output":
                output_chars = action.summary.get("output_chars", 0)
                file_count = action.summary.get("files_written", 0)
                if output_chars > self.MAX_OUTPUT_CHARS_SANE:
                    msg = (f"Coder produced {output_chars:,} chars of output "
                           f"for {file_count} files — {output_chars / max(file_count, 1):,.0f} "
                           f"chars/file — PI JSONL overhead is excessive")
                    anomalies.append(msg)
                    recommendations.append(
                        "PI may be in a tool-call loop. Consider adding "
                        "a max-turns limit to the PI subprocess or reducing "
                        "the task's complexity."
                    )
                    if severity == Severity.OK:
                        severity = Severity.WARN
            if action.action_type == "coder_output":
                output_chars = action.summary.get("output_chars", 0)
                file_count = action.summary.get("files_written", 0)
                if file_count > 0 and output_chars < self.MIN_OUTPUT_CHARS_SANE:
                    msg = (f"Coder produced only {output_chars} chars of output "
                           f"with {file_count} files — output may be empty/stale")
                    anomalies.append(msg)
                    if severity != Severity.ERROR:
                        severity = Severity.WARN

        # ── Check 5: Consecutive empty outputs ───────────────────
        empty_count = 0
        for action in reversed(self.actions):
            if action.action_type == "coder_output":
                oc = action.summary.get("output_chars", 0)
                fc = action.summary.get("files_written", 0)
                if oc < 50 and fc == 0:
                    empty_count += 1
                else:
                    break
        if empty_count >= self.MAX_EMPTY_OUTPUTS:
            msg = (f"{empty_count} consecutive empty coder outputs — "
                   f"PI subprocess may be crashing or the model is "
                   f"unable to produce output")
            anomalies.append(msg)
            recommendations.append(
                "Check PI subprocess exit codes and stderr. The model may not "
                "support the requested output format or may be timing out."
            )
            severity = Severity.ERROR

        # ── Assess escalation ────────────────────────────────────
        escalate = severity == Severity.ERROR

        return HealthCheck(
            severity=severity,
            assessment=self._build_assessment(anomalies, severity),
            anomalies=anomalies,
            recommendations=recommendations,
            escalate_to_principal=escalate,
        )

    def _build_assessment(self, anomalies: List[str], severity: Severity) -> str:
        """Build a natural-language assessment for the orchestrator."""
        window = self.actions[-self.WINDOW_SIZE:]
        role_counts: Dict[str, int] = {}
        for a in window:
            role_counts[a.role] = role_counts.get(a.role, 0) + 1

        roles_str = ", ".join(f"{r}({c})" for r, c in sorted(role_counts.items()))

        if severity == Severity.OK:
            return (f"Pipeline healthy. Last {len(window)} actions: {roles_str}. "
                    f"No anomalies detected.")
        elif severity == Severity.WARN:
            return (f"Pipeline WARNING. Last {len(window)} actions: {roles_str}. "
                    f"Anomalies: {'; '.join(anomalies)}")
        else:
            return (f"Pipeline ERROR — escalate to Principal. "
                    f"Last {len(window)} actions: {roles_str}. "
                    f"Anomalies: {'; '.join(anomalies)}")

    # ── Recent window ────────────────────────────────────────────────

    def recent_actions(self, n: int = 4) -> List[ActionRecord]:
        """Return the most recent N actions for inspection."""
        return self.actions[-n:]

    def last_action(self) -> Optional[ActionRecord]:
        """Return the most recent action, if any."""
        return self.actions[-1] if self.actions else None

    # ── Convenience recorders ────────────────────────────────────────

    def record_coder_output(
        self,
        tier: str,
        attempt: int,
        output_chars: int,
        files_written: int,
        truncated: bool = False,
        exit_code: Optional[int] = None,
    ) -> None:
        """Record a coder output action."""
        flags = []
        if truncated:
            flags.append("truncated")
        if exit_code and exit_code != 0:
            flags.append(f"exit_code={exit_code}")
        self.record(
            role="coder",
            tier=tier,
            attempt=attempt,
            action_type="coder_output",
            summary={
                "output_chars": output_chars,
                "files_written": files_written,
                "truncated": truncated,
                "exit_code": exit_code,
            },
            anomaly_flags=flags,
        )

    def record_judge_verdict(
        self,
        tier: str,
        attempt: int,
        score: float,
        accepted: bool,
        provisional: bool = False,
    ) -> None:
        """Record a judge verdict."""
        flags = []
        if score < 0.3:
            flags.append("very_low_score")
        elif score < 0.5:
            flags.append("low_score")
        if provisional:
            flags.append("provisional")
        self.record(
            role="judge",
            tier=tier,
            attempt=attempt,
            action_type="judge_verdict",
            summary={
                "score": score,
                "accepted": accepted,
                "provisional": provisional,
            },
            anomaly_flags=flags,
        )

    def record_escalation(
        self,
        from_tier: str,
        to_tier: str,
        reason: str,
    ) -> None:
        """Record a tier escalation."""
        self.record(
            role="orchestrator",
            tier=from_tier,
            attempt=0,
            action_type="escalation",
            summary={
                "from": from_tier,
                "to": to_tier,
                "reason": reason,
            },
            anomaly_flags=["escalation"],
        )
