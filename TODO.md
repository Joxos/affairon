# TODO — eventd

> 记录因快速开发而做出的不完全合理的技术决定，待后续版本改进。

## 待改进项

### TD-001: 支持用户自定义 event_id 和 timestamp 的类型

- **当前状态**：`event_id` 固定为 `int`（默认自增），`timestamp` 固定为 `float`（默认 `time.time()`）。自定义生成器签名为 `() -> int` / `() -> float`。
- **期望状态**：通过泛型参数化 Dispatcher，允许用户声明 `event_id` 和 `timestamp` 的类型（如 `str`、`UUID` 等），自定义生成器签名随之变为 `() -> IdT` / `() -> TsT`。
- **决策原因**：初版保持简单，`int` 自增和 `float` 时间戳覆盖绝大多数场景。泛型方案增加用户侧复杂度，不适合 MVP。
- **影响范围**：C-001（Event）、C-002（Dispatcher）
- **参考讨论**：`TECH_DISCUZ.md` TD-001

### TD-002: 异步并发 emit 的行为保证

- **当前状态**：`AsyncDispatcher.emit()` 使用 `_is_emitting` 标志进行递归保护，但未明确定义多个 `emit()` 协程并发调用时的行为（如 `asyncio.gather(d.emit(e1), d.emit(e2))`）。
- **期望状态**：明确并发 `emit` 的语义——是串行化（`asyncio.Lock`）还是支持独立队列并发。
- **决策原因**：初版建议使用 `asyncio.Lock` 串行化，保证行为简单可预测。如性能不可接受再引入并发方案。
- **影响范围**：C-002（AsyncDispatcher）
- **参考讨论**：`INFRASTRUCTURE.md` §8.2.9

### TD-003: 多线程支持（线程安全）

- **当前状态**：`Dispatcher` 和 `AsyncDispatcher` 均假设单线程（或单事件循环）环境运行，未提供任何线程安全保证。`RegistryTable` 的 `_registry`、`_revision`、`_plan_cache` 等内部状态无锁保护。
- **期望状态**：提供线程安全的 Dispatcher 变体或在现有 Dispatcher 中加入可选的线程安全模式（如 `threading.Lock` 保护注册/注销操作，`threading.local` 隔离 emit 上下文等）。
- **决策原因**：初版面向单线程/单事件循环场景，线程安全引入锁竞争和性能开销，需要在明确的多线程使用场景下再做设计。
- **影响范围**：C-002（Dispatcher / AsyncDispatcher）、C-003（RegistryTable）
- **参考讨论**：`TECH_DISCUZ.md` TD-015（RegistryTable 重命名讨论中附带提及）

### TD-004: 递归层数限制回调层数

- **当前状态**：同步 `Dispatcher.emit()` 使用直接递归调用，依赖 Python 的 `RecursionError`（默认栈深度 1000）作为安全网。用户如果构建循环事件链（A→B→A），将在 ~1000 层时崩溃。
- **期望状态**：提供可配置的递归深度限制（如 `max_emit_depth: int = 64`），在超出限制时抛出更具描述性的自定义异常（如 `EmitDepthExceededError`），并在错误消息中包含事件链路径信息以帮助调试。
- **决策原因**：初版使用 Python 原生 `RecursionError` 保持实现简单。自定义限制需要在 emit 路径中维护计数器（性能影响）和设计合理的默认值，需要更多使用场景反馈。
- **影响范围**：C-002（Dispatcher）
- **参考讨论**：`TECH_DISCUZ.md` TD-013（移除同步递归保护讨论）

### TD-005: 元事件化重构（ErrorHandler / DeadLetterQueue → MetaEvent 监听器）

- **当前状态**：C-005（ErrorHandler）和 C-006（DeadLetterQueue）通过 Dispatcher 内部直接调用 `error_handler.handle()` / `dead_letter_queue.enqueue()` 实现。已预留 `MetaEvent` 基类和 `ListenerErrorEvent`、`EventDeadLetteredEvent` 两个子类定义。
- **期望状态**：将 ErrorHandler 和 DeadLetterQueue 的功能完全迁移为 MetaEvent 监听器。Dispatcher 在错误/死信场景中 emit 对应的 MetaEvent，用户通过注册 MetaEvent 监听器来自定义处理逻辑，框架提供默认的内置监听器实现。
- **决策原因**：MetaEvent 监听器方案比直接实现 ErrorHandler 配置解析 + DeadLetterQueue 操作接口更优雅，但需要更完善的 MetaEvent 分发机制设计（如避免 MetaEvent 监听器自身出错时的无限递归）。初版先用直接调用保持简单。
- **影响范围**：C-001（Event / MetaEvent）、C-002（Dispatcher / AsyncDispatcher）、C-005（ErrorHandler）、C-006（DeadLetterQueue）
- **参考讨论**：`TECH_DISCUZ.md` TD-018（MetaEvent 元事件架构预留讨论）
