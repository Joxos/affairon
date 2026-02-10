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
│  └───────────────┘    │    ├── SyncDispatcher                │   │
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
- **覆盖需求**：F-002, F-003, F-003A, F-004, F-005, F-008, F-008-SYNC, F-009（配置入口）, F-010（日志调用点）
- **依赖**：C-001, C-003, C-004, C-005
- **对外暴露**：`BaseDispatcher`（抽象基类）、`SyncDispatcher`、`AsyncDispatcher`、`default_dispatcher`（模块级 `SyncDispatcher` 实例）
- **关键设计**：
  - `BaseDispatcher`（抽象基类）：封装共用逻辑
    - 构造参数管理（`error_strategy`、`retry_config`、`dead_letter_enabled`、`queue_max_size`、`event_id_generator`、`timestamp_generator`）
    - 持有 `ListenerStore`、`ErrorHandler` 实例
    - 注册/取消注册逻辑（`on()`、`register()`、`unregister()` 委托给 `ListenerStore`）
    - shutdown 状态管理（`_is_shutting_down` 标志）
    - `event_id` / `timestamp` 生成逻辑
  - `SyncDispatcher(BaseDispatcher)`：
    - `emit()` — 同步阻塞执行，持有 `SyncEventQueue`
    - `shutdown()` — 同步停机
  - `AsyncDispatcher(BaseDispatcher)`：
    - `async emit()` — 异步分层并行执行（同优先级 `gather`），持有 `AsyncEventQueue`
    - `async shutdown()` — 异步停机
  - `default_dispatcher`：模块级 `SyncDispatcher` 实例，在 `__init__.py` 中创建
- **文件**：`src/eventd/dispatcher.py`

### C-003: ListenerStore（监听器存储）

- **职责**：管理监听器的注册、取消注册、按事件类型 + MRO 查找、priority/after 拓扑排序
- **覆盖需求**：F-002, F-003, F-003A 的存储与查询逻辑
- **依赖**：无（叶子节点）
- **对外暴露**：`ListenerStore`、`ListenerEntry`
- **关键设计**：
  - `ListenerEntry`（`dataclass`）：
    - `callback: Callable` — 监听器回调函数
    - `priority: int` — 优先级（越大越高）
    - `after: list[str]` — 依赖的监听器名称列表
    - `name: str` — 监听器名称（默认为函数名 `callback.__name__`）
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
- **覆盖需求**：F-006
- **依赖**：无（叶子节点）
- **对外暴露**：`SyncEventQueue`、`AsyncEventQueue`
- **关键设计**：
  - `SyncEventQueue`：
    - 内部数据结构：`list`（用作 FIFO 队列）
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
- **覆盖需求**：F-009
- **依赖**：C-006（当 `dead_letter_enabled=True` 时将失败事件转入死信队列）
- **对外暴露**：`ErrorHandler`、`RetryConfig`
- **关键设计**：
  - `ErrorHandler`：
    - 构造参数：`error_strategy`、`retry_config`、`dead_letter_queue`（可选）
    - `handle(exception, event, listener, context) -> ErrorResult` — 按策略处理异常，返回处理结果
    - propagate 策略：直接 re-raise
    - capture 策略：记录日志，返回包含异常信息的字典
    - retry 策略：立即重试至 `max_retries`，支持 `should_retry` 条件判断，最终失败转入死信队列（如启用）或返回异常信息
  - `RetryConfig`（`dataclass`）：
    - `max_retries: int`
    - `should_retry: Callable[[Exception, dict], bool] | None` — 可选条件函数
- **文件**：`src/eventd/error_handler.py`

### C-006: DeadLetterQueue（死信队列）

- **职责**：存储处理失败的事件及其上下文信息，提供读取和管理 API
- **覆盖需求**：F-007
- **依赖**：无（叶子节点）
- **对外暴露**：`DeadLetterQueue`、`DeadLetterEntry`
- **关键设计**：
  - `DeadLetterEntry`（`dataclass`）：
    - `event: Event` — 失败的事件实例
    - `exception: Exception` — 导致失败的异常
    - `context: dict` — 处理时的上下文信息（如监听器名称、重试次数等）
    - `timestamp: float` — 进入死信队列的时间
  - `DeadLetterQueue`：
    - 内部数据结构：`list[DeadLetterEntry]`
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
├── dispatcher.py        # C-002: BaseDispatcher, SyncDispatcher, AsyncDispatcher
├── listener.py          # C-003: ListenerStore, ListenerEntry
├── queue.py             # C-004: SyncEventQueue, AsyncEventQueue
├── error_handler.py     # C-005: ErrorHandler, RetryConfig
├── dead_letter.py       # C-006: DeadLetterQueue, DeadLetterEntry
├── exceptions.py        # 自定义异常类 (CyclicDependencyError, KeyConflictError, QueueFullError, ShutdownTimeoutError)
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
| `event_id` | `Any` | 事件唯一标识，由 Dispatcher 在 `emit()` 时注入 |
| `timestamp` | `Any` | 事件时间戳，由 Dispatcher 在 `emit()` 时注入 |

- Pre: 用户构造事件时**不可**传入 `event_id` 或 `timestamp`（框架保留字段）
- Post: 实例创建成功后，用户自定义字段已通过 pydantic 验证；`event_id` 和 `timestamp` 为 `None`（未注入状态）
- Inv: `Event` 实例创建后，用户自定义字段不可变（pydantic frozen model 或由用户决定）
- 副作用: 无
- 错误: `ValidationError`（pydantic 原生）— 用户自定义字段验证失败

---

### C-002 API（Dispatcher）

#### `BaseDispatcher.__init__(self, *, error_strategy: str = "propagate", retry_config: RetryConfig | None = None, dead_letter_enabled: bool = False, queue_max_size: int | None = None, event_id_generator: Callable[[], Any] | None = None, timestamp_generator: Callable[[], Any] | None = None) -> None`

构造事件管理器。

- Pre: `error_strategy` ∈ `{"propagate", "capture", "retry"}`；当 `error_strategy == "retry"` 时 `retry_config` 不得为 `None`；`queue_max_size` 为正整数或 `None`
- Post: 实例已创建，内部 `ListenerStore`、`ErrorHandler`、`EventQueue` 已初始化；`_is_shutting_down == False`
- Inv: 构造参数在实例生命周期内不可变
- 副作用: 无
- 错误: `ValueError` — `error_strategy` 非法，或 `retry` 策略但未提供 `retry_config`

#### `BaseDispatcher.on(self, *event_types: type[Event], priority: int = 0, after: list[str] | None = None) -> Callable[[F], F]`

装饰器方式注册监听器。`F` 为被装饰函数的类型。

- Pre: `event_types` 中每个元素为 `Event` 的子类；回调函数类型与 Dispatcher 类型匹配（`SyncDispatcher` → 同步函数，`AsyncDispatcher` → 异步函数）；`after` 中引用的监听器名称已注册到**任意事件**；`after` 不形成循环依赖
- Post: 回调函数已注册到所有指定事件类型；返回原始函数（不修改）
- Inv: 注册操作不影响已注册的其他监听器
- 副作用: 修改内部 `ListenerStore` 状态
- 错误:
  - `ValueError` — `after` 中引用了未注册的监听器名称
  - `CyclicDependencyError` — `after` 形成循环依赖
  - `TypeError` — 回调函数类型与 Dispatcher 类型不匹配（同步 vs 异步）

#### `BaseDispatcher.register(self, event_types: type[Event] | list[type[Event]], callback: Callable, *, priority: int = 0, after: list[str] | None = None) -> None`

方法调用方式注册监听器。

- Pre: 同 `on()`
- Post: 同 `on()`，但无返回值
- Inv: 同 `on()`
- 副作用: 同 `on()`
- 错误: 同 `on()`

#### `BaseDispatcher.unregister(self, event_types: type[Event] | list[type[Event]], callback: Callable) -> None`

取消监听器注册。

- Pre: `callback` 已注册到所有指定的 `event_types`；移除 `callback` 不会导致其他监听器的 `after` 依赖失效
- Post: `callback` 已从所有指定事件类型的监听器列表中移除
- Inv: 取消注册不影响其他已注册的监听器
- 副作用: 修改内部 `ListenerStore` 状态
- 错误:
  - `ValueError` — `callback` 未注册到指定事件类型
  - `ValueError` — 移除 `callback` 导致其他监听器的 `after` 依赖失效

#### `SyncDispatcher.emit(self, event: Event) -> dict`

同步提交事件。

- Pre: `event` 为 `Event` 子类的实例；Dispatcher 未处于 shutdown 状态（`_is_shutting_down == False`）
- Post: `event.event_id` 和 `event.timestamp` 已被赋值；所有匹配的监听器已按 MRO 顺序、priority（高→低）、after 拓扑顺序依次执行；所有监听器返回的字典已合并为一个字典返回；如果监听器在执行中触发新事件，新事件已通过 `SyncEventQueue` 排队并在当前 `emit` 调用内完成处理
- Inv: `event_id` 生成器的调用计数单调递增
- 副作用: 执行监听器（监听器可能产生任意副作用）；可能修改 `EventQueue` 和 `DeadLetterQueue` 状态；写日志
- 错误:
  - `TypeError` — 监听器返回非字典值
  - `KeyConflictError` — 合并返回字典时键冲突
  - `QueueFullError` — 递归事件导致队列超出 `max_size`
  - `ShutdownTimeoutError` — Dispatcher 已关闭
  - 监听器抛出的异常（当 `error_strategy == "propagate"` 时）

#### `AsyncDispatcher.emit(self, event: Event) -> dict`

异步提交事件。

- Pre: 同 `SyncDispatcher.emit()`；当前处于 asyncio 事件循环中
- Post: 同 `SyncDispatcher.emit()`，但同优先级层的监听器通过 `asyncio.gather()` 并行执行，不同优先级层按顺序执行
- Inv: 同 `SyncDispatcher.emit()`
- 副作用: 同 `SyncDispatcher.emit()`
- 错误: 同 `SyncDispatcher.emit()`（`QueueFullError` 不适用于异步模式，异步队列满时阻塞等待）

#### `SyncDispatcher.shutdown(self, *, timeout: float | None = None) -> None`

同步优雅停机。

- Pre: Dispatcher 未处于 shutdown 状态
- Post: `_is_shutting_down == True`；所有正在执行的监听器已完成（包括递归触发的事件）；事件队列已排空；后续 `emit()` 调用将被拒绝
- Inv: shutdown 操作是幂等的（重复调用无副作用，但首次之后的调用因 Pre 不满足而报错 — 见下方错误说明）
- 副作用: 修改 `_is_shutting_down` 状态；清理内部资源
- 错误: `ShutdownTimeoutError` — 在 `timeout` 秒内未完成停机

#### `AsyncDispatcher.shutdown(self, *, timeout: float | None = None) -> None`

异步优雅停机。

- Pre: 同 `SyncDispatcher.shutdown()`；当前处于 asyncio 事件循环中
- Post: 同 `SyncDispatcher.shutdown()`
- Inv: 同 `SyncDispatcher.shutdown()`
- 副作用: 同 `SyncDispatcher.shutdown()`
- 错误: 同 `SyncDispatcher.shutdown()`

---

### C-003 API（ListenerStore）

#### `ListenerEntry`（dataclass）

```python
@dataclass
class ListenerEntry:
    callback: Callable
    priority: int
    after: list[str]
    name: str
```

- Inv: `name` 默认为 `callback.__name__`；`priority` 越大优先级越高；`after` 为监听器名称列表（可为空列表）

#### `ListenerStore.__init__(self) -> None`

构造空的监听器存储。

- Pre: 无
- Post: 内部存储为空
- Inv: 无
- 副作用: 无
- 错误: 无

#### `ListenerStore.add(self, event_types: list[type[Event]], entry: ListenerEntry) -> None`

注册监听器。

- Pre: `event_types` 中每个元素为 `Event` 的子类；`entry.after` 中引用的监听器名称已注册到**任意事件类型**（不限于当前 `event_types`）；`entry.after` 加入后不形成循环依赖
- Post: `entry` 已添加到每个指定事件类型的监听器列表
- Inv: 同一 `callback` 可多次注册到不同事件类型；注册操作不修改已有条目
- 副作用: 修改内部存储
- 错误:
  - `ValueError` — `entry.after` 中引用了未注册的监听器名称
  - `CyclicDependencyError` — `entry.after` 形成循环依赖

#### `ListenerStore.remove(self, event_types: list[type[Event]], callback: Callable) -> None`

取消注册监听器。

- Pre: `callback` 已注册到所有指定的 `event_types`；移除后不会导致其他监听器的 `after` 依赖失效
- Post: `callback` 对应的 `ListenerEntry` 已从所有指定事件类型的监听器列表中移除
- Inv: 移除操作不影响其他已注册的条目
- 副作用: 修改内部存储
- 错误:
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

#### `SyncEventQueue.__init__(self, max_size: int | None = None) -> None`

构造同步事件队列。

- Pre: `max_size` 为正整数或 `None`
- Post: 队列为空
- Inv: `max_size` 在生命周期内不可变
- 副作用: 无
- 错误: 无

#### `SyncEventQueue.put(self, event: Event) -> None`

追加事件到队列。

- Pre: 队列未满（`len(queue) < max_size`，或 `max_size is None`）
- Post: `event` 已追加到队列尾部；队列长度增加 1
- Inv: FIFO 顺序保持
- 副作用: 修改内部队列
- 错误: `QueueFullError` — 队列已满

#### `SyncEventQueue.get(self) -> Event`

取出队列头部事件。

- Pre: 队列非空
- Post: 返回队列头部事件；队列长度减少 1
- Inv: FIFO 顺序保持
- 副作用: 修改内部队列
- 错误: `IndexError` — 队列为空（调用方应先检查 `is_empty()`）

#### `SyncEventQueue.is_empty(self) -> bool`

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

#### `RetryConfig`（dataclass）

```python
@dataclass
class RetryConfig:
    max_retries: int
    should_retry: Callable[[Exception, dict], bool] | None = None
```

- Inv: `max_retries >= 1`；`should_retry` 为 `None` 时表示始终重试（直到达到 `max_retries`）

#### `ErrorHandler.__init__(self, *, error_strategy: str = "propagate", retry_config: RetryConfig | None = None, dead_letter_queue: DeadLetterQueue | None = None) -> None`

构造异常处理器。

- Pre: `error_strategy` ∈ `{"propagate", "capture", "retry"}`；当 `error_strategy == "retry"` 时 `retry_config` 不得为 `None`
- Post: 实例已创建，策略已配置
- Inv: 策略在生命周期内不可变
- 副作用: 无
- 错误: `ValueError` — 参数非法

#### `ErrorHandler.handle(self, exception: Exception, event: Event, listener: ListenerEntry, context: dict) -> dict | None`

按策略处理监听器异常。

- Pre: `exception` 为监听器执行时抛出的异常；`event` 为当前处理的事件；`listener` 为抛出异常的监听器；`context` 包含执行上下文信息
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
    context: dict
    timestamp: float
```

- Inv: 所有字段在创建后不可变（frozen dataclass 或约定不修改）

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
- 副作用: 修改内部存储
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
| `CyclicDependencyError` | `ValueError` | `after` 依赖形成循环（注册时 / resolve_order 时） |
| `KeyConflictError` | `ValueError` | 合并监听器返回字典时键冲突 |
| `QueueFullError` | `RuntimeError` | 同步事件队列超出 `max_size` |
| `ShutdownTimeoutError` | `TimeoutError` | 优雅停机超时 |
