# RAE Conformance Statement — MR-Krabs

**Specification:** [Registered Accountable Entity (RAE)](https://github.com/o3willard-AI/RAE), v1.0.4
**Product:** MR-Krabs (this repository)
**Claim:** *displays an RAE at L0 (declared, unverified)* — **not** *implements RAE*
**Date:** 2026-09-19

> **⚠️ Label collision — read before parsing any "L0/L1/L2" in this repo.**
> MR-Krabs's **L0 → L1 → L2 → Principal** are *model escalation tiers*
> (local llama.cpp → first cloud → premium cloud → calling-agent fallback):
> they grade which model does the work. The RAE spec's **L0/L1/L2** are
> *assurance levels*: they grade how firmly the accountable human is
> identified and proven. The two ladders share labels and share no meaning.
> Every "L0" in *this* file means **RAE assurance level L0 (declared)**, never
> model tier L0. Elsewhere in the repo (README, docs/HARDWARE-TIERS.md,
> configs like `l0-coder`), "L0" means the model tier. See
> [docs/accountability.md](docs/accountability.md) for the full side-by-side.

Per RAE §4, an L0 display is not an implementation and "publishes no
conformance statement." This file is therefore **not** a §4 conformance
declaration — MR-Krabs makes no claim to implement the RAE practice, whose
attribution machinery (N1, N3, N4, N6a/N6b, N7, N8) begins at RAE L1. It is
published voluntarily, at the conventional location §4 names, to state exactly
what MR-Krabs does and does not assert, so no reader has to infer the boundary.

## The claim, precisely

MR-Krabs displays an RAE at L0 (declared, unverified):

- **What exists:** the human operator who submits the task (writes the spec)
  and reviews the final output is the accountable human. The pipeline between
  those two points — coder, judge, retries, tier escalations — is orchestrated
  work attributable to that operator, and attribution terminates at the human,
  never at a model or agent (RAE N2). The human gate blocks on explicit
  confirm-or-deny, so the operator is an accepting authority, not just a
  requester. Run records (prompt-flow logger, gate record) bind the run to the
  operator of record (`operator_id` / `operator_name` in config — added by the
  companion code change this documentation describes).
- **What is missing for RAE L1:** the operator is self-declared in
  configuration and not verified — no organization-verified identity, no
  signing credential bound to authorization records. MR-Krabs will not claim
  RAE L1 until operator identity is verifiable (e.g., signed gate
  confirmations under an org-issued credential).

## Clause status (informational — L0 declares no enforcement tier)

| Clause | Status in MR-Krabs | Note |
|---|---|---|
| N1 Pre-attribution | Partial, declared | The operator names the task before the pipeline runs, and the gate approval precedes acceptance of output — pre-attribution in *shape*. Not registration-grade: the operator binding is an unverified config declaration. |
| N2 Agents are never RAEs | Honored | Coder, judge, orchestrator, and every escalation tier are subjects of attribution; the operator is the object. The Principal tier's fallback to the calling agent does not move accountability: the operator still owns the run. |
| N3 No-RAE invariant | Informational | Every run names an operator of record, and the human gate makes unaccepted output loud rather than silent. MR-Krabs declares no enforcement tier at RAE L0; block-vs-flag semantics belong to L1 conformance. (The gate's deny path is a *quality* control, not an RAE enforcement tier — do not conflate.) |
| N4 Influenced actions | Not applicable | MR-Krabs orchestrates agent work directly; it does not model a human acting on agent output as a separate provenance chain. (The operator reviewing final output is the RAE of their own acceptance decision trivially — N4's base case — but MR-Krabs records no downstream actions beyond the run.) |
| N5 Natural-person resolution | Honored | The operator is a named natural person, never an organization or an agent. |
| N6a/N6b Sponsorship scope | Partial, declared | Submitting a spec authorizes one run against that spec — a per-task scope in practice, narrower than most standing sponsorships. It is not yet a declared-scope expression evaluated at runtime (N6a) or reviewed for breadth (N6b). |
| N7 Sponsorship lifecycle | Not applicable | MR-Krabs's operator binding is per-run configuration, not a standing sponsorship relationship; expiry/transfer semantics have nothing to attach to. Runs are short-lived and end at the gate. |
| N8 Agent-to-agent delegation | Honored (at the run level) | The pipeline *is* agent-invokes-agent (orchestrator → coder/judge → escalation tiers → Principal fallback). Attribution resolves to the operator whose submission covers the invoking pipeline; no tier's involvement displaces the operator, and no tier is itself treated as an accountable party. |

## Proof location

- **Run records:** the prompt-flow logger
  (`src/core/prompt_flow_logger.py`, enabled via `MRKRABS_PROMPT_FLOW_DEBUG=1`
  or `prompt_flow_debug: true`) writes every agent-boundary input/output under
  `~/.mrkrabs/debug/<task_id>/`.
- **Human gate:** pending state, confirmations, and denials are recorded per
  task under `~/.mrkrabs/pending/<task_id>.json`
  (`src/core/human_gate.py`).
- **Operator binding (companion code change):** `operator_id` /
  `operator_name` in `~/.mrkrabs/config.yaml`, propagated into the records
  above, is delivered by the parallel code task this documentation describes.
  This PR is docs-only; it documents the authoritative model that change
  implements.

## What would change the claim

Raising MR-Krabs to *implements RAE 1.0.x L1, \<tier\> tier* (RAE assurance
L1 — not model tier L1) requires: organization-verified operator identity; a
signing credential bound to the operator's authorization records (signed gate
confirmations are the natural fit); declared-scope expressions with N6a/N6b
handling; an enforcement-tier declaration for N3; and conversion of this file
into a true §4 conformance statement using the canonical claim form. Model-tier
names are unaffected by, and independent of, any assurance-level change.
