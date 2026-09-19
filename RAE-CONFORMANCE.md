# RAE Claim Boundary — MR-Krabs

> **This is not a conformance statement.** Per §4 of the
> [RAE specification](https://github.com/o3willard-AI/RAE) (v1.0.4), a
> conformance statement is required only of implementations claiming **L1 or
> L2**; "an L0 display is not an implementation and publishes no statement."
> MR-Krabs displays an RAE at **L0 (declared, unverified)**, so it publishes
> no §4 conformance declaration. This file is a *voluntary claim-boundary
> document*: it records exactly what MR-Krabs claims, what it does not, and
> the status of each clause — so a reader or auditor never has to guess.

## The claim

**MR-Krabs displays an RAE at L0 (declared, unverified)** against RAE spec
v1.0.4.

The displayed RAE is the **operator**: the human who submits the task (writes
the spec) and reviews the final output. The operator's identity is
self-declared (config `operator_id` / `operator_name`, recorded through the
prompt-flow logger and the human review gate); nothing verifies it. Because
the identity is declared but not org-verified, the assurance level is capped
at L0 regardless of any other property of the system. MR-Krabs does **not**
claim L1 (registered) or L2 (registered, verified), and L0 never takes the
verb "implement."

Machine-readable claim summary:

```yaml
spec_version: "1.0.4"
level: L0            # declared, unverified — display only
tier: null           # enforcement/informational tiers (N3) begin at L1; not claimed
claim: "displays an RAE at L0 (declared, unverified)"
conformance_statement: none   # per spec §4, L0 publishes no statement; this file is voluntary
proof_location: docs/ACCOUNTABILITY.md
```

## Label collision warning

**The "L0/L1/L2" in MR-Krabs's escalation tiers are NOT RAE assurance levels.**
They are *model/capability tiers* (L0 = local model on llama.cpp, L1 = first
cloud escalation, L2 = premium cloud escalation, Principal = calling-agent
fallback). The RAE spec's L0/L1/L2 are *assurance levels* for the accountable
human's identity. The two ladders share labels and nothing else:

| Label | As a MR-Krabs model tier | As a RAE assurance level |
|---|---|---|
| L0 | Local model on llama.cpp | Declared identity, unverified — **MR-Krabs's operator is here** |
| L1 | First cloud escalation | Registered: org-verified identity + signing credential — not claimed |
| L2 | Premium cloud escalation | Registered (verified): third-party identity + tamper-evident registry — not claimed |

A task may run on the L2 model tier while its RAE sits at assurance level L0.
Escalating model tiers never raises the assurance level. Full treatment:
[docs/ACCOUNTABILITY.md](docs/ACCOUNTABILITY.md).

## Clause-by-clause status

Per spec §4, the full attribution machinery (N1, N3, N4, N6a/N6b, N7, N8)
**begins at L1**. An L0 display asserts only the display criterion. The
statuses below are therefore informational about the L0 display, not
implementation claims. "Not claimed" is used instead of "not applicable" —
per the spec, "not applicable" is reserved for architectural inapplicability,
and none of these clauses is architecturally inapplicable to MR-Krabs; they
are simply not built, which at L0 is expected.

| Clause | Summary | Status at L0 | Notes |
|---|---|---|---|
| Display criterion | Show the declared identity with the explicit label "declared, unverified (L0)" | **Met** | `docs/ACCOUNTABILITY.md`, this file, README note; operator recorded via prompt-flow logger and human gate (companion code change) |
| N1 | Pre-attribution: registration precedes action | Not claimed | No registration event exists; the operator declaration is self-asserted at config time, not verified before action |
| N2 | Agents are never RAEs | **Respected** | The coder, judge, orchestrator, and Principal fallback are instruments; accountability terminates at the operator (documented, not enforced by a registry) |
| N3 | No-RAE invariant with declared tier (blocked = enforcement, flagged = informational) | Not claimed | Tier semantics begin at L1. A run with no operator configured still proceeds; nothing is blocked — consistent with an L0 display |
| N4 | Influenced actions carry provenance references to sponsorship records | Not claimed | Run evidence references the declared operator once the companion code change lands, but there is no sponsorship registry to reference; depth/state semantics not implemented |
| N5 | The RAE is a single natural person | **Respected by design** | The operator is a human; Principal fallback goes to a calling *agent*, which is explicitly never the RAE |
| N6a/N6b | Runtime scope-match / registry-time breadth review | Not claimed | No scope records exist to match or review |
| N7 | Sponsorship lifecycle (lapse, expiry, revocation, succession) | Not claimed | The declared operator has no lifecycle machinery; changing the config value is a plain edit, not a succession event |
| N8 | Agent-to-agent delegation: nearest covering sponsorship | Not claimed | MR-Krabs does delegate (coder/judge/Principal), but with no sponsorship records there is no "nearest covering sponsorship" to resolve; delegated work remains attributable to the operator only in the documentary sense above |

## What L1 would require

For reference (not a roadmap commitment): org-verified operator identity, a
signing credential bound to authorization records, pre-attribution records
(N1) naming sponsorship and scope, declared N3 tier handling, N4 provenance
references in run evidence, and a published §4 conformance statement. See
[docs/ACCOUNTABILITY.md](docs/ACCOUNTABILITY.md) and spec §4.

## References

- RAE specification v1.0.4: https://github.com/o3willard-AI/RAE (`SPEC.md`)
- Accountability model: [docs/ACCOUNTABILITY.md](docs/ACCOUNTABILITY.md)
- Model tiers (the other L0/L1/L2): [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/HARDWARE-TIERS.md](docs/HARDWARE-TIERS.md)
