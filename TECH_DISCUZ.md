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
└── ShutdownTimeoutError(EventdError, TimeoutError)
```

> **注**：`QueueFullError(EventdError, RuntimeError)` 已在 TD-013 讨论中移除 — 同步路径不再使用 EventQueue，异步路径使用 `asyncio.Queue` 的原生异常。

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
    listener_callback: Callable[[Event], dict[str, Any] | None]
    retry_count: int
    event_type: type[Event]
```

**收集方式**：Dispatcher 在 `emit()` 执行监听器时遇到异常，在 `except` 块中构建此对象，传入 `ErrorHandler.handle()`。

**理由**：类型安全、IDE 可自动补全、结构明确。比 `dict` 更不容易出错（键名拼写错误等）。

---

## TD-012: asyncio.TaskGroup 替代 asyncio.gather

**背景**：`AsyncDispatcher.emit()` 中同一优先级层内的多个异步监听器需要并发执行。原设计使用 `asyncio.gather(return_exceptions=True)` 收集异常。

**可选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A | `asyncio.gather(return_exceptions=True)` | 熟悉度高，所有任务运行完毕后统一检查 | 异常混在返回值中需手动筛选；不符合结构化并发趋势 |
| B | `asyncio.TaskGroup`（Python 3.11+） | 结构化并发，异常通过 `ExceptionGroup` 传播，支持 `except*` 语法 | 首个任务失败时取消其余任务（需要评估是否符合需求） |

**决定**：方案 B。使用 `asyncio.TaskGroup`。

**理由**：
1. 结构化并发是 Python 异步的未来方向，`asyncio.gather` 被社区视为遗留 API。
2. `ExceptionGroup` + `except*` 语法提供更清晰的多异常处理模型。
3. TaskGroup 的「首个失败即取消」行为与 eventd 的错误策略（PROPAGATE 模式）天然契合。
4. 项目要求 Python 3.12+，无兼容性顾虑。
5. 注意：需使用默认参数技巧避免闭包捕获问题 — `async def _run(idx: int = i, e: ListenerEntry = entry)`。

---

## TD-013: 移除同步 Dispatcher.emit() 的递归保护机制

**背景**：原设计中同步 `Dispatcher.emit()` 使用 `_is_emitting` 标志位 + `EventQueue` 实现递归保护 — 当监听器在执行过程中触发新的 `emit()` 时，新事件被推入队列延迟处理，而非直接递归。

**讨论**：
- 用户认为该保护机制过度设计，Python 自身的 `RecursionError`（默认栈深度 ~1000）已是足够的安全网。
- 队列化处理改变了事件的语义 — 延迟执行与即时递归的行为差异可能令用户困惑。
- 移除队列后，同步路径不再需要 `EventQueue` 组件，架构得以简化。

**可选方案**：

| 方案 | 描述 |
|------|------|
| A | 保留 `_is_emitting` + `EventQueue` 递归保护 |
| B | 完全移除保护，依赖 Python `RecursionError` |
| C | 移除队列，但保留可配置的深度计数器（`max_emit_depth`） |

**决定**：方案 B（初版），方案 C 记录到 `TODO.md` TD-004 待后续实现。

**理由**：
1. 直接递归保持了事件的即时语义，行为更可预测。
2. Python `RecursionError` 是可靠的安全网，无需框架层面重复保护。
3. 在函数 docstring 中警告用户避免构建循环事件链。
4. 同步路径移除 `EventQueue` 后，`EventQueue` 简化为仅 `AsyncEventQueue`（异步路径仍需队列处理协程切换场景）。
5. 未来可通过 `max_emit_depth` 计数器提供更精细的控制（TD-004）。

**附带变更**：
- 移除 `QueueFullError` 异常（无同步队列则无需此异常）。
- §8.2.9（递归事件处理）章节整体移除，相关逻辑合并到 §8.2.2 同步 emit 流程中。
- C-004 组件清单从「EventQueue / AsyncEventQueue」简化为仅「AsyncEventQueue」。

---

## TD-014: Callable 注解必须携带完整参数和返回值类型

**背景**：原设计中多处使用不完整的 `Callable` 注解（如 `Callable`、`Callable[..., Any]`），不符合项目类型安全要求。

**决定**：所有 `Callable` 注解必须包含完整的参数类型列表和返回值类型。使用 `collections.abc.Callable` 而非 `typing.Callable`。

**注解清单**：

| 用途 | 完整注解 |
|------|----------|
| 同步监听器回调 | `Callable[[Event], dict[str, Any] \| None]` |
| 异步监听器回调 | `Callable[[Event], Awaitable[dict[str, Any] \| None]]` |
| 重试判断函数 | `Callable[[Exception, ExecutionContext], bool]` |
| event_id 生成器 | `Callable[[], int]` |
| timestamp 生成器 | `Callable[[], float]` |

**理由**：完整的 Callable 注解让 IDE 和类型检查器能够验证回调签名，避免运行时参数不匹配错误。符合 HOW_TO.md §8 的类型注解规范要求。

---

## TD-015: C-003 ListenerStore 重命名为 RegistryTable

**背景**：C-003 组件原名 `ListenerStore`，职责为管理监听器的注册、注销和依赖拓扑排序。内部核心数据结构为 `dict[type[Event], list[ListenerEntry]]`，本质是以事件类型为键的注册表。

**讨论**：用户认为 `ListenerStore` 命名不够准确 — `Store` 暗示简单存储，未能体现组件的注册表（registry）性质和内部的表（table）数据结构。

**决定**：重命名为 `RegistryTable`。

**变更范围**：
- 类名：`ListenerStore` → `RegistryTable`
- 实例属性：`self._listener_store` → `self._registry`
- 文件名：`listener.py` → `registry.py`
- INFRASTRUCTURE.md 全文更新（§1~§8 所有引用）

**理由**：`RegistryTable` 更准确地描述了组件的双重性质 — 既是注册中心（Registry），又以表结构（Table）组织数据。命名应当反映实现意图而非仅仅描述功能。

---

## TD-016: `_merge_dict` 重命名为 `merge_dict`（移除前导下划线）

**背景**：`_merge_dict` 是 `Dispatcher.emit()` 中合并各监听器返回的 `dict` 的工具函数。原设计使用前导下划线标记为内部方法。

**讨论**：用户认为该函数虽然在 emit 内部使用，但其逻辑（合并字典、键冲突抛 `KeyConflictError`）具有通用性，不应限制为私有。

**决定**：重命名为 `merge_dict`（公共函数），保留 `KeyConflictError` 特化行为，添加完整 docstring。

**理由**：
1. 函数逻辑通用（合并字典 + 冲突检测），用户可能在自定义场景中复用。
2. 移除前导下划线表明这是框架公开的工具函数，属于公共 API 的一部分。
3. 公共函数需要更完善的文档，促进代码可维护性。

---

## TD-017: graphlib.TopologicalSorter 替代自实现 Kahn 算法

**背景**：`RegistryTable.resolve_order()` 需要对监听器的 `after` 依赖关系进行拓扑排序，输出按优先级分层的执行计划。原设计自行实现 Kahn 算法（BFS 逐层剥离入度为 0 的节点）。

**讨论**：用户指出 Python 标准库 `graphlib`（3.9+）提供 `TopologicalSorter`，不应重复造轮子。对于较复杂但已有标准实现的算法，应优先使用标准库。

**可选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A | 自实现 Kahn 算法 | 完全控制分层输出逻辑 | 维护成本高，可能有边界 bug |
| B | `graphlib.TopologicalSorter` | 标准库保证正确性，零维护成本 | `static_order()` 返回扁平序列，需自行分层 |

**决定**：方案 B。使用 `graphlib.TopologicalSorter`。

**实现细节**：
- 使用 `ts.add(node, *dependencies)` 构建依赖图。
- 使用 `ts.static_order()` 获取拓扑序（扁平）。
- 分层逻辑：按 `static_order()` 顺序遍历，同一批无依赖的节点归为一层。
- `graphlib.CycleError` 捕获并包装为 `CyclicDependencyError`。

**理由**：
1. 标准库实现经过充分测试，边界情况处理更可靠。
2. `graphlib` 是 Python 3.9+ 内置模块，无额外依赖。
3. 减少框架自身代码量和维护负担。
4. 符合项目原则 — 「不重复造轮子」。

---

## TD-018: MetaEvent 元事件架构预留

**背景**：原设计中 C-005（ErrorHandler）和 C-006（DeadLetterQueue）通过 Dispatcher 内部直接调用实现。用户提出是否可以用元事件（MetaEvent）机制替代 — 将错误处理和死信入队表达为框架内部事件，用户通过注册 MetaEvent 监听器来自定义行为。

**讨论**：
- 用户认为「预留元事件比实现一个错误处理机制（带配置解析）和一个死信队列（带相关操作）更简单」。
- 关于「MetaEvent 监听器自身出错怎么办」的问题，用户明确：「如果 ErrorHandler 自身出错，说明是框架自身编写问题，这在交付时不应该出现。这应该被视为 bug 而不是设计问题。」
- 因此 MVP 阶段不需要处理 MetaEvent 监听器的递归错误场景。

**决定**：MVP 预留 MetaEvent 类定义，实际功能仍用直接调用实现。完整的元事件化重构记录到 `TODO.md` TD-005。

**预留内容**：

```python
class MetaEvent(Event):
    """框架内部元事件基类。"""

class ListenerErrorEvent(MetaEvent):
    listener_name: str
    original_event_type: str
    error_message: str
    error_type: str

class EventDeadLetteredEvent(MetaEvent):
    listener_name: str
    original_event_type: str
    error_message: str
    retry_count: int
```

**理由**：
1. 预留类定义成本极低（几行代码），但为未来重构奠定基础。
2. 元事件机制比直接实现 ErrorHandler 配置解析 + DeadLetterQueue 操作接口更优雅、更统一。
3. MVP 阶段用直接调用保持简单，避免过度设计。

---

## TD-019: resolve_order 缓存机制（revision 计数器 + WeakKeyDictionary）

**背景**：`RegistryTable.resolve_order(event_type)` 需要进行拓扑排序，这是 O(V+E) 操作。如果注册表未变更，对同一 `event_type` 的重复调用应返回缓存结果以避免不必要的计算。

**讨论**：需要一种轻量的缓存失效机制 — 当注册表发生变更（`add()` / `remove()`）时自动失效缓存。

**可选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A | 无缓存，每次调用都重新排序 | 实现简单 | 高频 emit 场景性能差 |
| B | `functools.lru_cache` + 手动 `cache_clear()` | 标准库支持 | 需在每个变更点手动清理，容易遗漏 |
| C | `_revision` 计数器 + `_plan_cache` 字典 | 自动失效，读路径只需比较整数 | 需自行管理缓存结构 |

**决定**：方案 C。使用 `_revision: int` 计数器 + `_plan_cache: weakref.WeakKeyDictionary`。

**实现细节**：
- `RegistryTable._revision: int = 0`：每次 `add()` / `remove()` 操作后自增。
- `RegistryTable._plan_cache: weakref.WeakKeyDictionary[type[Event], tuple[int, list[list[ListenerEntry]]]]`：缓存键为事件类型（class 对象），值为 `(revision_at_build_time, execution_plan)`。
- `resolve_order()` 步骤 0：检查缓存命中 — 如果 `event_type in _plan_cache` 且 `cached_revision == self._revision`，直接返回缓存的 plan。
- `resolve_order()` 步骤 5：完成排序后写入缓存 — `_plan_cache[event_type] = (self._revision, plan)`。

**理由**：
1. `_revision` 整数比较是 O(1) 操作，缓存命中路径开销极低。
2. `WeakKeyDictionary` 以 `type[Event]` 为键 — 如果用户动态创建的事件类被垃圾回收，对应缓存条目自动清理，防止内存泄漏。
3. 相比 `lru_cache` + `cache_clear()`，revision 方案不需要在每个变更点手动调用清理，只需自增计数器即可。
4. 缓存粒度为单个 `event_type`，不同事件类型的缓存互不影响。
