# HOW_TO_en.md — AI-Driven Development Process

> This document defines a complete software development workflow where AI serves as the core executor.  
> Every participating AI Agent **must** read this document before starting work and strictly comply with it.

---

## 0. Terminology

| Term | Definition |
|------|------------|
| **User** | The person who proposes requirements and makes final decisions |
| **Agent** | The AI executing development tasks |
| **Assertion** | User-confirmed, indivisible factual statement (similar to axioms) |
| **Assumption** | Unconfirmed inference about business logic and requirements |
| **Component** | The smallest unit in the system with independently describable interface and responsibilities |
| **Contract** | Component's external interface signature + preconditions + postconditions + invariants |
| **Third-party Axiom** | Behavior explicitly guaranteed by third-party library documentation, treated as axioms without user confirmation |

### 0.1 Prohibition Rules for Assumptions

- **Business Logic Assumptions**: **Prohibited** at any stage. All business logic must be user-confirmed and recorded as assertions.
- **Technical Implementation Assumptions Allowed Scope**:
  - **Allowed**: Python language semantics, standard library behavior (e.g., `dict` time complexity, `asyncio` event loop model).
  - **Allowed**: Third-party axioms (behavior explicitly guaranteed in third-party library official documentation).
  - **Prohibited**: Undocumented third-party library behavior (e.g., internal implementation details, undocumented side effects).
  - **Prohibited**: Performance characteristic assumptions (e.g., "this operation is fast enough"), unless there's documented complexity guarantee.

---

## 1. Requirements Clarification → `PRD.md`

**Goal**: Convert user's vague intent into a logically consistent product requirements document without isolated concepts or implicit assumptions.

### 1.1 Process

1. User states initial idea.
2. Agent asks questions **one by one** for each dimension until user confirms completeness:
   - **User Personas**: Who uses it? Roles and permissions?
   - **Core Behaviors**: What are the key user operations?
   - **Data Model**: What data needs persistence? Relationships between data?
   - **Presentation Layer**: What needs to be displayed? On what devices?
   - **State Transitions**: What are the consequences of success/failure/exceptions?
   - **Non-functional Requirements**: Performance, security, availability, internationalization, etc.
   - **Edge Cases**: Extreme inputs, concurrency, empty states, permission violations, etc.
3. After each round of questions, Agent appends confirmed assertions to the `PRD.md` draft.
4. Only when **all assertions form a logically consistent set with no remaining assumptions**, and user explicitly approves, `PRD.md` is finalized.

### 1.2 Questioning Standards

- Questions **must** be complete and specific.
- Questions **should** be multiple-choice, or at least provide possible options, reference opinions, and examples.
- **Prohibited**: Incomplete questions, such as:
  - "How to handle listeners?" (What are listeners? What should they handle?)
  - "How to handle exceptions?" (What exceptions are possible? What strategies exist?)

### 1.3 `PRD.md` Format Requirements (Example)

```
# PRD — <Project Name>

## 1. Overview
<One-sentence project goal description>

## 2. Users and Roles
- Role A: <Description>
- Role B: <Description>

## 3. Functional Requirements (Sorted by Priority)
### F-001: <Feature Name>
- Trigger Condition: ...
- Input: ...
- Processing Logic: ...
- Output/Result: ...
- Exception Handling: ...

## 4. Non-functional Requirements
- Performance: ...
- Security: ...

## 5. Constraints and Assumptions
<Should be empty or only contain user-explicitly-stated known constraints>

## 6. Glossary
```

---

## 2. Architecture Design → `INFRASTRUCTURE.md`

**Goal**: Map requirements from `PRD.md` to an implementable technical architecture.

### 2.1 Process

1. Agent proposes architecture (component division, tech stack, interaction methods) based on `PRD.md`.
2. User reviews and provides feedback, Agent modifies until user approves.
3. Output initial `INFRASTRUCTURE.md`, including **component diagram** and **dependency graph**.

### 2.2 `INFRASTRUCTURE.md` Format Requirements

```
# INFRASTRUCTURE — <Project Name>

## 1. System Overview
<Text description or ASCII diagram of component relationships>

## 2. Tech Stack
| Layer | Technology | Version | Rationale |
|-------|------------|---------|-----------|

## 3. Component List
### C-001: <Component Name>
- Responsibilities: ...
- Dependencies: [C-xxx, ...]
- Deployment: ...
```

---

## 3. Contract Design → Append to `INFRASTRUCTURE.md`

**Goal**: Define precise external interfaces for each component.

### 3.1 Process

1. For each component in `INFRASTRUCTURE.md`, Agent lists its public APIs.
2. Each API uses **Design by Contract** description:
   - **Signature**: Function/method name, parameter types, return type
   - **Precondition (Pre)**: Conditions that must be satisfied before calling
   - **Postcondition (Post)**: Conditions guaranteed to hold after calling
   - **Invariant (Inv)**: Conditions that always hold before and after calling
   - **Side Effects**: Modifications to external state
   - **Errors**: Possible exceptions and their meanings
3. After user confirmation, append to `INFRASTRUCTURE.md`.

### 3.2 Contract Format (Example)

```
### C-001 API

#### `create_user(name: str, email: str) -> User`
- Pre: `name` non-empty and length ≤ 128; `email` conforms to RFC 5322
- Post: Corresponding record exists in database; returned `User.id` is unique
- Inv: Total user count increases monotonically
- Side Effects: Writes to database
- Errors: `DuplicateEmailError` — Email already exists
```

---

## 4. Internal Logic Design → Append to `INFRASTRUCTURE.md`

**Goal**: Derive internal methods and algorithms from each component's contracts.

### 4.1 Process

1. For each public API, Agent derives internal methods required for its implementation.
2. Use **pseudocode** or **state machines** for complex logic.
3. Annotate time/space complexity (if applicable).
4. After user confirmation, append to `INFRASTRUCTURE.md`.

---

## 5. Implementation Plan → `PLAN.md`

**Goal**: Convert `INFRASTRUCTURE.md` into ordered implementation steps.

### 5.1 Process

1. Agent performs **topological sorting** of components (by dependencies).
2. Divide sorted results into implementation phases, each including:
   - Components/features to implement
   - Acceptance criteria for this phase (automatically derived by Agent from contracts in `INFRASTRUCTURE.md`, user **must** review)
   - Expected files involved
   - Expected commit points (at least one commit per phase)
   - Note whether this phase involves concurrency/synchronization logic, and if so, mark points requiring special attention
3. If project requires special branch strategy (non-default), specify in `BRANCHES.md` (see §7).
4. After user confirmation, output `PLAN.md`.

### 5.2 `PLAN.md` Format Requirements (Example)

```
# PLAN — <Project Name>

## Phase 1: <Name>
- Goal: ...
- Components: [C-001, C-002]
- Acceptance Criteria:
  - [ ] Test T-001 passes
  - [ ] Test T-002 passes
- Files Involved: ...
- Expected Commit: `feat: implement event base class`
- Concurrency Notes: None / <Description>

## Phase 2: <Name>
...
```

---

## 6. Iterative Implementation + Testing

**Goal**: Implement code phase by phase according to `PLAN.md`, with tests accompanying each phase.

### 6.1 Process

Each phase implementation is divided into three steps, **requiring explicit user approval between steps**:

**Step A — Skeleton Generation**:

1. Generate overall API and function/class skeletons (signatures, docstrings, `raise NotImplementedError`) based on contracts in `INFRASTRUCTURE.md`.
2. User reviews skeleton, confirms interface design is correct, then approves.

**Step B — Test Writing**:

1. After skeleton approval and before concrete implementation, write test cases based on contracts.
2. Tests **must** comply with test specifications in §6.2.
3. At this point, run tests; expect all to fail (since implementation is not yet complete).
4. User reviews test cases, confirms coverage and quality, then approves.

**Step C — Concrete Implementation**:

1. Fill in concrete implementation logic in skeleton.
2. Run tests, ensure all pass.
3. Submit code, check off completed items in `PLAN.md`.

**Phase Transition**: After Step C of current phase completes and passes tests, must receive explicit user approval before entering next phase.

If `INFRASTRUCTURE.md` errors or insufficiencies are discovered during implementation, **update documentation first, then modify code**.

### 6.2 Test Specifications

#### 6.2.1 Mandatory Rules

| ID | Rule | Description |
|----|------|-------------|
| T-01 | Each public API's contract **preconditions, postconditions, invariants** each correspond to at least one test | Ensure contract is verified |
| T-02 | Edge cases cover at least all scenarios listed in `PRD.md` | Ensure boundary behavior is correct |
| T-03 | Each test **must** contain meaningful assertions | Prohibit `assert True`, empty assertions, or only checking "no exception thrown" |
| T-04 | Tests **must** be independent of each other, not dependent on execution order | Prohibit implicit state sharing |
| T-05 | Each test verifies only one behavior | Single Responsibility Principle |
| T-06 | Test naming **must** describe the behavior being tested, not implementation details | E.g., `test_emit_triggers_all_registered_listeners`, not `test_loop` |
| T-07 | Exception paths **must** have corresponding tests | Use `pytest.raises` to verify exception type and message |
| T-08 | Async tests **must** use `pytest-asyncio` | Ensure async behavior executes correctly in event loop |
| T-09 | **Must** run all tests before each commit and merge | Ensure code changes don't introduce regressions |

#### 6.2.2 Recommended Rules

| ID | Rule | Description |
|----|------|-------------|
| T-R1 | Use `pytest.fixture` to manage test data and shared resources | Reduce duplication, improve maintainability |
| T-R2 | Use `pytest.mark.parametrize` for parameterized tests in complex scenarios | Improve coverage |
| T-R3 | Mock/stub only for isolating external dependencies (e.g., network, filesystem), don't mock internal methods of tested code | Avoid coupling tests with implementation |
| T-R4 | Use `Given-When-Then` comments to organize test structure | Improve readability |
| T-R5 | For stateful objects, test their complete lifecycle | E.g., create → use → destroy |
| T-R6 | Place fixtures in `conftest.py`, organize test files by module | Keep test directory structure clean |

#### 6.2.3 Coverage Requirements

- No hard coverage percentage target.
- Agent **must** provide written explanation for uncovered code paths, for user review.
- Explanation format: List uncovered paths and reasons in commit message or phase summary.

---

## 7. Version Control

### 7.1 Commit Specification

- All commit messages **must** use [Conventional Commits](https://www.conventionalcommits.org/) format.
- Detailed specification in project root `CONV_COMMIT.md`.
- Format: `<type>(<scope>): <description>`
- Common types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`.

### 7.2 Branch Strategy (Default)

| Branch | Purpose | Operator |
|--------|---------|----------|
| `dev-ai` | Agent's working branch, all Agent commits go here | Agent |
| `dev` | User merges and reviews changes from `dev-ai` here | User |
| `main` | Stable branch, user merges approved changes here | User |

- For special branch requirements, user must specify in `BRANCHES.md`, Agent **must** check if `BRANCHES.md` exists before starting work.

---

## 8. Code Standards

### 8.1 General Standards (Applicable to All Projects)

| Category | Standard |
|----------|----------|
| Naming Convention | Follow PEP 8 (functions/variables `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`) |
| Code Formatting | Use `ruff format` |
| Static Checking | Use `ruff check` |
| Import Sorting | Use `isort` (integrated via ruff, independent execution not allowed) |
| Type Hints | Use PEP 585 built-in generic syntax (`list[str]`, `dict[str, int]`, `tuple[int, ...]`), **prohibit** old syntax like `typing.List`, `typing.Dict`. Optional types use `X \| None`, **prohibit** `typing.Optional` (reduce `typing` module imports, maintain style consistency) |
| Enum Values | Use `enum.Enum` (Python 3.11+) or newer implementations for specific data types (e.g., `enum.StrEnum`), **prohibit** literal string enums (e.g., `"propagate" \| "capture"`) |
| Standard Library Priority | Prioritize standard library data structures and tools, **prohibit** reimplementing functionality already provided by standard library. For special requirements, should inherit standard library implementation and extend |
| Docstring | Google Style |
| Package Management | Use `uv` |
| Testing Framework | `pytest` + `pytest-asyncio` |
| In-code Comments | Use English for in-code comments only |
| Git Usage | AI should NOT use git directly (except inspection like git log and git status) unless it has user's permission |

### 8.2 Python Projects

- Commit messages must use Conventional Commits (see §7.1).
- All Python variables must have type annotations, unless there's sufficient reason not to.
- All code must pass formatting and static checking before submission.

---

## 9. Agent Behavioral Standards

### 9.1 Workload Control

- Agent's workload in each reply **should** be controlled to about one git commit's worth.
- Agent should minimize the number of task divisions when dividing tasks, and complete as much as possible at once. Even if there are doubts and points needing discussion, should first make drafts/placeholders, and bring up all issues at the end.

### 9.2 Progress Reporting

- Agent **must** summarize current progress and ask for next steps at the end of each reply.

### 9.3 Problem Handling

- When Agent discovers problems during implementation, **should** record them and continue working, pointing out all discovered problems at the end of the reply.
- If a problem affects implementation, Agent can suspend that part or only complete a draft, explaining the reason at the end of the reply, but **must not** interrupt midway regardless of draft completion.

### 9.4 Critical Thinking

- After receiving user feedback, Agent **should** think critically, only accepting reasonable feedback to ensure code quality.
- If user feedback contradicts existing assertions, Agent **must** follow user feedback, but **must** simultaneously issue a warning and update related assertions.

### 9.5 Questioning Standards

- When Agent asks user questions, **must** simultaneously provide reference opinions, optional solutions, and/or examples.
- **Prohibited**: Open-ended questions without reference options.

### 9.6 Multi-Agent Collaboration

- Collaboration boundaries between Agents are defined by `PLAN.md`. Each phase can be annotated with responsible Agent identity.
- Different Agents synchronize state through documents (`PRD.md`, `INFRASTRUCTURE.md`, `PLAN.md`), not relying on conversation context.

### 9.7 Technical Debt Recording

- For technical decisions made midway for rapid development that are not entirely reasonable, Agent **must** record the issue in `TODO.md`.
- Each record includes: ID, problem description, reason for occurrence, suggested future improvement direction.
- If Agent chooses "use simple solution first, optimize later" path during implementation, **must** leave an entry in `TODO.md`.

### 9.8 Technical Decision Discussion Recording

- Discussions between User and Agent about technical solutions, Agent **must** record discussion process and final conclusion in `TECH_DISCUZ.md`.
- Each record includes: ID, discussion topic, alternative solutions, final decision and rationale.
- Recording timing: Immediately append to `TECH_DISCUZ.md` after user confirms technical decision.

### 9.9 Commit Message Suggestions

- After each phase task completion, Agent **must** provide commit message suggestions.
- Commit message **must** follow Conventional Commits format (see §7.1 and `CONV_COMMIT.md`).
- Suggestions should reflect actual changes in this phase task, not generic descriptions.

---

## 10. Delivery and Review → `REVIEW.md`

**Goal**: Deliver project and summarize experience.

### 10.1 Trigger Timing

`REVIEW.md` is generated or updated in two situations:

1. **After user points out error**: Agent fixes error and records error cause, fix solution, and prevention measures in `REVIEW.md`.
2. **After overall project acceptance**: Agent generates complete `REVIEW.md`, including:
   - Compliance comparison with original `PRD.md`
   - Deviations during implementation and reasons
   - Technical challenges encountered and solutions
   - Improvement suggestions for the process itself

---

## Appendix A: Precise Description Languages

In the above workflow, to minimize ambiguity and maximize conciseness, recommend following practices:

| Scenario | Recommended Method | Rationale |
|----------|-------------------|-----------|
| Data Model | **JSON Schema** or **TypeScript Interface** | Precise types, machine-parseable |
| API Contract | **Design by Contract** (Pre/Post/Inv) | Mathematical, eliminates ambiguity |
| State Transitions | **State Machine Diagram** (Mermaid syntax) | Exhaustively lists all states and transitions |
| Implementation Logic | **Pseudocode** | Language-agnostic, concise |
| Component Relationships | **Dependency Graph** (DAG) | Can be used for topological sorting |
| Requirement Items | **Given-When-Then** (BDD style) | Can be directly converted to tests |

---

## Appendix B: Process Checklist

Agent self-checks against following checklist before each phase ends:

### B.1 General Checklist

- [ ] Are there unconfirmed assumptions in this phase's output documents?
- [ ] Are all newly introduced terms defined in glossary?
- [ ] Do all components have clear responsibility boundaries?
- [ ] Do all APIs have complete contract descriptions?
- [ ] Are there isolated concepts (referenced but undefined, or defined but never referenced)?
- [ ] Are document changes synchronized to all related documents?

### B.2 PRD Writing Specific Checklist (Execute after §1.1 Step 4)

Before finalizing PRD, **must** check following dimensions item by item:

#### B.2.1 Completeness of Timing and Triggers

- [ ] Each data generation/modification operation has explicit **timing** (at initialization? at submission? at registration?)
- [ ] Each state change has explicit trigger condition
- [ ] Sync/async context switch points are explicitly marked

#### B.2.2 Consistency of Numeric Semantics

- [ ] Semantics of all numeric configurations (e.g., priority) are confirmed (higher is better or lower is better?)
- [ ] Boundary values are defined (meaning of 0, -1, None)

#### B.2.3 Completeness of Error Handling

- [ ] Each error scenario has explicit handling strategy
- [ ] Configuration API is defined (if user can configure error handling strategy)
- [ ] Exception types are listed

#### B.2.4 Consistency and Constraint Validation

- [ ] Consistency check with all previous decisions (e.g., does it violate "sync can only have sync listeners" convention?)
- [ ] Cross-functional consistency check (e.g., are sync and async behaviors consistent?)

#### B.2.5 Precision of Input/Output

- [ ] Each function's input parameter types and count are precise
- [ ] Each function's return value type and structure are precise
- [ ] Polymorphic inputs (e.g., supports single value or list) are explicitly marked
- [ ] Return value merging/aggregation strategy is defined (if multiple return values exist)
- [ ] Key conflict, value conflict, and other merge conflict handling strategies are defined

#### B.2.6 Accuracy of Architecture Understanding

- [ ] Execution model is explicit (single-threaded? multi-threaded? coroutines?)
- [ ] Blocking/non-blocking behavior is explicit
- [ ] Real purpose of queue is understood (recursion control? decouple producer-consumer? thread communication?)
- [ ] Is "consumer" concept applicable to current architecture (consumer thread may not exist in single-threaded model)

#### B.2.7 Exhaustion of Edge Cases

- [ ] Empty states (no listeners, empty queue, etc.) are handled
- [ ] Extreme inputs (max queue length, circular dependencies, etc.) are handled
- [ ] Concurrency/race conditions are considered

#### B.2.8 Lifecycle Management

- [ ] Startup process is defined
- [ ] Shutdown/cleanup process is defined (do both sync and async support?)
- [ ] Resource release strategy is defined

### B.3 Test Quality Check (Execute after §6.1 Step B)

- [ ] Do tests cover normal paths and exception paths?
- [ ] Does each test contain meaningful assertions (not `assert True`)?
- [ ] Are tests independent of each other (no implicit state dependencies)?
- [ ] Do test names describe the behavior being tested?
- [ ] Are mock/stub only used to isolate external dependencies?
- [ ] Are uncovered code paths explained in writing with reasons?

### B.4 Common Error Patterns (Self-check Table)

| Error Type | Check Question | Example |
|------------|----------------|---------|
| **Missing Timing** | "When is it generated/occurs?" | Is event_id generated at initialization or submission? |
| **Numeric Ambiguity** | "Is higher or lower better for this number?" | Which has higher priority: priority=1 or priority=100? |
| **Unclear Reference** | "What specifically does X refer to?" | Does "listener doesn't exist" mean function doesn't exist or not registered? |
| **API Inconsistency** | "Are these two similar feature APIs symmetric?" | Does decorator support list but method call doesn't? |
| **Context Omission** | "Need to check runtime environment?" | Is async function called inside event loop? |
| **Missing Configuration** | "How to configure this behavior?" | How to set error handling strategy? |
| **Decision Contradiction** | "Does this conflict with previous decisions?" | Does it violate previous decision that sync can only have sync listeners? |
| **Scenario Omission** | "Does sync version also need this feature?" | Is graceful shutdown only implemented for async version? |
| **Architecture Misunderstanding** | "What's the execution model? Is there consumer thread?" | Is sync mode single-threaded or multi-threaded consumer? |
| **Over-defensive** | "Is this check already completed at earlier stage?" | Does emit need to check conditions already guaranteed at registration? |
| **Merge Conflict** | "How to merge multiple return values? What about conflicts?" | Does key conflict overwrite or error? |

---

## Appendix C: Analysis of Original Process Insufficiencies and This Document's Improvements

### Choice of Precise Description Languages

Natural language has inherent ambiguity. This document mitigates this through:

- **Interfaces**: Use Design by Contract (similar to Eiffel language's Design by Contract)
- **Data**: Use JSON Schema or type annotations
- **Behavior**: Use Given-When-Then or state machines
- **Structure**: Use dependency graphs

Complete ambiguity elimination requires formal methods (e.g., TLA+, Alloy), but their learning cost vs. benefit ratio is unreasonable for most projects. The above compromise solutions strike a balance between readability and precision.

### Case Study: Common Errors in PRD Writing (Eventd Project)

During Eventd project's PRD writing process, Agent made following typical errors:

#### Error 1: Missing Timing Description

**Error Description**: Did not specify generation timing of `event_id` and `timestamp` (at initialization vs at submission).
**Root Cause**: When writing feature points, only focused on "what exists", not "when".
**Prevention Measure**: For each data operation, force question "when does this operation occur?"

#### Error 2: Numeric Semantics Assumption

**Error Description**: Assumed `priority` lower is higher priority, but user expected higher is higher.
**Root Cause**: Did not confirm numeric semantics with user, used common but inapplicable convention for this project.
**Prevention Measure**: For all numeric configurations, must explicitly ask "is higher or lower better?"

#### Error 3: Reference Ambiguity

**Error Description**: "Listener doesn't exist" did not specify whether it means "function undefined" or "not registered".
**Root Cause**: Used vague natural language description, did not realize possibility of two interpretations.
**Prevention Measure**: For each conditional judgment, force clarification of specific referent object's state.

#### Error 4: API Asymmetry

**Error Description**: Decorator method supports multiple events (`@on([E1, E2])`), but method call method did not reflect this capability.
**Root Cause**: Did not carefully check API symmetry when copying and pasting feature descriptions.
**Prevention Measure**: When multiple methods (decorator vs method call) exist for same functionality, must compare parameters item by item.

#### Error 5: Context Check Omission

**Error Description**: Did not mention async emit needs to check if inside asyncio event loop.
**Root Cause**: Only focused on normal flow, omitted environment checks.
**Prevention Measure**: For each feature involving sync/async switching, must list context check points.

#### Error 6: Missing Configuration Method

**Error Description**: Mentioned "decided by configuration" but did not specify how to configure.
**Root Cause**: Treated configuration as "implementation detail", but this must be specified in PRD.
**Prevention Measure**: Whenever mentioning "configurable", must immediately define configuration API.

#### Error 7: Decision Contradiction

**Error Description**: F-004 allowed sync manager to call async listeners, violating "sync can only have sync listeners" decision.
**Root Cause**: Did not review previous decision constraints when writing.
**Prevention Measure**: Before writing each feature, review all confirmed design decisions.

#### Error 8: Scenario Omission

**Error Description**: Only implemented graceful shutdown for async mode, omitted sync mode.
**Root Cause**: Incorrectly generalized "async-specific" feature, did not consider sync scenario's equivalent need.
**Prevention Measure**: For each feature, force question "does sync version also need this feature?"

#### Error 9: Behavior Inconsistency

**Error Description**: Sync queue full throws exception, async queue full blocks, behavior inconsistent.
**Root Cause**: Did not consider cross-mode behavior consistency.
**Prevention Measure**: When sync/async two modes exist, must list behavior comparison table.

#### Error 10: Architecture Misunderstanding

**Error Description**: Misunderstood sync single-threaded model as multi-threaded consumer model, description contained concepts like "consumer thread", "blocking wait" inapplicable to single-threaded model.
**Root Cause**: Did not accurately understand execution model (single-threaded vs multi-threaded), used familiar queue pattern (producer-consumer) instead of project's actual need (recursion depth control).
**Prevention Measure**: Explicitly ask: What's the execution model? Does consumer thread exist? What's the queue's real purpose?

#### Error 11: Over-defensive

**Error Description**: Checked "inside asyncio event loop" at emit time, but registration already guaranteed sync manager can only register sync listeners, no need to recheck at emit.
**Root Cause**: Did not realize precondition already guaranteed at earlier stage (registration), added unnecessary runtime check.
**Prevention Measure**: Check each condition: Is this check already completed at registration/initialization stage? Are there redundant checks?

#### Error 12: Merge Conflict Undefined

**Error Description**: Did not define key conflict handling strategy when merging multiple listener return values (overwrite vs error).
**Root Cause**: Assumed user will avoid conflicts, or thought framework should silently handle, did not explicitly define conflict handling strategy.
**Prevention Measure**: For any aggregation/merge operation, must define conflict handling strategy (overwrite, error, or ignore?).

### Lesson Summary

Common root of these errors:

1. **Over-reliance on intuition**: Used "usually" or "default" assumptions instead of confirming with user
2. **Lack of systematic checking**: Did not verify completeness of each feature point item by item
3. **Ignoring edge cases**: Only focused on normal flow, omitted error handling and extreme scenarios
4. **Missing consistency checks**: Did not compare with previous decisions and cross-functionality
5. **Shallow architecture understanding**: Applied familiar patterns instead of understanding project's actual architecture
6. **Over-defensive programming**: Added unnecessary checks, did not consider preconditions already guaranteed at earlier stages

**Core Principle**: Better verbose documentation than missing details. Every ambiguity is a future bug.

**Additional Principles**:

- **Understand architecture first, then describe features**: Ensure accurate understanding of execution model, threading model, data flow, avoid applying familiar but mismatched patterns
- **Check preconditions**: Before adding any check or handling logic, confirm if it's already completed at registration/initialization stage
- **Explicitly define conflict strategies**: Any merge, aggregation operation must explicitly define conflict handling strategy
