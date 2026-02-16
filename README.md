# Affairon

An affair-driven framework oriented around “requirement seams”: expose requirements as **affair hook points**, allowing multiple callbacks to collaborate on a single seam and merge results.

---

## Positioning & Philosophy

Traditional extension often means “write new code + modify existing code.”
affaird’s stance: treat a requirement as an affair hook point; callbacks that implement the affair’s functionality attach like **plugins**. Calling the seam (an **affair call**) is like calling a **large extensible function**:

- Multiple callbacks collaborate on the same seam
- Callback results are merged and returned
- **affair-as-contract**

---

## Core Features

- **Type safety**: affairs are Pydantic models
- **Evolvable**: affair classes support inheritance
- **Controllable order**: `after` declares execution order; the framework can generate layered plans via multiple strategies
- **Naturally concurrent**: once required order is controlled, other tasks on the seam are naturally concurrent
- **Result aggregation**: multiple callbacks return dicts that are merged

---

## Design Tradeoffs

This paradigm is not “universal,” but its gains and costs are both clear:

**Gains**

- Clearer architecture: seam as contract
- Safer extension: affair types are traceable, refactorable, and verifiable
- More controllable execution: explicit order / concurrency

**Costs / Risks**

- Debugging needs stronger trace visibility
- Composition and extension increase maintenance cost (versioning, compatibility, testing)
- Abstraction introduces performance overhead (mitigate via hot-path consolidation)

affaird’s long-term goal: reduce costs and risks via framework assistance (affair stack, conflict detection, evolving policies).

---

## Key Semantics

- **Callback returns**: returning a `dict` is merged; returning `None` contributes nothing
- **Conflicts**: key collisions raise `KeyConflictError`
- **dependency order**: `after` declares “must run before” callbacks
- **Async concurrency**: same-layer callbacks run concurrently; failures may surface as `ExceptionGroup`

---

## Project Vision

If you align with this paradigm, contributions and discussions are welcome.
