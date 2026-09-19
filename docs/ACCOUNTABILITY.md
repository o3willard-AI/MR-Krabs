# Accountability Model (RAE)

**MR-Krabs displays an RAE at L0 (declared, unverified),** per the
[Registered Accountable Entity (RAE) specification](https://github.com/o3willard-AI/RAE)
(v1.0.4 at the time of writing).

This page defines who is accountable for work MR-Krabs orchestrates, how that
accountability is recorded, and — importantly — what the labels L0/L1/L2 do
and do not mean in this repository.

## The accountable human: the operator

In the MR-Krabs pipeline:

```
Human writes spec → MR-Krabs loop (coder → judge → retry/accept → escalate)
                         ↑ fully autonomous                    ↓
                    Human reviews final output         Principal Agent (fallback)
```

the **operator** — the human who submits the task (writes the spec) and reviews
the final output — is the RAE: the single natural person accountable for what
the pipeline produces under that task.

Everything the pipeline does on a submitted task — the coder's output, the
judge's accept/reject decisions, retries, coaching feedback, and tier
escalation — is orchestrated work performed on the operator's behalf, and is
**attributable to that human**, never to an agent. Agents (the coder, the
judge, the orchestrator, the Principal fallback) are instruments of the
operator's task; under the RAE spec an agent is never an accountable entity
(N2), and accountability terminates at the natural person who submitted the
work (N5).

## Declared, not verified: why this is L0

The operator's identity is **self-declared**. MR-Krabs records the operator's
identity (operator id/name) alongside the task and surfaces it in the
prompt-flow log and at the human review gate, but nothing verifies that
declaration: there is no organizational identity check, no signing credential
bound to authorization records, and no registration event that precedes
action.

Under the RAE assurance ladder (§3 of the spec), a claimed-but-unverified
identity caps the system at **L0 (declared, unverified)**. MR-Krabs therefore
displays an RAE at L0 and makes no claim of L1 (registered) or L2
(registered, verified). Per the spec, L0 is display-only: it is a seed of the
accountability practice, not the practice itself, and the attribution
machinery (N1 pre-attribution, N3 no-RAE handling, N4 provenance references,
N6 scope review, N7 sponsorship lifecycle, N8 delegation) begins at L1.

What the accountability record consists of (operator recording is delivered by
a companion code change landing on `main`; until it merges, the declared
operator is not yet stamped in the code paths below — flagged honestly rather
than overclaimed):

- The operator's declared identity (`operator_id` / `operator_name` in config)
  travels with the submitted task through the pipeline.
- The prompt-flow logger stamps the declared operator on run evidence.
- The human gate presents the final output to the same operator for review.

A false declaration is therefore visible in the run record — but visibility is
not verification, and MR-Krabs does not claim it is.

## The label collision: model tiers are NOT assurance levels

MR-Krabs uses the names **L0, L1, L2, and Principal** for its *escalation
tiers*, and the RAE spec uses the names **L0, L1, L2** for its *assurance
levels*. The labels collide; the concepts are completely distinct and must
never be conflated.

| | MR-Krabs L0/L1/L2/Principal | RAE L0/L1/L2 |
|---|---|---|
| **What it names** | A **model/capability tier**: which model the pipeline routes work to | An **assurance level**: how strongly a human's accountability is established |
| **L0 means** | Local model on llama.cpp (~75% of tasks, zero cost) | Declared identity only — claimed, unverified |
| **L1 means** | First cloud escalation (OpenRouter or secondary local model) | Registered — org-verified identity + signing credential |
| **L2 means** | Premium cloud escalation | Registered (verified) — third-party-verified identity + tamper-evident registry |
| **Beyond** | **Principal**: falls back to the calling agent | (nothing above L2) |
| **Axis** | Cost / capability routing of *models* | Trust / verification of the *accountable human* |

Rules of thumb when reading this repo:

- A tier reference is about **which model runs the work** (routing, cost,
  escalation, circuit breakers). See the [Architecture](ARCHITECTURE.md) and
  [Hardware Tiers](HARDWARE-TIERS.md) docs.
- An assurance-level reference is about **who answers for the work** (the
  operator). See this page and [RAE-CONFORMANCE.md](../RAE-CONFORMANCE.md).
- "MR-Krabs operates at L0" is ambiguous on its own — always qualify it:
  "L0 model tier" or "RAE assurance level L0".

The coincidence is unfortunate but harmless as long as the two axes stay
explicit: a task can run entirely on the L2 *model tier* (premium cloud) while
the accountable operator remains at assurance *level* L0 (declared,
unverified), and vice versa. Escalating the model tier never raises the
assurance level, and registering the operator (raising assurance) would never
change which models the pipeline routes to.

## Raising the level

Moving from L0 to L1 is not a documentation exercise; per the spec it would
require, at minimum: organization-verified operator identity, a signing
credential bound to authorization records, pre-attribution (registration
preceding task submission), declared no-RAE handling, provenance references in
run evidence, and a published conformance statement. Until those exist, the
honest claim is the display claim: **an RAE at L0, declared, unverified**.

## References

- RAE specification: https://github.com/o3willard-AI/RAE (`SPEC.md`, §3 assurance ladder, §4 conformance)
- Claim boundary document: [RAE-CONFORMANCE.md](../RAE-CONFORMANCE.md)
- Pipeline architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
