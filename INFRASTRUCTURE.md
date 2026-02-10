# INFRASTRUCTURE — eventd

## 1. 系统总览

eventd 是一个支持同步/异步模式的 Python 事件驱动框架。系统由 6 个核心组件构成，分为三层：

- **公开 API 层**：Dispatcher（C-002）和 Event（C-001）直接面向用户
- **内部服务层**：ListenerStore（C-003）、EventQueue（C-004）、ErrorHandler（C-005）为 Dispatcher 提供内部能力
- **存储层**：DeadLetterQueue（C-006）存储失败事件

```
┌─────────────────────────────────────────────────────────────────┐
│                        公开 API 层                               │
│                                                                 │
│  ┌───────────────┐    ┌─────────────────────────────────────┐   │
│  │  C-001        │    │  C-002  Dispatcher                  │   │
│  │  Event        │◄───│                                     │   │
│  │  (事件模型)    │    │  BaseDispatcher                     │   │
│  └───────────────┘    │    ├── Dispatcher                    │   │
│                       │    └── AsyncDispatcher               │   │
│                       └──────┬──────────┬──────────┬────────┘   │
│                              │          │          │            │
└──────────────────────────────┼──────────┼──────────┼────────────┘
                               │          │          │
┌──────────────────────────────┼──────────┼──────────┼────────────┐
│                        内部服务层        │          │            │
│                              │          │          │            │
│  ┌───────────────┐  ┌───────▼───┐  ┌───▼──────────▼────────┐   │
│  │  C-003        │  │  C-004    │  │  C-005                │   │
│  │  ListenerStore│  │  EventQ.  │  │  ErrorHandler         │   │
│  │  (监听器存储)  │  │  (事件队列)│  │  (异常处理)            │   │
│  └───────────────┘  └──────────┘  └──────────┬─────────────┘   │
│                                              │                 │
└──────────────────────────────────────────────┼─────────────────┘
                                               │
┌──────────────────────────────────────────────┼─────────────────┐
│                        存储层                 │                 │
│                                              │                 │
│                                    ┌─────────▼─────────┐       │
│                                    │  C-006            │       │
│                                    │  DeadLetterQueue  │       │
│                                    │  (死信队列)        │       │
│                                    └───────────────────┘       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 数据流

1. **注册流**：用户 → `Dispatcher.on()` / `register()` → `ListenerStore` 存储监听器
2. **分发流**：用户 → `Dispatcher.emit(event)` → `ListenerStore.resolve_order()` 获取执行计划 → 执行监听器 → 合并返回值
3. **递归流**：监听器内 `emit()` → `EventQueue` 排队 → Dispatcher 消费队列
4. **异常流**：监听器异常 → `ErrorHandler` 按策略处理 → 可选进入 `DeadLetterQueue`
5. **停机流**：用户 → `Dispatcher.shutdown()` → 拒绝新事件 → 等待队列排空 → 清理资源

## 2. 技术栈

| 层 | 技术 | 版本 | 理由 |
|----|------|------|------|
| 运行时 | CPython | 3.12+ | PEP 585 泛型语法、现代语言特性 |
| 异步运行时 | asyncio | 标准库 | Python 官方异步支持，零额外依赖 |
| 数据验证 | pydantic | ^2.0 | Event 字段验证、类型安全、性能优秀 |
| 日志 | loguru | ^0.7 | 零配置、结构化日志、简单易用 |
| 包管理 | uv | latest | 快速解析和安装，现代 Python 包管理 |
| 测试 | pytest | ^8.0 | 生态丰富、插件支持 |
| 异步测试 | pytest-asyncio | ^0.24 | pytest 的 asyncio 测试支持 |
| 格式化 | ruff format | latest | 高速格式化 |
| 静态检查 | ruff check | latest | 高速 lint，集成 isort 规则 |

## 3. 组件清单

### C-001: Event（事件模型）

- **职责**：事件基类定义，提供 `event_id`、`timestamp` 元数据字段，依赖 pydantic 进行用户自定义字段的验证
- **覆盖需求**：F-001
- **依赖**：无（叶子节点）
- **对外暴露**：`Event` 基类（用户继承使用）
- **关键设计**：
  - 继承 `pydantic.BaseModel`
  - `event_id` 和 `timestamp` 为框架保留字段，构造时不可由用户传入，由 Dispatcher 在 `emit()` 时通过赋值注入
  - 用户通过子类添加自定义数据字段
- **文件**：`src/eventd/event.py`

### C-002: Dispatcher（事件管理器）

- **职责**：事件分发核心。提供 `on()`、`register()`、`unregister()`、`emit()`、`shutdown()` 等公开 API。协调 ListenerStore、EventQueue、ErrorHandler 完成事件的注册、分发、异常处理和生命周期管理
- **作用说明**：Dispatcher 是用户与框架交互的唯一入口。用户通过 Dispatcher 注册监听器、提交事件、配置异常策略和控制生命周期。Dispatcher 本身不直接处理存储、队列和异常，而是将这些职责委托给内部服务层组件
- **覆盖需求**：F-002, F-003, F-003A, F-004, F-005, F-008, F-008-SYNC, F-009（配置入口）, F-010（日志调用点）
- **依赖**：C-001, C-003, C-004, C-005
- **对外暴露**：`BaseDispatcher`（抽象基类）、`Dispatcher`、`AsyncDispatcher`、`default_dispatcher`（模块级 `Dispatcher` 实例）
- **关键设计**：
  - `BaseDispatcher`（抽象基类）：封装共用逻辑
    - 构造参数管理（`error_strategy`、`retry_config`、`dead_letter_enabled`、`queue_max_size`、`event_id_generator`、`timestamp_generator`）
    - 持有 `ListenerStore`、`ErrorHandler` 实例
    - 注册/取消注册逻辑（`on()`、`register()`、`unregister()` 委托给 `ListenerStore`）
    - shutdown 状态管理（`_is_shutting_down` 标志）
    - `event_id` / `timestamp` 生成逻辑
  - `Dispatcher(BaseDispatcher)`：
    - `emit()` — 同步阻塞执行，持有 `EventQueue`
    - `shutdown()` — 同步停机
  - `AsyncDispatcher(BaseDispatcher)`：
    - `async emit()` — 异步分层并行执行（同优先级 `gather`），持有 `AsyncEventQueue`
    - `async shutdown()` — 异步停机
  - `default_dispatcher`：模块级 `Dispatcher` 实例，在 `__init__.py` 中创建
- **文件**：`src/eventd/dispatcher.py`

### C-003: ListenerStore（监听器存储）

- **职责**：管理监听器的注册、取消注册、按事件类型 + MRO 查找、priority/after 拓扑排序
- **作用说明**：ListenerStore 是 Dispatcher 的内部组件，用户不直接访问。它负责维护事件类型到监听器列表的映射关系，并在 emit 时提供按 MRO、priority、after 排序后的分层执行计划
- **覆盖需求**：F-002, F-003, F-003A 的存储与查询逻辑
- **依赖**：无（叶子节点）
- **对外暴露**：`ListenerStore`、`ListenerEntry`
- **关键设计**：
  - `ListenerEntry`（`dataclass`）：
    - `callback: Callable` — 监听器回调函数
    - `priority: int` — 优先级（越大越高）
    - `after: list[Callable]` — 依赖的监听器回调函数列表（这些监听器必须在当前监听器之前执行）
    - `name: str` — 可选调试标签（默认为 `callback.__qualname__`），仅用于日志和错误消息，不参与业务逻辑
  - `ListenerStore`：
    - 内部数据结构：`dict[type[Event], list[ListenerEntry]]`
    - `add(event_types, entry)` — 注册监听器，执行 after 引用检查和循环依赖检测
    - `remove(event_types, callback)` — 取消注册，执行被依赖检查
    - `resolve_order(event_type) -> list[list[ListenerEntry]]` — 返回按 MRO 展开、按 priority 分层、after 拓扑排序后的分层执行计划。外层 list 为优先级层（从高到低），内层 list 为同层内按 after 拓扑排序后的执行序列
    - 循环依赖检测在 `add()` 时执行，抛出 `CyclicDependencyError`
    - after 引用未注册监听器的检测在 `add()` 时执行，抛出 `ValueError`
- **文件**：`src/eventd/listener.py`

### C-004: EventQueue（事件队列）

- **职责**：管理事件递归触发时的执行队列，控制递归深度
- **作用说明**：EventQueue 是 Dispatcher 的内部组件，用户不直接访问。当监听器在处理事件时触发新事件（递归事件），新事件不会立即递归执行，而是被放入 EventQueue 由 Dispatcher 在当前事件处理完毕后消费，从而避免栈溢出
- **覆盖需求**：F-006
- **依赖**：无（叶子节点）
- **对外暴露**：`EventQueue`、`AsyncEventQueue`
- **关键设计**：
  - `EventQueue`：
    - 内部数据结构：`collections.deque`（无 maxlen，手动检查 `max_size`）
    - `put(event)` — 追加事件，队列满时抛出 `QueueFullError`
    - `get() -> Event` — 取出下一个事件
    - `is_empty() -> bool`
    - `max_size: int | None` — `None` 表示无限制
  - `AsyncEventQueue`：
    - 内部数据结构：`asyncio.Queue`
    - `async put(event)` — 追加事件，队列满时阻塞等待
    - `async get() -> Event` — 取出下一个事件
    - `is_empty() -> bool`
    - `max_size: int | None` — `None` 表示无限制
  - 两个类不共享基类，因为同步/异步的满时行为和内部实现差异较大
- **文件**：`src/eventd/queue.py`

### C-005: ErrorHandler（异常处理）

- **职责**：根据策略（propagate / capture / retry）处理监听器执行异常
- **作用说明**：ErrorHandler 是 Dispatcher 的内部组件，由 `BaseDispatcher.__init__()` 在构造时创建，用户不直接访问。用户通过 Dispatcher 构造参数（`error_strategy`、`retry_config`、`dead_letter_enabled`）间接配置 ErrorHandler 的行为。Dispatcher 在 `emit()` 的 except 块中调用 `ErrorHandler.handle()`
- **覆盖需求**：F-009
- **依赖**：C-006（当 `dead_letter_enabled=True` 时将失败事件转入死信队列）
- **对外暴露**：`ErrorHandler`、`RetryConfig`、`ErrorStrategy`（`StrEnum`）
- **关键设计**：
  - `ErrorStrategy`（`StrEnum`）：
    - `PROPAGATE = "propagate"` — 直接 re-raise
    - `CAPTURE = "capture"` — 记录日志，返回异常信息
    - `RETRY = "retry"` — 立即重试
  - `ErrorHandler`：
    - 构造参数：`error_strategy: ErrorStrategy`、`retry_config`、`dead_letter_queue`（可选）
    - `handle(exception, event, listener, context: ExecutionContext) -> dict | None` — 按策略处理异常，返回处理结果
    - propagate 策略：直接 re-raise
    - capture 策略：记录日志，返回包含异常信息的字典
    - retry 策略：立即重试至 `max_retries`，支持 `should_retry` 条件判断，最终失败转入死信队列（如启用）或返回异常信息
  - `RetryConfig`（`dataclass`）：
    - `max_retries: int`
    - `should_retry: Callable[[Exception, ExecutionContext], bool] | None` — 可选条件函数
  - `ExecutionContext`（`dataclass`）：
    - `event: Event` — 当前处理的事件
    - `listener_name: str` — 监听器名称（`callback.__qualname__`）
    - `listener_callback: Callable` — 监听器回调函数
    - `retry_count: int` — 当前重试次数（0 = 首次执行）
    - `event_type: type[Event]` — 匹配的 MRO 层级事件类型
    - **构建时机**：仅在 `emit()` 的 except 块中构建，不预先创建（性能优化）
- **文件**：`src/eventd/error_handler.py`

### C-006: DeadLetterQueue（死信队列）

- **职责**：存储处理失败的事件及其上下文信息，提供读取和管理 API
- **作用说明**：DeadLetterQueue 是 ErrorHandler 的内部组件，用户通过 Dispatcher 间接访问。当监听器执行失败且异常策略为 capture/retry 时，失败的事件和上下文信息被存入 DeadLetterQueue，供用户后续查阅和处理
- **覆盖需求**：F-007
- **依赖**：无（叶子节点）
- **对外暴露**：`DeadLetterQueue`、`DeadLetterEntry`
- **关键设计**：
  - `DeadLetterEntry`（`dataclass`）：
    - `event: Event` — 失败的事件实例
    - `exception: Exception` — 导致失败的异常
    - `context: ExecutionContext` — 处理时的执行上下文
    - `timestamp: float` — 进入死信队列的时间
  - `DeadLetterQueue`：
    - 内部数据结构：`collections.deque`（无 maxlen，为未来多线程双端读取预留）
    - `put(entry)` — 添加条目
    - `get_all() -> list[DeadLetterEntry]` — 获取所有条目
    - `clear()` — 清空队列
    - `__len__() -> int` — 返回当前条目数
- **文件**：`src/eventd/dead_letter.py`

## 4. 依赖图

```
C-001 Event            ─── (无依赖)
C-003 ListenerStore    ─── (无依赖)
C-004 EventQueue       ─── (无依赖)
C-006 DeadLetterQueue  ─── (无依赖)
C-005 ErrorHandler     ─── C-006
C-002 Dispatcher       ─── C-001, C-003, C-004, C-005
```

拓扑排序后的实现顺序：

```
阶段 A（可并行）: C-001, C-003, C-004, C-006
阶段 B:           C-005 (依赖 C-006)
阶段 C:           C-002 (依赖 C-001, C-003, C-004, C-005)
```

## 5. 文件结构

```
src/eventd/
├── __init__.py          # 公开 API 导出 + default_dispatcher 实例
├── event.py             # C-001: Event 基类
├── dispatcher.py        # C-002: BaseDispatcher, Dispatcher, AsyncDispatcher
├── listener.py          # C-003: ListenerStore, ListenerEntry
├── queue.py             # C-004: EventQueue, AsyncEventQueue
├── error_handler.py     # C-005: ErrorHandler, RetryConfig, ErrorStrategy, ExecutionContext
├── dead_letter.py       # C-006: DeadLetterQueue, DeadLetterEntry
├── exceptions.py        # 自定义异常类 (EventdError, EventValidationError, CyclicDependencyError, KeyConflictError, QueueFullError, ShutdownTimeoutError)
└── _types.py            # 共享类型定义 (type aliases)
```

## 6. 未独立为组件的功能说明

| 功能 | 归属 | 理由 |
|------|------|------|
| F-010 日志记录 | 各组件内部直接调用 `loguru.logger` | 日志是横切关注点，不需要独立封装层 |
| MRO 解析逻辑 | C-003 `ListenerStore.resolve_order()` | 与监听器查询紧密耦合，无独立复用价值 |
| 自定义异常类 | `exceptions.py`（独立文件，非独立组件） | 异常类被多个组件共用，但本身无行为逻辑，不构成独立组件 |
| 共享类型定义 | `_types.py`（独立文件，非独立组件） | type alias 供多个组件引用，但无行为逻辑 |

---

## 7. 契约设计

> 本节为 `INFRASTRUCTURE.md` §3（HOW_TO.md §3）的产出。  
> 对每个组件的公开 API 使用契约式描述：签名、前置条件（Pre）、后置条件（Post）、不变量（Inv）、副作用、错误。

### C-001 API（Event）

#### `class Event(pydantic.BaseModel)`

事件基类。用户通过继承此类定义自定义事件。

**框架保留字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `event_id` | `int` | 事件唯一标识，由 Dispatcher 在 `emit()` 时注入（默认自增） |
| `timestamp` | `float` | 事件时间戳，由 Dispatcher 在 `emit()` 时注入（默认 `time.time()`） |

- Pre: 用户构造事件时**不可**传入 `event_id` 或 `timestamp`（框架保留字段）
- Post: 实例创建成功后，用户自定义字段已通过 pydantic 验证；`event_id` 和 `timestamp` 为 `None`（未注入状态）
- Inv: `Event` 实例创建后，用户自定义字段不可变（pydantic frozen model 或由用户决定）
- 副作用: 无
- 错误: `EventValidationError` — 用户自定义字段验证失败（捕获 pydantic `ValidationError` 后包装为 eventd 自有异常）

---

### C-002 API（Dispatcher）

#### `BaseDispatcher.__init__(self, *, error_strategy: ErrorStrategy = ErrorStrategy.PROPAGATE, retry_config: RetryConfig | None = None, dead_letter_enabled: bool = False, queue_max_size: int | None = None, event_id_generator: Callable[[], int] | None = None, timestamp_generator: Callable[[], float] | None = None) -> None`

构造事件管理器。

- Pre: `error_strategy` 为 `ErrorStrategy` 枚举值；当 `error_strategy == ErrorStrategy.RETRY` 时 `retry_config` 不得为 `None`；`queue_max_size` 为正整数或 `None`
- Post: 实例已创建，内部 `ListenerStore`、`ErrorHandler`、`EventQueue` 已初始化；`_is_shutting_down == False`
- Inv: 构造参数在实例生命周期内不可变
- 副作用: 无
- 错误: `ValueError` — `retry` 策略但未提供 `retry_config`，或 `queue_max_size` 非正整数

#### `BaseDispatcher.on(self, *event_types: type[Event], priority: int = 0, after: list[Callable] | None = None) -> Callable[[F], F]`

装饰器方式注册监听器。`F` 为被装饰函数的类型。

- Pre: `event_types` 中每个元素为 `Event` 的子类；回调函数类型与 Dispatcher 类型匹配（`Dispatcher` → 同步函数，`AsyncDispatcher` → 异步函数）；`after` 中引用的回调函数已注册到**任意事件**；`after` 不形成循环依赖
- Post: 回调函数已注册到所有指定事件类型；返回原始函数（不修改）
- Inv: 注册操作不影响已注册的其他监听器
- 副作用: 修改内部 `ListenerStore` 状态
- 错误:
  - `ValueError` — `after` 中引用了未注册的回调函数
  - `CyclicDependencyError` — `after` 形成循环依赖
  - `TypeError` — 回调函数类型与 Dispatcher 类型不匹配（同步 vs 异步）

#### `BaseDispatcher.register(self, event_types: type[Event] | list[type[Event]], callback: Callable, *, priority: int = 0, after: list[Callable] | None = None) -> None`

方法调用方式注册监听器。

- Pre: 同 `on()`
- Post: 同 `on()`，但无返回值
- Inv: 同 `on()`
- 副作用: 同 `on()`
- 错误: 同 `on()`

#### `BaseDispatcher.unregister(self, event_types: type[Event] | list[type[Event]] | None = None, callback: Callable | None = None) -> None`

取消监听器注册。支持四种调用模式：

| `event_types` | `callback` | 行为 |
|---------------|------------|------|
| 有 | 有 | 从指定事件类型中移除指定回调 |
| 有 | `None` | 从指定事件类型中移除**所有**监听器 |
| `None` | 有 | 从**所有**事件类型中移除指定回调 |
| `None` | `None` | 抛出 `ValueError`（无意义调用） |

- Pre: 当同时指定 `event_types` 和 `callback` 时，`callback` 必须已注册到所有指定的 `event_types`；移除操作不会导致其他监听器的 `after` 依赖失效
- Post: 对应的监听器已从相关事件类型的监听器列表中移除
- Inv: 取消注册不影响不相关的已注册监听器
- 副作用: 修改内部 `ListenerStore` 状态
- 错误:
  - `ValueError` — `event_types` 和 `callback` 均为 `None`
  - `ValueError` — `callback` 未注册到指定事件类型
  - `ValueError` — 移除操作导致其他监听器的 `after` 依赖失效

#### `Dispatcher.emit(self, event: Event) -> dict`

同步提交事件。

- Pre: `event` 为 `Event` 子类的实例；Dispatcher 未处于 shutdown 状态（`_is_shutting_down == False`）
- Post: `event.event_id` 和 `event.timestamp` 已被赋值；所有匹配的监听器已按 MRO 顺序、priority（高→低）、after 拓扑顺序依次执行；所有监听器返回的字典已合并为一个字典返回；如果监听器在执行中触发新事件，新事件已通过 `EventQueue` 排队并在当前 `emit` 调用内完成处理
- Inv: `event_id` 生成器的调用计数单调递增
- 副作用: 执行监听器（监听器可能产生任意副作用）；可能修改 `EventQueue` 和 `DeadLetterQueue` 状态；写日志
- 错误:
  - `TypeError` — 监听器返回非字典值
  - `KeyConflictError` — 合并返回字典时键冲突
  - `QueueFullError` — 递归事件导致队列超出 `max_size`
  - `ShutdownTimeoutError` — Dispatcher 已关闭
  - 监听器抛出的异常（当 `error_strategy == ErrorStrategy.PROPAGATE` 时）

#### `AsyncDispatcher.emit(self, event: Event) -> dict`

异步提交事件。

- Pre: 同 `Dispatcher.emit()`；当前处于 asyncio 事件循环中
- Post: 同 `Dispatcher.emit()`，但同优先级层的监听器通过 `asyncio.gather()` 并行执行，不同优先级层按顺序执行
- Inv: 同 `Dispatcher.emit()`
- 副作用: 同 `Dispatcher.emit()`
- 错误: 同 `Dispatcher.emit()`（`QueueFullError` 不适用于异步模式，异步队列满时阻塞等待）

#### `Dispatcher.shutdown(self, *, timeout: float | None = None) -> None`

同步优雅停机。

- Pre: Dispatcher 未处于 shutdown 状态
- Post: `_is_shutting_down == True`；所有正在执行的监听器已完成（包括递归触发的事件）；事件队列已排空；后续 `emit()` 调用将被拒绝
- Inv: shutdown 操作是幂等的（重复调用无副作用，但首次之后的调用因 Pre 不满足而报错 — 见下方错误说明）
- 副作用: 修改 `_is_shutting_down` 状态；清理内部资源
- 错误: `ShutdownTimeoutError` — 在 `timeout` 秒内未完成停机

#### `AsyncDispatcher.shutdown(self, *, timeout: float | None = None) -> None`

异步优雅停机。

- Pre: 同 `Dispatcher.shutdown()`；当前处于 asyncio 事件循环中
- Post: 同 `Dispatcher.shutdown()`
- Inv: 同 `Dispatcher.shutdown()`
- 副作用: 同 `Dispatcher.shutdown()`
- 错误: 同 `Dispatcher.shutdown()`

---

### C-003 API（ListenerStore）

#### `ListenerEntry`（dataclass）

```python
@dataclass
class ListenerEntry:
    callback: Callable
    priority: int
    after: list[Callable]
    name: str  # 可选调试标签，默认 callback.__qualname__
```

- Inv: `name` 默认为 `callback.__qualname__`，仅用于日志和错误消息，不参与业务逻辑；`priority` 越大优先级越高；`after` 为回调函数列表（可为空列表），引用必须在当前监听器之前执行的监听器

#### `ListenerStore.__init__(self) -> None`

构造空的监听器存储。

- Pre: 无
- Post: 内部存储为空
- Inv: 无
- 副作用: 无
- 错误: 无

#### `ListenerStore.add(self, event_types: list[type[Event]], entry: ListenerEntry) -> None`

注册监听器。

- Pre: `event_types` 中每个元素为 `Event` 的子类；`entry.after` 中引用的回调函数已注册到**任意事件类型**（不限于当前 `event_types`）；`entry.after` 加入后不形成循环依赖
- Post: `entry` 已添加到每个指定事件类型的监听器列表
- Inv: 同一 `callback` 可多次注册到不同事件类型；注册操作不修改已有条目
- 副作用: 修改内部存储
- 错误:
  - `ValueError` — `entry.after` 中引用了未注册的回调函数
  - `CyclicDependencyError` — `entry.after` 形成循环依赖

#### `ListenerStore.remove(self, event_types: list[type[Event]] | None, callback: Callable | None) -> None`

取消注册监听器。支持与 `BaseDispatcher.unregister()` 相同的四种调用模式。

- Pre: 当同时指定 `event_types` 和 `callback` 时，`callback` 已注册到所有指定的 `event_types`；移除后不会导致其他监听器的 `after` 依赖失效
- Post: 对应的 `ListenerEntry` 已从相关事件类型的监听器列表中移除
- Inv: 移除操作不影响不相关的已注册条目
- 副作用: 修改内部存储
- 错误:
  - `ValueError` — `event_types` 和 `callback` 均为 `None`
  - `ValueError` — `callback` 未注册到指定事件类型
  - `ValueError` — 移除导致其他监听器的 `after` 依赖失效

#### `ListenerStore.resolve_order(self, event_type: type[Event]) -> list[list[ListenerEntry]]`

按 MRO、priority、after 排序，返回分层执行计划。

- Pre: `event_type` 为 `Event` 的子类
- Post: 返回值为二维列表。外层按优先级从高到低排列，内层为同优先级的监听器按 after 拓扑排序后的执行序列。所有通过 MRO 匹配的监听器均包含在内（不去重）
- Inv: 返回值为只读快照（不影响内部状态）；同一 `event_type` 在注册状态不变时，多次调用返回相同结果
- 副作用: 无
- 错误:
  - `CyclicDependencyError` — after 依赖在排序时检测到循环（理论上不应发生，因为 `add()` 时已检测，此处为防御性检查）

---

### C-004 API（EventQueue）

#### `EventQueue.__init__(self, max_size: int | None = None) -> None`

构造同步事件队列。

- Pre: `max_size` 为正整数或 `None`
- Post: 队列为空
- Inv: `max_size` 在生命周期内不可变
- 副作用: 无
- 错误: 无

#### `EventQueue.put(self, event: Event) -> None`

追加事件到队列。

- Pre: 队列未满（`len(queue) < max_size`，或 `max_size is None`）
- Post: `event` 已追加到队列尾部；队列长度增加 1
- Inv: FIFO 顺序保持
- 副作用: 修改内部 `deque`
- 错误: `QueueFullError` — 队列已满

#### `EventQueue.get(self) -> Event`

取出队列头部事件。

- Pre: 队列非空
- Post: 返回队列头部事件；队列长度减少 1
- Inv: FIFO 顺序保持
- 副作用: 修改内部 `deque`
- 错误: `IndexError` — 队列为空（调用方应先检查 `is_empty()`）

#### `EventQueue.is_empty(self) -> bool`

检查队列是否为空。

- Pre: 无
- Post: 返回 `True` 当且仅当队列长度为 0
- Inv: 不修改队列状态
- 副作用: 无
- 错误: 无

#### `AsyncEventQueue.__init__(self, max_size: int | None = None) -> None`

构造异步事件队列。

- Pre: `max_size` 为正整数或 `None`（`None` 时 `asyncio.Queue` 使用 `maxsize=0` 即无限制）
- Post: 队列为空
- Inv: `max_size` 在生命周期内不可变
- 副作用: 无
- 错误: 无

#### `async AsyncEventQueue.put(self, event: Event) -> None`

追加事件到队列（异步）。

- Pre: 当前处于 asyncio 事件循环中
- Post: `event` 已追加到队列尾部
- Inv: FIFO 顺序保持
- 副作用: 修改内部队列；队列满时阻塞当前协程直到有空间
- 错误: 无（满时阻塞，不抛异常）

#### `async AsyncEventQueue.get(self) -> Event`

取出队列头部事件（异步）。

- Pre: 当前处于 asyncio 事件循环中
- Post: 返回队列头部事件；队列长度减少 1
- Inv: FIFO 顺序保持
- 副作用: 修改内部队列；队列空时阻塞当前协程直到有事件
- 错误: 无（空时阻塞，不抛异常）

#### `AsyncEventQueue.is_empty(self) -> bool`

检查队列是否为空。

- Pre: 无
- Post: 返回 `True` 当且仅当队列长度为 0
- Inv: 不修改队列状态
- 副作用: 无
- 错误: 无

---

### C-005 API（ErrorHandler）

#### `ErrorStrategy`（StrEnum）

```python
class ErrorStrategy(enum.StrEnum):
    PROPAGATE = "propagate"
    CAPTURE = "capture"
    RETRY = "retry"
```

- Inv: 枚举值不可扩展

#### `ExecutionContext`（dataclass）

```python
@dataclass
class ExecutionContext:
    event: Event
    listener_name: str        # callback.__qualname__
    listener_callback: Callable
    retry_count: int          # 0 = 首次执行
    event_type: type[Event]   # 匹配的 MRO 层级事件类型
```

- Inv: 所有字段在创建后不可变（frozen dataclass）
- **构建时机**：仅在 `emit()` 的 except 块中构建 `ExecutionContext` 实例，不预先创建（性能优化——正常路径零开销）

#### `RetryConfig`（dataclass）

```python
@dataclass
class RetryConfig:
    max_retries: int
    should_retry: Callable[[Exception, ExecutionContext], bool] | None = None
```

- Inv: `max_retries >= 1`；`should_retry` 为 `None` 时表示始终重试（直到达到 `max_retries`）

#### `ErrorHandler.__init__(self, *, error_strategy: ErrorStrategy = ErrorStrategy.PROPAGATE, retry_config: RetryConfig | None = None, dead_letter_queue: DeadLetterQueue | None = None) -> None`

构造异常处理器。

- Pre: 当 `error_strategy == ErrorStrategy.RETRY` 时 `retry_config` 不得为 `None`
- Post: 实例已创建，策略已配置
- Inv: 策略在生命周期内不可变
- 副作用: 无
- 错误: `ValueError` — `retry` 策略但未提供 `retry_config`

#### `ErrorHandler.handle(self, exception: Exception, event: Event, listener: ListenerEntry, context: ExecutionContext) -> dict | None`

按策略处理监听器异常。

- Pre: `exception` 为监听器执行时抛出的异常；`event` 为当前处理的事件；`listener` 为抛出异常的监听器；`context` 为在 except 块中构建的执行上下文
- Post:
  - propagate: 异常被 re-raise，此方法不返回
  - capture: 返回包含异常信息的字典（如 `{"__error__": {"listener": name, "exception": str(exception)}}`)，日志已记录
  - retry: 立即重试监听器执行至 `max_retries` 次；若 `should_retry` 返回 `False` 或重试耗尽，转入死信队列（如启用）并返回异常信息字典；若重试成功，返回监听器的正常返回值
- Inv: propagate 策略下此方法永远不正常返回；capture 和 retry 策略下此方法始终返回字典
- 副作用: retry 策略会重新执行监听器（监听器可能产生副作用）；可能向 `DeadLetterQueue` 写入条目；写日志
- 错误: propagate 策略下 re-raise 原始异常；retry 策略下如果重试的监听器抛出非预期异常且 `should_retry` 返回 `False`，异常信息被捕获并返回

---

### C-006 API（DeadLetterQueue）

#### `DeadLetterEntry`（dataclass）

```python
@dataclass
class DeadLetterEntry:
    event: Event
    exception: Exception
    context: ExecutionContext
    timestamp: float
```

- Inv: 所有字段在创建后不可变（frozen dataclass）

#### `DeadLetterQueue.__init__(self) -> None`

构造空的死信队列。

- Pre: 无
- Post: 队列为空；`len(self) == 0`
- Inv: 无
- 副作用: 无
- 错误: 无

#### `DeadLetterQueue.put(self, entry: DeadLetterEntry) -> None`

添加死信条目。

- Pre: `entry` 为有效的 `DeadLetterEntry` 实例
- Post: `entry` 已追加到队列尾部；`len(self)` 增加 1
- Inv: 追加顺序保持（FIFO）
- 副作用: 修改内部 `deque`
- 错误: 无

#### `DeadLetterQueue.get_all(self) -> list[DeadLetterEntry]`

获取所有死信条目。

- Pre: 无
- Post: 返回所有条目的列表副本（修改返回值不影响内部状态）
- Inv: 不修改内部状态
- 副作用: 无
- 错误: 无

#### `DeadLetterQueue.clear(self) -> None`

清空死信队列。

- Pre: 无
- Post: 队列为空；`len(self) == 0`
- Inv: 无
- 副作用: 修改内部存储
- 错误: 无

#### `DeadLetterQueue.__len__(self) -> int`

返回当前条目数。

- Pre: 无
- Post: 返回值 ≥ 0
- Inv: 返回值等于 `put()` 调用次数减去 `clear()` 造成的清除量
- 副作用: 无
- 错误: 无

---

### 异常类清单（`exceptions.py`）

| 异常类 | 继承自 | 触发场景 |
|--------|--------|----------|
| `EventdError` | `Exception` | eventd 所有自定义异常的基类 |
| `EventValidationError` | `EventdError`, `ValueError` | 用户自定义字段验证失败（包装 pydantic `ValidationError`） |
| `CyclicDependencyError` | `EventdError`, `ValueError` | `after` 依赖形成循环（注册时 / resolve_order 时） |
| `KeyConflictError` | `EventdError`, `ValueError` | 合并监听器返回字典时键冲突 |
| `QueueFullError` | `EventdError`, `RuntimeError` | 同步事件队列超出 `max_size` |
| `ShutdownTimeoutError` | `EventdError`, `TimeoutError` | 优雅停机超时 |

---

## 8. 内部逻辑设计

> 本节为 `INFRASTRUCTURE.md` §4（HOW_TO.md §4）的产出。  
> 对每个组件的公开 API 推导其实现所需的内部方法、算法和伪代码。标注时间/空间复杂度（如适用）。

### C-001 内部逻辑（Event）

#### 8.1.1 框架保留字段保护

**目标**：用户构造 `Event` 子类时，不得传入 `event_id` 或 `timestamp`。这两个字段由 Dispatcher 在 `emit()` 时赋值。

**实现方案**：利用 pydantic `model_validator(mode="before")` 在字段解析前拦截。

```python
# 伪代码
class Event(pydantic.BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: int | None = Field(default=None, init=False)
    timestamp: float | None = Field(default=None, init=False)

    @model_validator(mode="before")
    @classmethod
    def _reject_reserved_fields(cls, data: dict) -> dict:
        # pydantic v2 的 mode="before" 在字段解析前执行
        # data 为用户传入的原始字典
        reserved = {"event_id", "timestamp"}
        provided = reserved & set(data.keys())
        if provided:
            raise EventValidationError(
                f"保留字段不可由用户传入: {provided}"
            )
        return data
```

**关键点**：

- `init=False`：pydantic 在 `__init__` 签名中不暴露该字段，但如果用户通过 `dict` 或 `**kwargs` 传入仍可绕过，因此需要 `model_validator` 主动拦截
- `frozen=True`：Event 实例创建后所有字段不可变（pydantic 保证）。但 Dispatcher 需要在 `emit()` 时赋值 `event_id` 和 `timestamp`，使用 `model_config` 中的 `frozen=True` 后需通过 `object.__setattr__()` 绕过 frozen 保护进行一次性注入（见 C-002 `_inject_metadata`）

#### 8.1.2 EventValidationError 包装

**目标**：用户自定义字段验证失败时，将 pydantic `ValidationError` 包装为 `EventValidationError`。

**实现方案**：在 `Event.__init_subclass__` 中无法拦截实例化，因此在 `__init__` 级别处理。使用 `__init_subclass__` 不合适（它在类定义时调用，非实例化时）。正确方案是利用 pydantic 自身的 validator 机制——pydantic 的 `ValidationError` 会在实例化时自动抛出，我们需要在调用侧捕获并包装。

**两种可选方案**：

1. **方案 A（推荐）**：在 `Event.__init__` 中 `try/except` 包装

```python
# 伪代码
class Event(pydantic.BaseModel):
    def __init__(self, **data):
        try:
            super().__init__(**data)
        except pydantic.ValidationError as e:
            raise EventValidationError(str(e)) from e
```

2. **方案 B**：不在 Event 内包装，而是在调用侧（Dispatcher.emit / 用户代码）捕获

**选择方案 A 的理由**：Event 是用户直接实例化的类，在 Event 内部包装可以保证无论用户在哪里创建 Event 实例都能得到统一的 `EventValidationError`，无需 Dispatcher 额外处理。

---

### C-002 内部逻辑（Dispatcher）

#### 8.2.1 `_inject_metadata(self, event: Event) -> None`

**目标**：在 `emit()` 时为事件注入 `event_id` 和 `timestamp`。

```python
# 伪代码
def _inject_metadata(self, event: Event) -> None:
    # frozen model 需通过 object.__setattr__ 绕过保护
    object.__setattr__(event, "event_id", self._event_id_generator())
    object.__setattr__(event, "timestamp", self._timestamp_generator())
```

**复杂度**：O(1)

**关键点**：

- `event_id_generator` 默认为自增计数器（`itertools.count().__next__` 或等价实现）
- `timestamp_generator` 默认为 `time.time`
- 用户可通过构造参数替换生成器

#### 8.2.2 `Dispatcher.emit()` 内部流程

**目标**：同步分发事件，处理递归事件队列。

```python
# 伪代码
def emit(self, event: Event) -> dict:
    # 1. 状态检查
    if self._is_shutting_down:
        raise ShutdownTimeoutError("Dispatcher 已关闭")

    # 2. 注入元数据
    self._inject_metadata(event)

    # 3. 判断是否为递归调用
    #    使用 _is_emitting 标志区分首次调用和递归调用
    if self._is_emitting:
        # 递归调用：入队，由外层 emit 消费
        self._queue.put(event)
        return {}

    # 4. 首次调用：进入分发循环
    self._is_emitting = True
    merged_result: dict = {}
    try:
        # 处理当前事件
        result = self._dispatch_single(event)
        _merge_dict(merged_result, result)

        # 消费队列中的递归事件
        while not self._queue.is_empty():
            queued_event = self._queue.get()
            result = self._dispatch_single(queued_event)
            _merge_dict(merged_result, result)
    finally:
        self._is_emitting = False

    return merged_result
```

#### 8.2.3 `_dispatch_single(self, event: Event) -> dict`（内部方法）

**目标**：分发单个事件给所有匹配的监听器。

```python
# 伪代码
def _dispatch_single(self, event: Event) -> dict:
    # 1. 获取分层执行计划
    layers = self._listener_store.resolve_order(type(event))

    merged_result: dict = {}
    # 2. 按优先级层依次执行
    for layer in layers:
        for entry in layer:
            result = self._execute_listener(entry, event)
            if result is not None:
                _merge_dict(merged_result, result)

    return merged_result
```

#### 8.2.4 `_execute_listener(self, entry: ListenerEntry, event: Event) -> dict | None`（内部方法）

**目标**：执行单个监听器，处理返回值验证和异常。

```python
# 伪代码
def _execute_listener(self, entry: ListenerEntry, event: Event) -> dict | None:
    try:
        result = entry.callback(event)
    except Exception as exc:
        # 构建 ExecutionContext（仅在异常时构建）
        ctx = ExecutionContext(
            event=event,
            listener_name=entry.name,
            listener_callback=entry.callback,
            retry_count=0,
            event_type=type(event),  # 实际应为 resolve_order 返回时确定的 MRO 层级
        )
        return self._error_handler.handle(exc, event, entry, ctx)

    # 返回值验证
    if result is None:
        return None
    if not isinstance(result, dict):
        raise TypeError(
            f"监听器 {entry.name} 返回非字典值: {type(result)}"
        )
    return result
```

**备注**：`event_type` 字段应为 `resolve_order` 返回时确定的匹配 MRO 层级，而非 `type(event)`。实际实现中需要将 MRO 匹配类型从 `resolve_order` 传递到此方法。具体方案在实现阶段确定（可选方案：`resolve_order` 返回包含 `event_type` 的元组，或者 `_dispatch_single` 传递额外参数）。

#### 8.2.5 `_merge_dict(target: dict, source: dict) -> None`（模块级辅助函数）

**目标**：合并监听器返回的字典，键冲突时抛出 `KeyConflictError`。

```python
# 伪代码
def _merge_dict(target: dict, source: dict) -> None:
    conflicts = set(target.keys()) & set(source.keys())
    if conflicts:
        raise KeyConflictError(f"键冲突: {conflicts}")
    target.update(source)
```

**复杂度**：O(min(|target|, |source|)) 用于冲突检测

#### 8.2.6 `AsyncDispatcher.emit()` 内部流程

**目标**：异步分发事件，同优先级层通过 `asyncio.gather()` 并行执行。

```python
# 伪代码
async def emit(self, event: Event) -> dict:
    # 1-3 同 Dispatcher.emit()（状态检查、注入、递归判断）
    ...

    # 4. 首次调用：进入分发循环
    self._is_emitting = True
    merged_result: dict = {}
    try:
        result = await self._dispatch_single(event)
        _merge_dict(merged_result, result)

        while not self._queue.is_empty():
            queued_event = await self._queue.get()
            result = await self._dispatch_single(queued_event)
            _merge_dict(merged_result, result)
    finally:
        self._is_emitting = False

    return merged_result
```

#### 8.2.7 `AsyncDispatcher._dispatch_single()` 内部差异

```python
# 伪代码 — 与同步版的唯一区别：同层 gather
async def _dispatch_single(self, event: Event) -> dict:
    layers = self._listener_store.resolve_order(type(event))

    merged_result: dict = {}
    for layer in layers:
        # 同优先级层并行执行
        results = await asyncio.gather(
            *(self._execute_listener(entry, event) for entry in layer)
        )
        for result in results:
            if result is not None:
                _merge_dict(merged_result, result)

    return merged_result
```

#### 8.2.8 `Dispatcher.shutdown()` / `AsyncDispatcher.shutdown()` 内部流程

```python
# 伪代码（同步版）
def shutdown(self, *, timeout: float | None = None) -> None:
    if self._is_shutting_down:
        return  # 幂等：已关闭则直接返回

    self._is_shutting_down = True

    # 等待当前 emit 完成（如果有正在执行的 emit）
    # 同步模式下 emit 是阻塞的，shutdown 只能在 emit 外部调用
    # 因此到达此处时 _is_emitting 一定为 False（单线程保证）
    # timeout 主要用于异步版本，同步版可选保留参数签名以保持对称

    # 清理队列中残余事件（如有）
    while not self._queue.is_empty():
        _ = self._queue.get()
```

```python
# 伪代码（异步版）
async def shutdown(self, *, timeout: float | None = None) -> None:
    if self._is_shutting_down:
        return

    self._is_shutting_down = True

    # 等待队列排空
    if timeout is not None:
        try:
            await asyncio.wait_for(self._drain_queue(), timeout=timeout)
        except asyncio.TimeoutError:
            raise ShutdownTimeoutError(
                f"停机超时: {timeout}s 内未完成"
            ) from None
    else:
        await self._drain_queue()

async def _drain_queue(self) -> None:
    while not self._queue.is_empty():
        event = await self._queue.get()
        await self._dispatch_single(event)
```

**关键点**：

- `shutdown` 是幂等的：首次调用后设置 `_is_shutting_down = True`，后续调用直接返回（不抛异常）
- 同步版本中 `timeout` 参数实际无意义（单线程不存在等待问题），但保留签名以保持同步/异步 API 对称
- 异步版本使用 `asyncio.wait_for` 实现超时控制

#### 8.2.9 `_is_emitting` 递归保护机制

**目标**：防止监听器中 `emit()` 导致无限递归。

**工作原理**：

1. 首次 `emit()` 调用设置 `_is_emitting = True`
2. 如果监听器在处理中再次调用 `emit()`，检测到 `_is_emitting == True`，将新事件放入 `EventQueue` 而非立即递归
3. 首次 `emit()` 在处理完当前事件后，循环消费队列中的所有递归事件
4. 队列为空后，设置 `_is_emitting = False`

**同步模式下的单线程保证**：由于 Python GIL 和同步执行模型，`_is_emitting` 不需要加锁。

**异步模式下的协程安全**：单个 `AsyncDispatcher` 实例在同一事件循环中使用。`_is_emitting` 在 `await` 点之间不会被其他协程修改（因为协程切换仅发生在 `await` 点）。但如果两个独立的 `emit()` 协程并发调用（如 `asyncio.gather(d.emit(e1), d.emit(e2))`），需要额外考虑。

**并发 emit 的处理**（草稿，待实现阶段确定）：

- 方案 A：使用 `asyncio.Lock` 保证同一时间只有一个 `emit` 在执行
- 方案 B：允许并发，每次 `emit` 使用独立的队列实例

> **悬置项**：异步并发 `emit` 的确切行为需在实现阶段验证。建议实现时先用 `asyncio.Lock` 串行化，如性能不可接受再考虑方案 B。记录至 TODO.md。

---

### C-003 内部逻辑（ListenerStore）

#### 8.3.1 内部数据结构

```python
# 伪代码
class ListenerStore:
    def __init__(self):
        # 事件类型 → 监听器列表
        self._store: dict[type[Event], list[ListenerEntry]] = {}
        # callback → 已注册的事件类型集合（用于反查）
        self._callback_events: dict[Callable, set[type[Event]]] = {}
```

**`_callback_events` 的作用**：

- `remove(None, callback)` 需要查找 callback 注册在哪些事件上 → O(1) 查找
- `add()` 时检查 `after` 引用的 callback 是否已注册 → O(1) 查找
- 维护成本：`add()` 和 `remove()` 时同步更新

#### 8.3.2 `resolve_order()` 算法

**输入**：`event_type: type[Event]`

**输出**：`list[list[ListenerEntry]]`（外层 = 优先级层，内层 = 拓扑排序后的执行序列）

**算法步骤**：

```
1. MRO 展开
   对 event_type.__mro__ 中每个类型 T（排除 object 和非 Event 的类型）：
     收集 self._store[T] 中的所有 ListenerEntry

2. 去重
   同一 callback 可能通过不同 MRO 层级匹配多次，保留所有匹配（不去重）
   — 这是 §7 契约的 Post 条件要求

3. 按 priority 分组
   将所有收集到的 ListenerEntry 按 priority 值分组
   排序方式：priority 值从大到小

4. 组内拓扑排序
   对每个优先级组：
     构建 DAG：
       节点 = 该组内的 ListenerEntry
       边 = entry.after 中引用的 callback → 引用方
       （即如果 A.after 包含 B.callback，则 B → A）
     执行拓扑排序（Kahn 算法）
     如果检测到环 → 抛出 CyclicDependencyError（防御性）

5. 组合
   将各优先级组的拓扑排序结果组合为二维列表返回
```

**复杂度**：

- 时间：O(L × M) 其中 L = 匹配的监听器总数，M = MRO 链长度（通常 ≤ 5）
- 拓扑排序：O(V + E) 其中 V = 单组内监听器数，E = after 边数
- 总体：O(M × L + V + E)，实际项目中 L、V、E 均很小

#### 8.3.3 组内拓扑排序（Kahn 算法）

```python
# 伪代码
def _topological_sort(entries: list[ListenerEntry]) -> list[ListenerEntry]:
    # 构建 callback → entry 的映射
    callback_to_entry: dict[Callable, ListenerEntry] = {
        e.callback: e for e in entries
    }

    # 计算入度
    in_degree: dict[Callable, int] = {e.callback: 0 for e in entries}
    for entry in entries:
        for dep in entry.after:
            if dep in callback_to_entry:
                # dep → entry 的边（dep 必须在 entry 之前）
                in_degree[entry.callback] += 1

    # Kahn 算法
    queue = deque(
        e for e in entries if in_degree[e.callback] == 0
    )
    result: list[ListenerEntry] = []

    while queue:
        current = queue.popleft()
        result.append(current)
        # 找到所有依赖 current 的 entry
        for entry in entries:
            if current.callback in entry.after:
                in_degree[entry.callback] -= 1
                if in_degree[entry.callback] == 0:
                    queue.append(entry)

    if len(result) != len(entries):
        raise CyclicDependencyError("检测到循环依赖")

    return result
```

**注意**：`entry.after` 中的 callback 可能不在当前优先级组内（注册在不同优先级或不同事件类型上）。对于不在当前组内的 `after` 引用，跳过即可（这些依赖在其他优先级层中已经被满足，因为高优先级层先执行）。

#### 8.3.4 `add()` 时的循环依赖检测

**目标**：在注册时检测 `after` 是否引入循环依赖，避免 `resolve_order()` 时才发现。

```python
# 伪代码
def add(self, event_types: list[type[Event]], entry: ListenerEntry) -> None:
    # 1. 检查 after 引用的回调是否已注册
    for dep in entry.after:
        if dep not in self._callback_events:
            raise ValueError(f"after 引用了未注册的回调: {dep.__qualname__}")

    # 2. 循环依赖检测（DFS）
    #    从新 entry 出发，沿 after 链向上遍历，检查是否能回到 entry 自身
    self._check_cycle(entry)

    # 3. 添加到存储
    for event_type in event_types:
        if event_type not in self._store:
            self._store[event_type] = []
        self._store[event_type].append(entry)

    # 4. 更新反查索引
    if entry.callback not in self._callback_events:
        self._callback_events[entry.callback] = set()
    self._callback_events[entry.callback].update(event_types)
```

#### 8.3.5 循环依赖检测（DFS）

```python
# 伪代码
def _check_cycle(self, new_entry: ListenerEntry) -> None:
    """从 new_entry 的 after 依赖出发，DFS 检查是否存在回到 new_entry 的环。"""
    visited: set[Callable] = set()

    def dfs(callback: Callable) -> bool:
        if callback == new_entry.callback:
            return True  # 找到环
        if callback in visited:
            return False
        visited.add(callback)

        # 查找 callback 对应的 entry 的 after 列表
        # 需要从所有事件类型中搜索该 callback 的 entry
        for entries in self._store.values():
            for entry in entries:
                if entry.callback == callback:
                    for dep in entry.after:
                        if dfs(dep):
                            return True
                    break  # 同一 callback 的 after 列表相同，找到一个即可
        return False

    for dep in new_entry.after:
        if dfs(dep):
            raise CyclicDependencyError(
                f"检测到循环依赖: {new_entry.name} -> ... -> {new_entry.name}"
            )
```

**复杂度**：O(V + E)，V = 已注册的 callback 总数，E = after 边总数

#### 8.3.6 `remove()` 时的被依赖检查

**目标**：移除监听器前检查是否有其他监听器依赖它（通过 `after` 引用）。

```python
# 伪代码
def remove(self, event_types: list[type[Event]] | None, callback: Callable | None) -> None:
    # 1. 参数校验
    if event_types is None and callback is None:
        raise ValueError("event_types 和 callback 不可同时为 None")

    # 2. 确定要移除的范围
    if event_types is not None and callback is not None:
        # 模式 1: 从指定事件移除指定回调
        targets = [(et, callback) for et in event_types]
    elif event_types is not None:
        # 模式 2: 从指定事件移除所有回调
        targets = [
            (et, e.callback)
            for et in event_types
            for e in self._store.get(et, [])
        ]
    else:
        # 模式 3: 从所有事件移除指定回调
        targets = [
            (et, callback)
            for et in self._callback_events.get(callback, set())
        ]

    # 3. 被依赖检查
    callbacks_to_remove = {cb for _, cb in targets}
    for entries in self._store.values():
        for entry in entries:
            if entry.callback not in callbacks_to_remove:
                # 此 entry 不在移除范围内
                deps_broken = set(entry.after) & callbacks_to_remove
                if deps_broken:
                    names = [d.__qualname__ for d in deps_broken]
                    raise ValueError(
                        f"无法移除: {names} 被 {entry.name} 的 after 依赖引用"
                    )

    # 4. 执行移除
    for et, cb in targets:
        if et in self._store:
            self._store[et] = [
                e for e in self._store[et] if e.callback != cb
            ]
            if not self._store[et]:
                del self._store[et]

    # 5. 更新反查索引
    for _, cb in targets:
        if cb in self._callback_events:
            for et, _ in targets:
                self._callback_events[cb].discard(et)
            if not self._callback_events[cb]:
                del self._callback_events[cb]
```

---

### C-004 内部逻辑（EventQueue）

#### 8.4.1 EventQueue（同步）

```python
# 伪代码
class EventQueue:
    def __init__(self, max_size: int | None = None):
        self._queue: deque[Event] = deque()
        self._max_size = max_size

    def put(self, event: Event) -> None:
        if self._max_size is not None and len(self._queue) >= self._max_size:
            raise QueueFullError(
                f"队列已满: {len(self._queue)}/{self._max_size}"
            )
        self._queue.append(event)

    def get(self) -> Event:
        return self._queue.popleft()  # 空时抛 IndexError

    def is_empty(self) -> bool:
        return len(self._queue) == 0
```

**复杂度**：`put` O(1)、`get` O(1)、`is_empty` O(1)

#### 8.4.2 AsyncEventQueue（异步）

```python
# 伪代码
class AsyncEventQueue:
    def __init__(self, max_size: int | None = None):
        maxsize = 0 if max_size is None else max_size
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)

    async def put(self, event: Event) -> None:
        await self._queue.put(event)  # 满时阻塞

    async def get(self) -> Event:
        return await self._queue.get()  # 空时阻塞

    def is_empty(self) -> bool:
        return self._queue.empty()
```

**复杂度**：与 `asyncio.Queue` 一致，所有操作 O(1) 摊还

**实现简洁性**：两个队列类均为薄封装，无复杂逻辑。

---

### C-005 内部逻辑（ErrorHandler）

#### 8.5.1 `handle()` 策略分发

```python
# 伪代码
class ErrorHandler:
    def handle(
        self,
        exception: Exception,
        event: Event,
        listener: ListenerEntry,
        context: ExecutionContext,
    ) -> dict | None:
        if self._strategy == ErrorStrategy.PROPAGATE:
            raise exception

        if self._strategy == ErrorStrategy.CAPTURE:
            return self._handle_capture(exception, event, listener, context)

        if self._strategy == ErrorStrategy.RETRY:
            return self._handle_retry(exception, event, listener, context)
```

#### 8.5.2 `_handle_capture()` 内部方法

```python
# 伪代码
def _handle_capture(
    self,
    exception: Exception,
    event: Event,
    listener: ListenerEntry,
    context: ExecutionContext,
) -> dict:
    logger.error(
        "监听器 {name} 处理事件 {event_id} 时抛出异常: {exc}",
        name=listener.name,
        event_id=event.event_id,
        exc=exception,
    )

    # 可选：写入死信队列
    if self._dead_letter_queue is not None:
        self._dead_letter_queue.put(
            DeadLetterEntry(
                event=event,
                exception=exception,
                context=context,
                timestamp=time.time(),
            )
        )

    return {
        "__error__": {
            "listener": listener.name,
            "exception": str(exception),
        }
    }
```

#### 8.5.3 `_handle_retry()` 内部方法

```python
# 伪代码
def _handle_retry(
    self,
    exception: Exception,
    event: Event,
    listener: ListenerEntry,
    context: ExecutionContext,
) -> dict | None:
    last_exception = exception

    for attempt in range(1, self._retry_config.max_retries + 1):
        # 构建新的 ExecutionContext（更新 retry_count）
        retry_ctx = ExecutionContext(
            event=context.event,
            listener_name=context.listener_name,
            listener_callback=context.listener_callback,
            retry_count=attempt,
            event_type=context.event_type,
        )

        # should_retry 判断
        if self._retry_config.should_retry is not None:
            if not self._retry_config.should_retry(last_exception, retry_ctx):
                logger.warning(
                    "should_retry 拒绝重试: {name}, attempt={attempt}",
                    name=listener.name,
                    attempt=attempt,
                )
                break

        # 执行重试
        try:
            result = listener.callback(event)
            logger.info(
                "重试成功: {name}, attempt={attempt}",
                name=listener.name,
                attempt=attempt,
            )
            return result  # 重试成功，返回正常结果
        except Exception as exc:
            last_exception = exc
            logger.warning(
                "重试失败: {name}, attempt={attempt}, exc={exc}",
                name=listener.name,
                attempt=attempt,
                exc=exc,
            )

    # 所有重试耗尽或 should_retry 拒绝
    logger.error(
        "重试耗尽: {name}, 最终异常: {exc}",
        name=listener.name,
        exc=last_exception,
    )

    # 写入死信队列（如启用）
    if self._dead_letter_queue is not None:
        final_ctx = ExecutionContext(
            event=context.event,
            listener_name=context.listener_name,
            listener_callback=context.listener_callback,
            retry_count=self._retry_config.max_retries,
            event_type=context.event_type,
        )
        self._dead_letter_queue.put(
            DeadLetterEntry(
                event=event,
                exception=last_exception,
                context=final_ctx,
                timestamp=time.time(),
            )
        )

    return {
        "__error__": {
            "listener": listener.name,
            "exception": str(last_exception),
        }
    }
```

**关键点**：

- `should_retry` 每次重试前调用，传入最新的异常和更新后的 `ExecutionContext`
- 重试成功则返回正常值，短路退出
- 重试耗尽后进入死信队列（如启用），返回错误字典
- 异步版本需要将 `listener.callback(event)` 替换为 `await listener.callback(event)`

---

### C-006 内部逻辑（DeadLetterQueue）

#### 8.6.1 完整实现

```python
# 伪代码
class DeadLetterQueue:
    def __init__(self):
        self._queue: deque[DeadLetterEntry] = deque()

    def put(self, entry: DeadLetterEntry) -> None:
        self._queue.append(entry)

    def get_all(self) -> list[DeadLetterEntry]:
        return list(self._queue)  # 返回副本

    def clear(self) -> None:
        self._queue.clear()

    def __len__(self) -> int:
        return len(self._queue)
```

**复杂度**：`put` O(1)、`get_all` O(n)、`clear` O(n)、`__len__` O(1)

**实现简洁性**：DeadLetterQueue 是最薄的封装层，所有操作直接委托给 `deque`。

---

### 8.7 悬置项与待确认事项

| 编号 | 事项 | 影响范围 | 建议处理时机 |
|------|------|----------|-------------|
| S-001 | 异步并发 `emit` 的行为（`asyncio.Lock` vs 独立队列） | C-002 AsyncDispatcher | 实现阶段确定，先用 Lock |
| S-002 | `resolve_order` 中 MRO 匹配层级信息如何传递到 `_execute_listener` 的 `ExecutionContext.event_type` | C-002, C-003 | 实现阶段确定（元组 or 额外参数） |
| S-003 | `_handle_retry` 的异步版本需 `await` 调用 | C-005 | 实现时处理（可能需要 `AsyncErrorHandler` 或策略模式） |
