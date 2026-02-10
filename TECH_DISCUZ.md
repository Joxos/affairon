# TECH_DISCUZ — eventd 技术决策讨论记录

> 记录项目开发过程中每个技术决策的讨论背景、可选方案、最终决定及理由。  
> 按时间顺序追加。每个条目使用 `TD-xxx` 编号，与 `TODO.md` 中的待改进项关联（如适用）。

---

## TD-001: event_id 与 timestamp 的类型注解

**背景**：PRD 中 `event_id_generator` 和 `timestamp_generator` 的签名为 `() -> Any`，允许用户自定义（如 `uuid4().hex` 返回 `str`）。但 HOW_TO.md §8 要求所有变量必须编写类型注解，`Any` 不符合规范。

**可选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A | 固定 `event_id: int`, `timestamp: float`，生成器签名 `() -> int` / `() -> float` | 简单、类型安全、初版够用 | 限制用户自定义类型（如 UUID） |
| B | 使用泛型 `Dispatcher[IdT, TsT]`，生成器签名 `() -> IdT` / `() -> TsT` | 灵活、完全类型安全 | 增加用户侧复杂度 |
| C | 默认类型 `int` / `float`，生成器签名仍为 `() -> Any` | 折中 | 类型不安全 |

**决定**：方案 A。初版保持简单，泛型支持记录到 `TODO.md` TD-001 待后续版本实现。

**理由**：绝大多数场景 `int` 自增和 `float` 时间戳已足够。泛型方案的用户体验设计需要更多考量（默认值、类型推导等），不适合 MVP 阶段引入。

---

## TD-002: pydantic ValidationError 的包装策略

**背景**：eventd 使用 pydantic BaseModel 进行事件字段验证。如果用户同时使用 pydantic，`ValidationError` 的来源不明确。

**可选方案**：

| 方案 | 描述 |
|------|------|
| A | 不包装，直接抛出 pydantic 原生 `ValidationError` |
| B | 捕获并包装为 `EventValidationError`，通过 `raise ... from e` 保留原始链 |

**决定**：方案 B。新增 `EventValidationError(EventdError, ValueError)`，在 Event 构造时捕获 `ValidationError` 并重新抛出。

**理由**：用户可通过 `except EventdError` 捕获所有 eventd 异常，或通过 `except EventValidationError` 精确捕获验证错误。`__cause__` 链保留完整的 pydantic 错误信息。Litestar 等成熟库也采用类似模式。

---

## TD-003: 异常继承策略 — 双继承 vs 单继承

**背景**：eventd 需要统一的异常基类 `EventdError`，但用户可能习惯捕获标准异常类型（如 `ValueError`、`RuntimeError`）。

**可选方案**：

| 方案 | 描述 |
|------|------|
| A | 只继承 `EventdError` |
| B | 双继承 `EventdError` + 对应标准异常类型 |

**决定**：方案 B。异常同时继承 `EventdError` 和对应的标准异常类型。

**理由**：向后兼容标准异常捕获习惯。用户既可以 `except EventdError` 捕获所有 eventd 异常，也可以 `except ValueError` 按语义捕获。

**异常层级**：

```
EventdError(Exception)
├── EventValidationError(EventdError, ValueError)
├── CyclicDependencyError(EventdError, ValueError)
├── KeyConflictError(EventdError, ValueError)
├── QueueFullError(EventdError, RuntimeError)
└── ShutdownTimeoutError(EventdError, TimeoutError)
```

---

## TD-004: 枚举类型选择 — StrEnum vs Enum

**背景**：`error_strategy` 等配置参数需要枚举值。Python 3.11+ 提供 `StrEnum`，3.12+ 更成熟。

**可选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A | `enum.Enum` | 更严格，不允许与字符串直接比较 | 日志输出不直观 |
| B | `enum.StrEnum` | `ErrorStrategy.PROPAGATE == "propagate"` 为 `True`，序列化/日志更友好 | 稍微不那么严格 |

**决定**：方案 B。使用 `StrEnum`。

**理由**：项目要求 Python 3.12+，`StrEnum` 原生支持。日志和调试输出更直观，序列化更方便。

---

## TD-005: 可选类型注解风格 — `X | None` vs `Optional[X]`

**背景**：PEP 604（Python 3.10+）引入了 `X | None` 语法，与 `typing.Optional[X]` 等价。项目已采用 PEP 585 规范（`list[str]` 替代 `typing.List[str]`）。

**决定**：统一使用 `X | None`，禁止 `Optional[X]`。

**理由**：减少 `typing` 模块导入依赖，保持与 PEP 585 规范的一致性。虽然 `Optional[X]` 可读性略优，但统一风格更重要。

---

## TD-006: `after` 参数类型 — `list[Callable]` vs `list[str]`

**背景**：监听器注册时的 `after` 参数用于声明执行顺序依赖。原设计使用 `list[str]`（监听器名称）。

**可选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A | `list[str]` | 松耦合 | 不可被 IDE/类型检查器验证；不同命名空间同名函数冲突 |
| B | `list[Callable]` | 类型安全、IDE 可检查、无命名冲突 | 必须先有函数引用才能声明依赖（这实际上是合理的约束） |

**决定**：方案 B。`after` 使用 `list[Callable]`。

**理由**：使用函数引用而非字符串名称，类型安全且避免命名空间冲突。用户声明 `after` 依赖时必须先定义被依赖的函数，这是自然的时序约束。`ListenerEntry.name` 保留为可选的调试标识（默认 `callback.__qualname__`），用于日志和错误消息。

---

## TD-007: `unregister` 灵活参数设计

**背景**：原设计要求同时传入 `event_types` 和 `callback`，限制过严。

**决定**：支持灵活的参数组合。

**行为矩阵**：

| `event_types` | `callback` | 行为 |
|---------------|------------|------|
| 有 | 有 | 从指定事件类型中移除指定回调 |
| 有 | `None` | 移除指定事件类型的所有监听器 |
| `None` | 有 | 从所有事件类型中移除指定回调 |
| `None` | `None` | `ValueError`（至少传一个参数） |

**约束**：每种情况都检查 `after` 依赖 — 如果批量移除导致残留监听器的 `after` 失效，抛出 `ValueError`。

---

## TD-008: EventQueue 数据结构选择

**背景**：同步事件队列需要 FIFO + 有界 + 满时抛异常的行为。

**标准库选项分析**：

| 选项 | 特点 | 适用性 |
|------|------|--------|
| `collections.deque(maxlen=N)` | O(1) 双端操作，但 `maxlen` 满时**静默丢弃旧元素** | 不设 maxlen，手动检查 size |
| `queue.Queue(maxsize=N)` | 线程安全，`put(block=False)` 满时抛 `queue.Full` | 单线程场景有线程安全开销 |
| `list` | 简单，但 `pop(0)` 是 O(n) | 性能不佳 |

**决定**：

- 同步队列（`EventQueue`）：内部使用 `collections.deque`（不设 maxlen），`put` 时手动检查 size 并抛 `QueueFullError`
- 异步队列（`AsyncEventQueue`）：直接使用 `asyncio.Queue`
- 死信队列（`DeadLetterQueue`）：使用 `collections.deque`（无 maxlen），为后续可能的多线程双端读取需求预留

**理由**：`deque` 的 `append`/`popleft` 均为 O(1)，且 `deque` 是线程安全的（CPython GIL 下单个操作原子），为后续扩展预留空间。保留薄封装类以维持架构层次清晰。

---

## TD-009: 命名规范 — 同步/异步前缀

**背景**：项目名称为 Eventd，代码中遵循 Python 命名规范写作 eventd。

**决定**：同步类不加 `Sync` 前缀，异步类加 `Async` 前缀。

**变更**：

| 原名 | 新名 |
|------|------|
| `SyncDispatcher` | `Dispatcher` |
| `AsyncDispatcher` | `AsyncDispatcher` |
| `SyncEventQueue` | `EventQueue` |
| `AsyncEventQueue` | `AsyncEventQueue` |

**理由**：同步是默认行为，异步是特殊化行为，加前缀标注异步是更自然的 Python 约定。

---

## TD-010: ExecutionContext 构建时机

**背景**：`ErrorHandler.handle()` 需要事件执行的上下文信息。原方案在每次调用监听器前构建 `ExecutionContext`。

**可选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A | 每次调用监听器前构建 | 代码简单 | 正常路径（占多数）浪费资源 |
| B | 仅在异常发生时（`except` 块中）构建 | 正常路径零开销 | 代码稍复杂 |

**决定**：方案 B。仅在 `except` 块中构建 `ExecutionContext`。

**理由**：生产环境中正常执行的比例远大于报错，在每次监听器调用前构建上下文对象是不必要的资源浪费。异常路径本身已经是慢路径，额外构建一个 dataclass 的开销可忽略不计。

---

## TD-011: context 字段类型 — dataclass vs dict

**背景**：多处使用 `context: dict` 但未定义结构和收集方式。

**决定**：使用 `ExecutionContext` dataclass 替代 `dict`。

**结构**：

```python
@dataclass
class ExecutionContext:
    event: Event
    listener_name: str
    listener_callback: Callable
    retry_count: int
    event_type: type[Event]
```

**收集方式**：Dispatcher 在 `emit()` 执行监听器时遇到异常，在 `except` 块中构建此对象，传入 `ErrorHandler.handle()`。

**理由**：类型安全、IDE 可自动补全、结构明确。比 `dict` 更不容易出错（键名拼写错误等）。
