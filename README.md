# Eventd

A framework for **hook-based extensibility** built around *affairs* (typed hook points). Treat each hook point as an extensible function: multiple plugin-style callbacks can cooperate on a single affair and return merged results.

---

## Positioning & Philosophy

Traditional extension often means “modify core + add new code.”
eventd’s stance: treat a requirement as a **hook point** (hook), model it as an **affair**, and let callbacks attach like plugins. Calling the hook point (an **affair call**) is like calling a **large extensible function**:

- Multiple callbacks collaborate on the same hook point
- Results can be merged and returned
- **affair-as-contract**: the affair itself is the data contract

This is not MQ-style “broadcast.” It is a **deterministic, input/output affair call**.

---

## Core Features

- **Typed hook**: affairs are Pydantic models (validation + IDE-friendly)
- **evolving seam**: affairs support inheritance (sub-affairs extend semantics)
- **dependency order**: `after` declares dependencies, enabling layered execution plans
- **naturally concurrent**: once dependency order is explicit, remaining work can run concurrently
- **result merging**: callbacks return dicts that are merged

---

## Design Tradeoffs

This paradigm has clear gains and clear costs:

**Gains**

- Clearer architecture: hook point as contract
- Safer extension: typed, traceable, refactorable affairs
- Explicit execution: order vs concurrency is modeled, not implied

**Costs / Risks**

- Debugging needs stronger tracing and visibility
- Composition and extension add evolving overhead (versioning, compatibility, testing)
- Abstraction introduces performance overhead (mitigate by keeping hot paths internal)

eventd’s long-term goal: turn these costs into **guardrails** (tracing, conflict detection, evolving policies).

---

## Key Semantics

- **Callback returns**: returning a `dict` contributes to result merging; `None` means no contribution
- **Conflicts**: key collisions raise `KeyConflictError`
- **dependency order**: `after` expresses “must run before” constraints
- **Async concurrency**: same-layer callbacks run concurrently; failures may surface as `ExceptionGroup`

---

## Status (MVP)

- MetaEvent types exist but are **not auto-emitted** yet
- Runtime cycle detection for recursive `emit` is not provided (user must avoid cycles)

---

## Vision (Short)

Build a framework where **hook-based extensibility** achieves **production-safe adoption**:

- hook point = Typed hook (contract & readability)
- extension = plugin-style callbacks (low-intrusion evolving)
- execution = dependency order / naturally concurrent (predictable)
- guardrails = tracing / evolving policies (operable)

If you align with this paradigm, contributions and discussions are welcome.
