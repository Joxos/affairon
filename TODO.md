# TODO — eventd

> 记录因快速开发而做出的不完全合理的技术决定，待后续版本改进。

## 待改进项

### TD-001: 支持用户自定义 event_id 和 timestamp 的类型

- **当前状态**：`event_id` 固定为 `int`（默认自增），`timestamp` 固定为 `float`（默认 `time.time()`）。自定义生成器签名为 `() -> int` / `() -> float`。
- **期望状态**：通过泛型参数化 Dispatcher，允许用户声明 `event_id` 和 `timestamp` 的类型（如 `str`、`UUID` 等），自定义生成器签名随之变为 `() -> IdT` / `() -> TsT`。
- **决策原因**：初版保持简单，`int` 自增和 `float` 时间戳覆盖绝大多数场景。泛型方案增加用户侧复杂度，不适合 MVP。
- **影响范围**：C-001（Event）、C-002（Dispatcher）
- **参考讨论**：`TECH_DISCUZ.md` TD-001
