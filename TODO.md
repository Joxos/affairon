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
