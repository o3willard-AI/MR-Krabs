# Accountability: the human behind the orchestration

MR-Krabs follows the [Registered Accountable Entity (RAE)](https://github.com/o3willard-AI/RAE)
model: an agent action is not fully accounted for until it is attributable to a
named human being. An agent is the *subject* of attribution, never the object
(RAE N2).

## Read this first: two different "L0/L1/L2" ladders

MR-Krabs uses the labels **L0, L1, L2, Principal** for its *model escalation
tiers*. The RAE specification uses the labels **L0, L1, L2** for its *assurance
levels*. The labels collide; the concepts have nothing to do with each other.
Never conflate them.

| | MR-Krabs model tiers | RAE assurance levels |
|---|---|---|
| What it grades | **Capability and cost routing**: which model handles the work | **Accountability strength**: how firmly the human is identified and proven |
| L0 | Local model on llama.cpp (~75% of tasks, zero cost) | Declared identity only — claimed, unverified |
| L1 | First cloud escalation (OpenRouter or secondary local) | Org-verified identity + signing credential bound to authorization records |
| L2 | Premium cloud escalation | Third-party-verified identity (KYC/eID-grade) + independently verifiable tamper-evident registry |
| Beyond | Principal: falls back to the calling agent | (no L3; the ladder ends at L2) |
| Direction of travel | Work escalates *up* when retries are exhausted | Assurance rises when *identity verification* strengthens |

A task handled entirely by the local model is "resolved at tier L0." An MR-Krabs
deployment with a self-declared operator "displays an RAE at L0." Both sentences
can be true of the same run, and they say completely different things: the first
is about which model did the work; the second is about how well we can prove who
is answerable for it. When precision matters, qualify the label — "model tier
L1" versus "assurance level L1" — or use the full phrases. This document and
[RAE-CONFORMANCE.md](../RAE-CONFORMANCE.md) use **"RAE L0" / "assurance level"**
for accountability and **"tier L0" / "model tier"** for routing.

## The accountability chain

**1. The operator submits the task.**

Every MR-Krabs run begins with a human writing a spec and submitting the task.
The pipeline (coder → judge → retry → escalate) then runs fully autonomously —
but the work it does is the operator's work, delegated, not a new actor's.

**2. The operator reviews the final output.**

The architecture closes where it opens: a human reviews the final output, and
the human gate (`wait_for_human`) blocks on explicit confirm-or-deny before
results are accepted. The operator is not merely the requester; they are the
accepting authority. Under RAE, sponsorship (standing advance authorization)
and approval (specific authorization of a particular action) both establish the
accountability link — MR-Krabs has both shapes: submitting the task sponsors
the run, and confirming at the gate approves the output.

**3. Every orchestrated action is attributable to that human.**

Coder passes, judge verdicts, escalations, retries, and gate decisions are
recorded through the prompt-flow logger and the human-gate record, and the run
is bound to the operator of record (`operator_id` / `operator_name` in
config — added by the companion code change this documentation describes).
So the trail resolves person → task → orchestrated action without leaving the
run's own records. Attribution terminates at the operator, never at the coder
model, the judge, or the orchestrator — no matter how many tiers the work
escalated through. A task that runs to model tier L2 (premium cloud) is no
less the operator's than one resolved locally at tier L0.

## Assurance level: RAE L0 (declared, unverified)

The operator is **self-declared in configuration and is not verified**. Nothing
in MR-Krabs proves that the configured `operator_name` is the person actually
running it, or a real person at all. Under the RAE assurance ladder this places
the claim at **L0 (declared)**:

> L0 — Claimed identity only. Below the registration bar: a seed of the
> practice, not the practice. (RAE §3)

So the honest claim MR-Krabs makes is: it **displays an RAE at L0 (declared,
unverified)**. It does **not** claim to *implement* RAE — the attribution
machinery of the practice (organization-verified identity, signing credentials
bound to authorization records, the rest of N1/N3/N4/N6–N8) begins at RAE L1,
and MR-Krabs is not there. See [RAE-CONFORMANCE.md](../RAE-CONFORMANCE.md) for
the exact claim boundary.

L0 is still worth having, and MR-Krabs's design makes it more than a name in a
config file: the human gate is a real synchronization point where the declared
operator must act (confirm or deny) for the run to complete, and the prompt-flow
records tie every escalation and verdict to that run. A declared-but-false
operator is a config-trust problem, not an audit-integrity problem. Verifying
operator identity (e.g., signing gate confirmations with an org-issued
credential) would raise the claim to RAE L1 and is out of scope for the current
version.

## Why this matters here specifically

MR-Krabs is an autonomous multi-agent pipeline: it writes code, judges it,
coaches retries, and escalates across models with no human in the loop between
spec and final output. That autonomy is the product — and it is exactly why the
accountability question is not optional. "The judge rejected it twice and tier
L2 rewrote it" describes a mechanism, not an owner. Binding every run to a
declared human operator, with a gate where that human actually decides, is the
difference between an autonomous pipeline that merely logs and one where
somebody is answerable.
