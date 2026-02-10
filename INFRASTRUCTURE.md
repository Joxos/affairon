# INFRASTRUCTURE — eventd

## 1. 系统总览

eventd 是一个支持同步/异步模式的 Python 事件驱动框架。MVP 阶段由 3 个核心组件构成，分为两层：

- **公开 API 层**：Dispatcher（C-002）、Event（C-001）和 MetaEvent（C-001M）直接面向用户
- **内部服务层**：RegistryTable（C-003）为 Dispatcher 提供监听器管理能力

> **未来扩展**：ErrorHandler（异常策略处理）和 DeadLetterQueue（死信队列）将基于 MetaEvent 监听器机制实现 — 即用户通过注册 `ListenerErrorEvent`、`EventDeadLetteredEvent` 等 MetaEvent 子类的监听器来自定义错误处理和死信管理，而非框架内部的独立组件。详见 `TODO.md` TD-005。

```
┌──────────────────────────────────────────────────────────────────┐
│                         公开 API 层                               │
│                                                                  │
│  ┌───────────────┐    ┌──────────────────────────────────────┐   │
│  │  C-001        │    │  C-002  Dispatcher                   │   │
│  │  Event        │◄───│                                      │   │
│  │  (事件模型)    │    │  BaseDispatcher                      │   │
│  │               │    │    ├── Dispatcher                     │   │
│  │  C-001M       │    │    └── AsyncDispatcher                │   │
│  │  MetaEvent    │    └──────────────┬───────────────────────┘   │
│  │  (元事件基类)  │                  │                            │
│  └───────────────┘                  │                            │
└─────────────────────────────────────┼────────────────────────────┘
                                      │
┌─────────────────────────────────────┼────────────────────────────┐
│                       内部服务层      │                            │
│                                     │                            │
│                      ┌──────────────▼───────────────┐            │
│                      │  C-003                       │            │
│                      │  RegistryTable               │            │
│                      │  (监听器注册表)                │            │
│                      └──────────────────────────────┘            │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 数据流

1. **注册流**：用户 → `Dispatcher.on()` / `register()` → `RegistryTable` 存储监听器
2. **分发流**：用户 → `Dispatcher.emit(event)` → `RegistryTable.resolve_order()` 获取执行计划（含缓存） → 执行监听器 → 合并返回值
3. **递归流**：监听器内 `emit()` → 直接递归执行（同步和异步均使用直接递归）。框架不做循环检测，Python `RecursionError` 为安全网
4. **异常流**：监听器异常 → 直接 propagate（re-raise）。MVP 不做异常策略处理，未来通过 MetaEvent 监听器扩展
5. **停机流**：用户 → `Dispatcher.shutdown()` → 拒绝新事件 → 清理资源
6. **元事件流**（预留）：框架内部行为（错误、死信等）→ 发射 `MetaEvent` → 用户注册的元事件监听器处理

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
- **对外暴露**：`Event` 基类（用户继承使用）、`MetaEvent` 基类（框架元事件）
- **关键设计**：
  - 继承 `pydantic.BaseModel`
  - `event_id` 和 `timestamp` 为框架保留字段，构造时不可由用户传入，由 Dispatcher 在 `emit()` 时通过赋值注入
  - 用户通过子类添加自定义数据字段
  - `MetaEvent(Event)` 为框架内部元事件的基类，用于描述框架自身行为（如错误发生、死信入队等），用户可注册监听元事件以实现可观测性扩展
- **文件**：`src/eventd/event.py`

### C-002: Dispatcher（事件管理器）

- **职责**：事件分发核心。提供 `on()`、`register()`、`unregister()`、`emit()`、`shutdown()` 等公开 API。协调 RegistryTable 完成事件的注册、分发和生命周期管理
- **作用说明**：Dispatcher 是用户与框架交互的唯一入口。用户通过 Dispatcher 注册监听器、提交事件和控制生命周期。Dispatcher 本身不直接处理存储，而是将监听器管理委托给内部的 RegistryTable
- **覆盖需求**：F-002, F-003, F-003A, F-004, F-005, F-008, F-008-SYNC, F-010（日志调用点）
- **依赖**：C-001, C-003
- **对外暴露**：`BaseDispatcher`（抽象基类）、`Dispatcher`、`AsyncDispatcher`、`default_dispatcher`（模块级 `Dispatcher` 实例）
- **关键设计**：
  - `BaseDispatcher`（抽象基类）：封装共用逻辑
    - 构造参数管理（`event_id_generator`、`timestamp_generator`）
    - 持有 `RegistryTable` 实例
    - 注册/取消注册逻辑（`on()`、`register()`、`unregister()` 委托给 `RegistryTable`）
    - shutdown 状态管理（`_is_shutting_down` 标志）
    - `event_id` / `timestamp` 生成逻辑
  - `Dispatcher(BaseDispatcher)`：
    - `emit()` — 同步阻塞执行，直接递归调用（无队列）
    - `shutdown()` — 同步停机
  - `AsyncDispatcher(BaseDispatcher)`：
    - `async emit()` — 异步分层并行执行（同优先级 `asyncio.TaskGroup`），递归事件直接递归执行
    - `async shutdown()` — 异步停机
  - `default_dispatcher`：模块级 `Dispatcher` 实例，在 `__init__.py` 中创建
- **文件**：`src/eventd/dispatcher.py`

### C-003: RegistryTable（注册表）

- **职责**：管理监听器的注册、取消注册、按事件类型 + MRO 查找、priority/after 拓扑排序，维护执行计划缓存
- **作用说明**：RegistryTable 是 Dispatcher 的内部组件，用户不直接访问。它负责维护事件类型到监听器列表的映射关系（二维表结构），并在 emit 时提供按 MRO、priority、after 排序后的分层执行计划。内部通过 `_revision` 计数器和 `_plan_cache` 实现缓存，避免每次 emit 时重复计算执行计划
- **覆盖需求**：F-002, F-003, F-003A 的存储与查询逻辑
- **依赖**：无（叶子节点）
- **对外暴露**：`RegistryTable`、`ListenerEntry`
- **关键设计**：
  - `ListenerEntry`（`dataclass`）：
    - `callback: Callable[[Event], dict[str, Any] | None]` — 同步监听器回调函数（异步监听器类型为 `Callable[[Event], Awaitable[dict[str, Any] | None]]`）
    - `priority: int` — 优先级（越大越高）
    - `after: list[Callable[[Event], dict[str, Any] | None]]` — 依赖的监听器回调函数列表（这些监听器必须在当前监听器之前执行）
    - `name: str` — 可选调试标签（默认为 `callback.__qualname__`），仅用于日志和错误消息，不参与业务逻辑
  - `RegistryTable`：
    - 内部数据结构：`dict[type[Event], list[ListenerEntry]]`
    - `_revision: int` — 全局修订计数器，每次 `add()` / `remove()` 时递增
    - `_plan_cache: weakref.WeakKeyDictionary[type[Event], tuple[int, list[list[ListenerEntry]]]]` — 缓存 `(revision, plan)`，key 为事件类型（WeakKeyDictionary 防止动态事件类被缓存持有导致内存泄漏）
    - `add(event_types, entry)` — 注册监听器，执行 after 引用检查和循环依赖检测，递增 `_revision`
    - `remove(event_types, callback)` — 取消注册，执行被依赖检查，递增 `_revision`
    - `resolve_order(event_type) -> list[list[ListenerEntry]]` — 返回按 MRO 展开、按 priority 分层、after 拓扑排序后的分层执行计划。优先从 `_plan_cache` 读取（当 `cached_revision == _revision` 时命中），缓存未命中时重建并写入。外层 list 为优先级层（从高到低），内层 list 为同层内按 after 拓扑排序后的执行序列
    - 循环依赖检测在 `add()` 时执行，抛出 `CyclicDependencyError`
    - after 引用未注册监听器的检测在 `add()` 时执行，抛出 `ValueError`
    - 拓扑排序使用标准库 `graphlib.TopologicalSorter`，循环检测由 `graphlib.CycleError` 包装为 `CyclicDependencyError`
- **文件**：`src/eventd/registry.py`

## 4. 依赖图

```
C-001 Event            ─── (无依赖)
C-003 RegistryTable    ─── (无依赖)
C-002 Dispatcher       ─── C-001, C-003
C-002 AsyncDispatcher  ─── C-001, C-003
```

拓扑排序后的实现顺序：

```
阶段 A（可并行）: C-001, C-003
阶段 B:           C-002 (依赖 C-001, C-003)
```

## 5. 文件结构

```
src/eventd/
├── __init__.py          # 公开 API 导出 + default_dispatcher 实例
├── event.py             # C-001: Event 基类, MetaEvent 基类
├── dispatcher.py        # C-002: BaseDispatcher, Dispatcher, AsyncDispatcher
├── registry.py          # C-003: RegistryTable, ListenerEntry
├── exceptions.py        # 自定义异常类 (EventdError, EventValidationError, CyclicDependencyError, KeyConflictError)
└── _types.py            # 共享类型定义 (type aliases)
```

## 6. 未独立为组件的功能说明

| 功能 | 归属 | 理由 |
|------|------|------|
| F-010 日志记录 | 各组件内部直接调用 `loguru.logger` | 日志是横切关注点，不需要独立封装层 |
| MRO 解析逻辑 | C-003 `RegistryTable.resolve_order()` | 与监听器查询紧密耦合，无独立复用价值 |
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

#### `BaseDispatcher.__init__(self, *, event_id_generator: Callable[[], int] | None = None, timestamp_generator: Callable[[], float] | None = None) -> None`

构造事件管理器。

- Pre: `event_id_generator`（如提供）为 `Callable[[], int]`；`timestamp_generator`（如提供）为 `Callable[[], float]`
- Post: 实例已创建，内部 `RegistryTable` 已初始化；`_is_shutting_down == False`
- Inv: 构造参数在实例生命周期内不可变
- 副作用: 无
- 错误: 无

#### `BaseDispatcher.on(self, *event_types: type[Event], priority: int = 0, after: list[Callable[[Event], dict[str, Any] | None]] | None = None) -> Callable[[F], F]`

装饰器方式注册监听器。`F` 为被装饰函数的类型。

- Pre: `event_types` 中每个元素为 `Event` 的子类；回调函数类型与 Dispatcher 类型匹配（`Dispatcher` → 同步函数，`AsyncDispatcher` → 异步函数）；`after` 中引用的回调函数已注册到**任意事件**；`after` 不形成循环依赖
- Post: 回调函数已注册到所有指定事件类型；返回原始函数（不修改）
- Inv: 注册操作不影响已注册的其他监听器
- 副作用: 修改内部 `RegistryTable` 状态
- 错误:
  - `ValueError` — `after` 中引用了未注册的回调函数
  - `CyclicDependencyError` — `after` 形成循环依赖
  - `TypeError` — 回调函数类型与 Dispatcher 类型不匹配（同步 vs 异步）

#### `BaseDispatcher.register(self, event_types: type[Event] | list[type[Event]], callback: Callable[[Event], dict[str, Any] | None], *, priority: int = 0, after: list[Callable[[Event], dict[str, Any] | None]] | None = None) -> None`

方法调用方式注册监听器。

- Pre: 同 `on()`
- Post: 同 `on()`，但无返回值
- Inv: 同 `on()`
- 副作用: 同 `on()`
- 错误: 同 `on()`

#### `BaseDispatcher.unregister(self, event_types: type[Event] | list[type[Event]] | None = None, callback: Callable[[Event], dict[str, Any] | None] | None = None) -> None`

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
- 副作用: 修改内部 `RegistryTable` 状态
- 错误:
  - `ValueError` — `event_types` 和 `callback` 均为 `None`
  - `ValueError` — `callback` 未注册到指定事件类型
  - `ValueError` — 移除操作导致其他监听器的 `after` 依赖失效

#### `Dispatcher.emit(self, event: Event) -> dict`

同步提交事件。

- Pre: `event` 为 `Event` 子类的实例；Dispatcher 未处于 shutdown 状态（`_is_shutting_down == False`）
- Post: `event.event_id` 和 `event.timestamp` 已被赋值；所有匹配的监听器已按 MRO 顺序、priority（高→低）、after 拓扑顺序依次执行；所有监听器返回的字典已合并为一个字典返回；如果监听器在执行中触发新事件，新事件将直接递归执行（Python 调用栈控制深度，`RecursionError` 为安全网）
- Inv: `event_id` 生成器的调用计数单调递增
- 副作用: 执行监听器（监听器可能产生任意副作用）；写日志
- 错误:
  - `TypeError` — 监听器返回非字典值
  - `KeyConflictError` — 合并返回字典时键冲突
  - `RecursionError` — 监听器形成无限递归事件链（Python 运行时抛出，框架不拦截）
  - `RuntimeError` — Dispatcher 已关闭（`_is_shutting_down == True`）
  - 监听器抛出的异常（直接 propagate，框架不拦截）

#### `AsyncDispatcher.emit(self, event: Event) -> dict`

异步提交事件。

- Pre: 同 `Dispatcher.emit()`；当前处于 asyncio 事件循环中
- Post: 同 `Dispatcher.emit()`，但同优先级层的监听器通过 `asyncio.TaskGroup` 并行执行，不同优先级层按顺序执行；递归事件通过 `await self.emit(new_event)` 直接递归执行（与同步版行为一致）
- Inv: 同 `Dispatcher.emit()`
- 副作用: 同 `Dispatcher.emit()`
- 错误: 同 `Dispatcher.emit()`；`ExceptionGroup` — 同优先级层多个监听器同时失败时（`asyncio.TaskGroup` 行为），需要 `except*` 处理

#### `Dispatcher.shutdown(self) -> None`

同步优雅停机。

- Pre: Dispatcher 未处于 shutdown 状态
- Post: `_is_shutting_down == True`；后续 `emit()` 调用将被拒绝
- Inv: shutdown 操作是幂等的（重复调用无副作用，但首次之后的调用因 Pre 不满足而报错 — 见下方错误说明）
- 副作用: 修改 `_is_shutting_down` 状态
- 错误: 无（幂等，重复调用直接返回）

#### `AsyncDispatcher.shutdown(self) -> None`

异步优雅停机。

- Pre: 同 `Dispatcher.shutdown()`；当前处于 asyncio 事件循环中
- Post: 同 `Dispatcher.shutdown()`
- Inv: 同 `Dispatcher.shutdown()`
- 副作用: 同 `Dispatcher.shutdown()`
- 错误: 同 `Dispatcher.shutdown()`

---

### C-003 API（RegistryTable）

#### `ListenerEntry`（dataclass）

```python
@dataclass
class ListenerEntry:
    callback: Callable[[Event], dict[str, Any] | None]
    priority: int
    after: list[Callable[[Event], dict[str, Any] | None]]
    name: str  # 可选调试标签，默认 callback.__qualname__
```

- Inv: `name` 默认为 `callback.__qualname__`，仅用于日志和错误消息，不参与业务逻辑；`priority` 越大优先级越高；`after` 为回调函数列表（可为空列表），引用必须在当前监听器之前执行的监听器

#### `RegistryTable.__init__(self) -> None`

构造空的注册表。

- Pre: 无
- Post: 内部存储为空；`_revision == 0`；`_plan_cache` 为空
- Inv: 无
- 副作用: 无
- 错误: 无

#### `RegistryTable.add(self, event_types: list[type[Event]], entry: ListenerEntry) -> None`

注册监听器。

- Pre: `event_types` 中每个元素为 `Event` 的子类；`entry.after` 中引用的回调函数已注册到**任意事件类型**（不限于当前 `event_types`）；`entry.after` 加入后不形成循环依赖
- Post: `entry` 已添加到每个指定事件类型的监听器列表；`_revision` 已递增；`_plan_cache` 中受影响的条目将在下次 `resolve_order()` 时惰性失效
- Inv: 同一 `callback` 可多次注册到不同事件类型；注册操作不修改已有条目
- 副作用: 修改内部存储
- 错误:
  - `ValueError` — `entry.after` 中引用了未注册的回调函数
  - `CyclicDependencyError` — `entry.after` 形成循环依赖

#### `RegistryTable.remove(self, event_types: list[type[Event]] | None, callback: Callable[[Event], dict[str, Any] | None] | None) -> None`

取消注册监听器。支持与 `BaseDispatcher.unregister()` 相同的四种调用模式。

- Pre: 当同时指定 `event_types` 和 `callback` 时，`callback` 已注册到所有指定的 `event_types`；移除后不会导致其他监听器的 `after` 依赖失效
- Post: 对应的 `ListenerEntry` 已从相关事件类型的监听器列表中移除；`_revision` 已递增
- Inv: 移除操作不影响不相关的已注册条目
- 副作用: 修改内部存储
- 错误:
  - `ValueError` — `event_types` 和 `callback` 均为 `None`
  - `ValueError` — `callback` 未注册到指定事件类型
  - `ValueError` — 移除导致其他监听器的 `after` 依赖失效

#### `RegistryTable.resolve_order(self, event_type: type[Event]) -> list[list[ListenerEntry]]`

按 MRO、priority、after 排序，返回分层执行计划。内部含缓存机制。

- Pre: `event_type` 为 `Event` 的子类
- Post: 返回值为二维列表。外层按优先级从高到低排列，内层为同优先级的监听器按 after 拓扑排序后的执行序列。所有通过 MRO 匹配的监听器均包含在内（不去重）。若缓存命中（`cached_revision == _revision`），直接返回缓存结果；否则重建并写入缓存
- Inv: 返回值为只读快照（不影响内部状态）；同一 `event_type` 在注册状态不变时，多次调用返回相同结果
- 副作用: 无
- 错误:
  - `CyclicDependencyError` — after 依赖在排序时检测到循环（理论上不应发生，因为 `add()` 时已检测，此处为防御性检查）

---

### 异常类清单（`exceptions.py`）

| 异常类 | 继承自 | 触发场景 |
|--------|--------|----------|
| `EventdError` | `Exception` | eventd 所有自定义异常的基类 |
| `EventValidationError` | `EventdError`, `ValueError` | 用户自定义字段验证失败（包装 pydantic `ValidationError`） |
| `CyclicDependencyError` | `EventdError`, `ValueError` | `after` 依赖形成循环（注册时 / resolve_order 时，包装 `graphlib.CycleError`） |
| `KeyConflictError` | `EventdError`, `ValueError` | 合并监听器返回字典时键冲突 |

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

#### 8.1.3 MetaEvent 基类

**目标**：为框架内部行为定义元事件基类，贯彻事件驱动理念。

```python
# 伪代码
class MetaEvent(Event):
    """框架元事件基类。

    用于描述框架自身行为（如错误发生、死信入队等）。
    用户可注册监听 MetaEvent 子类以实现可观测性扩展。

    预定义元事件类型（MVP 阶段仅定义类型，不自动发射）：
    - ListenerErrorEvent: 监听器执行异常时发射
    - EventDeadLetteredEvent: 事件进入死信队列时发射
    """
    pass


class ListenerErrorEvent(MetaEvent):
    """监听器执行异常时的元事件。"""
    listener_name: str
    original_event_type: str
    error_message: str
    error_type: str


class EventDeadLetteredEvent(MetaEvent):
    """事件进入死信队列时的元事件。"""
    listener_name: str
    original_event_type: str
    error_message: str
    retry_count: int
```

**关键点**：

- MVP 阶段仅定义 `MetaEvent` 及其子类的数据结构，不自动发射任何 MetaEvent
- **ErrorHandler 和 DeadLetterQueue 不再作为独立组件存在**。未来版本中，用户通过注册 `ListenerErrorEvent`、`EventDeadLetteredEvent` 等 MetaEvent 子类的监听器来实现自定义错误处理和死信管理 — Dispatcher 在异常/死信场景中 `emit()` 对应的 MetaEvent，监听器完成实际处理
- 元事件化扩展计划记录在 `TODO.md` TD-005 中

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

**目标**：同步分发事件。监听器内递归调用 `emit()` 直接递归执行，无队列机制。

```python
# 伪代码
def emit(self, event: Event) -> dict:
    """同步分发事件。

    Warning:
        监听器内可递归调用 emit()，框架不做循环检测。
        用户应自行避免形成无限递归的事件链（如 A→B→A），
        否则将触发 Python 运行时的 RecursionError（默认栈深度 1000）。
    """
    # 1. 状态检查
    if self._is_shutting_down:
        raise RuntimeError("Dispatcher 已关闭")

    # 2. 注入元数据
    self._inject_metadata(event)

    # 3. 直接分发（允许递归）
    return self._dispatch_single(event)
```

**与旧版的关键区别**：

- **移除 `_is_emitting` 标志**：不再检测递归调用
- **移除 `EventQueue`（同步模式）**：不再排队递归事件，直接递归执行
- **安全网**：Python 的 `RecursionError`（默认栈深度 1000）作为唯一保护
- **用户责任**：docstring 提醒用户避免循环事件链

#### 8.2.3 `_dispatch_single(self, event: Event) -> dict`（内部方法）

**目标**：分发单个事件给所有匹配的监听器。

```python
# 伪代码
def _dispatch_single(self, event: Event) -> dict:
    # 1. 获取分层执行计划（含缓存）
    layers = self._registry.resolve_order(type(event))

    merged_result: dict = {}
    # 2. 按优先级层依次执行
    for layer in layers:
        for entry in layer:
            result = self._execute_listener(entry, event)
            if result is not None:
                merge_dict(merged_result, result)

    return merged_result
```

#### 8.2.4 `_execute_listener(self, entry: ListenerEntry, event: Event) -> dict[str, Any] | None`（内部方法）

**目标**：执行单个监听器，处理返回值验证。异常直接 propagate。

```python
# 伪代码
def _execute_listener(
    self, entry: ListenerEntry, event: Event
) -> dict[str, Any] | None:
    # 监听器异常直接 propagate（不拦截）
    # 未来通过 MetaEvent 监听器扩展错误处理（见 TODO.md TD-005）
    result = entry.callback(event)

    # 返回值验证
    if result is None:
        return None
    if not isinstance(result, dict):
        raise TypeError(
            f"监听器 {entry.name} 返回非字典值: {type(result)}"
        )
    return result
```

#### 8.2.5 `merge_dict(target: dict, source: dict) -> None`（模块级公开辅助函数）

**目标**：合并监听器返回的字典，键冲突时抛出 `KeyConflictError`。

```python
# 伪代码
def merge_dict(target: dict, source: dict) -> None:
    """合并 source 字典到 target 字典。

    Args:
        target: 目标字典（就地修改）。
        source: 源字典。

    Raises:
        KeyConflictError: 当 target 和 source 存在重复键时。
    """
    conflicts = set(target.keys()) & set(source.keys())
    if conflicts:
        raise KeyConflictError(f"键冲突: {conflicts}")
    target.update(source)
```

**复杂度**：O(min(|target|, |source|)) 用于冲突检测

**命名说明**：函数不以下划线开头，因为 `merge_dict` 是一个通用的合并字典工具函数，虽然做了 `KeyConflictError` 特化报错，但其行为可被视为通用功能，不限于内部使用。

#### 8.2.6 `AsyncDispatcher.emit()` 内部流程

**目标**：异步分发事件，同优先级层通过 `asyncio.TaskGroup` 并行执行。递归事件直接递归执行（与同步版行为一致）。

```python
# 伪代码
async def emit(self, event: Event) -> dict:
    """异步分发事件。

    Warning:
        监听器内可递归调用 emit()，框架不做循环检测。
        用户应自行避免形成无限递归的事件链（如 A→B→A），
        否则将触发 Python 运行时的 RecursionError（默认栈深度 1000）。
    """
    # 1. 状态检查
    if self._is_shutting_down:
        raise RuntimeError("Dispatcher 已关闭")

    # 2. 注入元数据
    self._inject_metadata(event)

    # 3. 直接分发（允许递归）
    return await self._dispatch_single(event)
```

**与同步版的一致性**：

- 异步模式同样使用**直接递归**，不再使用 `_is_emitting` 标志或 `AsyncEventQueue`
- 监听器内 `await self.emit(new_event)` 直接递归执行完毕后，再继续当前监听器的后续逻辑
- Python `RecursionError` 为同步/异步共同的安全网
- 同优先级层内通过 `asyncio.TaskGroup` 并行执行（见 8.2.7）

#### 8.2.7 `AsyncDispatcher._dispatch_single()` 内部差异

**目标**：同优先级层通过 `asyncio.TaskGroup`（Python 3.11+）并行执行。

```python
# 伪代码 — 与同步版的区别：同层 TaskGroup 并行
async def _dispatch_single(self, event: Event) -> dict:
    layers = self._registry.resolve_order(type(event))

    merged_result: dict = {}
    for layer in layers:
        # 同优先级层并行执行（TaskGroup 替代 gather）
        results: list[dict[str, Any] | None] = [None] * len(layer)

        async with asyncio.TaskGroup() as tg:
            for i, entry in enumerate(layer):
                async def _run(
                    idx: int = i, e: ListenerEntry = entry
                ) -> None:
                    results[idx] = await self._execute_listener(e, event)
                tg.create_task(_run())

        for result in results:
            if result is not None:
                merge_dict(merged_result, result)

    return merged_result
```

**关键点**：

- `asyncio.TaskGroup`（Python 3.11+）是结构化并发的推荐方式，替代 `asyncio.gather()`
- 当任一 task 抛出异常时，`TaskGroup` 会取消所有其他 task 并抛出 `ExceptionGroup`
- 异常处理需使用 `except*` 语法（Python 3.11+）；MVP 阶段监听器异常直接 propagate（不拦截），因此 `ExceptionGroup` 会向上传播
- 使用默认参数 `idx=i, e=entry` 避免闭包变量捕获问题

#### 8.2.8 `Dispatcher.shutdown()` / `AsyncDispatcher.shutdown()` 内部流程

```python
# 伪代码（同步版）
def shutdown(self) -> None:
    if self._is_shutting_down:
        return  # 幂等：已关闭则直接返回

    self._is_shutting_down = True
    # 无队列，无需排空。设置标志后后续 emit() 将被拒绝
```

```python
# 伪代码（异步版）
async def shutdown(self) -> None:
    if self._is_shutting_down:
        return  # 幂等：已关闭则直接返回

    self._is_shutting_down = True
    # 无队列，无需排空。设置标志后后续 emit() 将被拒绝
```

**关键点**：

- `shutdown` 是幂等的：首次调用后设置 `_is_shutting_down = True`，后续调用直接返回（不抛异常）
- 同步/异步版本行为完全一致 — 均无队列需要排空，仅设置标志位
- 移除 `timeout` 参数（无队列则无超时场景）
- 移除 `ShutdownTimeoutError`（无超时场景）

---

### C-003 内部逻辑（RegistryTable）

#### 8.3.1 内部数据结构

```python
# 伪代码
import weakref
from collections.abc import Callable
from graphlib import TopologicalSorter, CycleError

class RegistryTable:
    def __init__(self) -> None:
        # 事件类型 → 监听器列表
        self._store: dict[type[Event], list[ListenerEntry]] = {}
        # callback → 已注册的事件类型集合（用于反查）
        self._callback_events: dict[
            Callable[[Event], dict[str, Any] | None],
            set[type[Event]],
        ] = {}
        # 全局修订计数器，add/remove 时递增
        self._revision: int = 0
        # 执行计划缓存：event_type → (revision, plan)
        # WeakKeyDictionary 防止动态事件类被缓存持有导致内存泄漏
        self._plan_cache: weakref.WeakKeyDictionary[
            type[Event],
            tuple[int, list[list[ListenerEntry]]],
        ] = weakref.WeakKeyDictionary()
```

**`_callback_events` 的作用**：

- `remove(None, callback)` 需要查找 callback 注册在哪些事件上 → O(1) 查找
- `add()` 时检查 `after` 引用的 callback 是否已注册 → O(1) 查找
- 维护成本：`add()` 和 `remove()` 时同步更新

**`_revision` + `_plan_cache` 缓存机制**：

- 每次 `add()` / `remove()` 递增 `_revision`
- `resolve_order()` 检查缓存：`cached_revision == self._revision` 时直接返回缓存结果
- 缓存未命中时重建执行计划并写入缓存
- `weakref.WeakKeyDictionary` 以事件类型为 key，当动态创建的事件类被 GC 回收时，对应缓存条目自动清除，防止内存泄漏

#### 8.3.2 `resolve_order()` 算法

**输入**：`event_type: type[Event]`

**输出**：`list[list[ListenerEntry]]`（外层 = 优先级层，内层 = 拓扑排序后的执行序列）

**算法步骤**：

```
0. 缓存检查
   如果 event_type 在 _plan_cache 中且 cached_revision == _revision：
     返回缓存的 plan

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
     使用 graphlib.TopologicalSorter 构建 DAG 并排序
     如果检测到环 → graphlib.CycleError → 包装为 CyclicDependencyError（防御性）

5. 缓存写入
   将 (self._revision, plan) 写入 _plan_cache[event_type]

6. 返回 plan
```

**复杂度**：

- 缓存命中：O(1)
- 缓存未命中：O(M × L + V + E)
  - M = MRO 链长度（通常 ≤ 5），L = 匹配的监听器总数
  - V = 单组内监听器数，E = after 边数
  - 实际项目中 L、V、E 均很小

#### 8.3.3 组内拓扑排序（graphlib.TopologicalSorter）

```python
# 伪代码
from graphlib import TopologicalSorter, CycleError

def _topological_sort(
    entries: list[ListenerEntry],
) -> list[ListenerEntry]:
    """使用标准库 graphlib 对同优先级组内的监听器进行拓扑排序。

    Args:
        entries: 同一优先级组内的监听器列表。

    Returns:
        按 after 依赖排序后的监听器列表。

    Raises:
        CyclicDependencyError: 检测到循环依赖（包装 graphlib.CycleError）。
    """
    # 构建 callback → entry 的映射
    callback_to_entry: dict[
        Callable[[Event], dict[str, Any] | None],
        ListenerEntry,
    ] = {e.callback: e for e in entries}

    # 构建 TopologicalSorter
    ts: TopologicalSorter[Callable[[Event], dict[str, Any] | None]] = (
        TopologicalSorter()
    )
    for entry in entries:
        # 收集当前组内的 after 依赖
        deps_in_group = [
            dep for dep in entry.after if dep in callback_to_entry
        ]
        ts.add(entry.callback, *deps_in_group)

    # 执行排序
    try:
        sorted_callbacks = tuple(ts.static_order())
    except CycleError as e:
        raise CyclicDependencyError(
            f"检测到循环依赖: {e.args[1]}"
        ) from e

    return [callback_to_entry[cb] for cb in sorted_callbacks]
```

**关键点**：

- 使用 `graphlib.TopologicalSorter`（Python 3.9+ 标准库），不自行实现 Kahn 算法
- `static_order()` 返回完整的排序序列，适用于非并行场景
- 循环检测由 `graphlib.CycleError` 提供，包装为 `CyclicDependencyError`
- `entry.after` 中不在当前优先级组内的 callback 被跳过（这些依赖在其他优先级层中已满足）

#### 8.3.4 `add()` 时的循环依赖检测

**目标**：在注册时检测 `after` 是否引入循环依赖，避免 `resolve_order()` 时才发现。

```python
# 伪代码
def add(
    self,
    event_types: list[type[Event]],
    entry: ListenerEntry,
) -> None:
    # 1. 检查 after 引用的回调是否已注册
    for dep in entry.after:
        if dep not in self._callback_events:
            raise ValueError(
                f"after 引用了未注册的回调: {dep.__qualname__}"
            )

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

    # 5. 递增修订计数器（使缓存失效）
    self._revision += 1
```

#### 8.3.5 循环依赖检测（DFS）

```python
# 伪代码
def _check_cycle(self, new_entry: ListenerEntry) -> None:
    """从 new_entry 的 after 依赖出发，DFS 检查是否存在回到 new_entry 的环。"""
    visited: set[Callable[[Event], dict[str, Any] | None]] = set()

    def dfs(
        callback: Callable[[Event], dict[str, Any] | None],
    ) -> bool:
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
def remove(
    self,
    event_types: list[type[Event]] | None,
    callback: Callable[[Event], dict[str, Any] | None] | None,
) -> None:
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

    # 6. 递增修订计数器（使缓存失效）
    self._revision += 1
```

---

### 8.7 悬置项与待确认事项

| 编号 | 事项 | 影响范围 | 建议处理时机 |
|------|------|----------|-------------|
| S-001 | 异步并发 `emit` 的行为（`asyncio.Lock` vs 允许并发） | C-002 AsyncDispatcher | 实现阶段确定，先用 Lock 串行化（见 TODO.md TD-002） |
