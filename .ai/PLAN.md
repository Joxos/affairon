# PLAN — eventd

> 本文档根据 `INFRASTRUCTURE.md` 中的组件依赖图和契约设计，将实现拆分为有序的阶段。  
> 每个阶段遵循 `HOW_TO.md` §6.1 的三步骤流程（骨架 → 测试 → 实现），阶段间必须经用户显式批准。

---

## 依赖拓扑排序

```
C-001 Event            ─── (无依赖)
C-003 RegistryTable    ─── (无依赖)
C-002 Dispatcher       ─── C-001, C-003
```

实现顺序：

```
阶段 0（基础设施）: exceptions.py, _types.py
阶段 1（可并行）:   C-001 Event, C-003 RegistryTable
阶段 2:             C-002 Dispatcher（依赖 C-001, C-003）
阶段 3:             __init__.py 公开 API 导出 + 集成测试
```

---

## 阶段 0: 基础设施（异常类与共享类型）

- **目标**: 建立项目骨架和所有组件共享的基础模块——异常类层次和类型别名
- **组件**: 无独立组件编号（跨组件共享模块）
- **验收标准**:
  - [ ] `EventdError` 继承自 `Exception`
  - [ ] `EventValidationError` 继承自 `EventdError` 和 `ValueError`
  - [ ] `CyclicDependencyError` 继承自 `EventdError` 和 `ValueError`
  - [ ] `KeyConflictError` 继承自 `EventdError` 和 `ValueError`
  - [ ] `_types.py` 中定义所有共享类型别名（如监听器回调类型、异步监听器回调类型）
  - [ ] 项目目录结构 `src/eventd/` 已创建
  - [ ] `pyproject.toml` 已配置（依赖: pydantic ^2.0, loguru ^0.7；开发依赖: pytest ^8.0, pytest-asyncio ^0.24, ruff）
  - [ ] ruff format + ruff check 通过
  - [ ] 异常类的继承关系测试通过
- **涉及文件**:
  - `pyproject.toml`
  - `src/eventd/__init__.py`（空占位）
  - `src/eventd/exceptions.py`
  - `src/eventd/_types.py`
- **预计 commit**: `feat(infra): add project skeleton, exceptions and shared types`
- **并发注意点**: 无

---

## 阶段 1: 事件模型 + 注册表

- **目标**: 实现两个无依赖的叶子组件——Event/MetaEvent 事件模型和 RegistryTable 注册表
- **组件**: [C-001, C-003]

### C-001 验收标准（Event / MetaEvent）

- [ ] `Event` 继承 `pydantic.BaseModel`，`frozen=True`
- [ ] `event_id: int | None` 和 `timestamp: float | None` 为框架保留字段，`init=False`，默认 `None`
- [ ] 用户构造时传入 `event_id` 或 `timestamp` 抛出 `EventValidationError`（`model_validator(mode="before")` 拦截）
- [ ] 用户自定义字段验证失败抛出 `EventValidationError`（包装 pydantic `ValidationError`）
- [ ] 用户可通过继承 `Event` 添加自定义数据字段
- [ ] `MetaEvent(Event)` 基类存在
- [ ] `ListenerErrorEvent(MetaEvent)` 定义正确（`listener_name`, `original_event_type`, `error_message`, `error_type`）
- [ ] `EventDeadLetteredEvent(MetaEvent)` 定义正确（`listener_name`, `original_event_type`, `error_message`, `retry_count`）
- [ ] MVP 阶段不自动发射任何 MetaEvent（仅定义）

### C-003 验收标准（RegistryTable / ListenerEntry）

- [ ] `ListenerEntry` 为 `dataclass`，字段: `callback`, `priority`, `after`, `name`
- [ ] `name` 默认为 `callback.__qualname__`
- [ ] `RegistryTable.__init__()`: `_store` 为空 dict，`_revision == 0`，`_plan_cache` 为空 `WeakKeyDictionary`
- [ ] `add()`: 注册监听器到指定事件类型，递增 `_revision`
- [ ] `add()`: `after` 中引用未注册回调时抛出 `ValueError`
- [ ] `add()`: `after` 形成循环依赖时抛出 `CyclicDependencyError`
- [ ] `remove()`: 四种模式行为正确（有/有、有/None、None/有、None/None→ValueError）
- [ ] `remove()`: 被依赖的监听器不可移除（抛出 `ValueError`）
- [ ] `remove()`: 递增 `_revision`
- [ ] `resolve_order()`: 返回按 MRO 展开、priority 分层、after 拓扑排序的二维列表
- [ ] `resolve_order()`: 缓存命中时直接返回（`cached_revision == _revision`）
- [ ] `resolve_order()`: 同一 callback 通过不同 MRO 层级匹配时不去重
- [ ] 拓扑排序使用 `graphlib.TopologicalSorter`
- [ ] `_callback_events` 反查索引正确维护

- **涉及文件**:
  - `src/eventd/event.py`（C-001）
  - `src/eventd/registry.py`（C-003）
  - `tests/unit/test_event.py`（C-001 测试）
  - `tests/unit/test_registry.py`（C-003 测试）
  - `tests/conftest.py`（共享 fixtures）
- **预计 commit**:
  - `feat(event): implement Event, MetaEvent and validation logic`
  - `feat(registry): implement RegistryTable with topo sort and caching`
- **并发注意点**: 无。C-001 和 C-003 无依赖关系，可并行开发，但因 AI 单线程工作，将顺序实现

---

## 阶段 2: 事件管理器

- **目标**: 实现 Dispatcher 核心——BaseDispatcher 抽象基类、Dispatcher（同步）和 AsyncDispatcher（异步）
- **组件**: [C-002]
- **验收标准**:
  - [ ] `BaseDispatcher.__init__()`: 接受 `event_id_generator` 和 `timestamp_generator` 可选参数
  - [ ] `BaseDispatcher.__init__()`: 内部创建 `RegistryTable` 实例，`_is_shutting_down == False`
  - [ ] `on()`: 装饰器方式注册监听器，返回原函数不修改
  - [ ] `on()`: 支持多事件类型 `*event_types`
  - [ ] `on()`: 回调函数类型与 Dispatcher 类型不匹配时抛出 `TypeError`
  - [ ] `register()`: 方法调用方式注册，`event_types` 支持单个类型和列表
  - [ ] `unregister()`: 四种模式委托给 `RegistryTable.remove()`
  - [ ] `Dispatcher.emit()`: 注入 `event_id` 和 `timestamp`（`object.__setattr__` 绕过 frozen）
  - [ ] `Dispatcher.emit()`: shutdown 状态下抛出 `RuntimeError`
  - [ ] `Dispatcher.emit()`: 按 `resolve_order()` 返回的分层计划依次执行监听器
  - [ ] `Dispatcher.emit()`: 监听器返回非字典抛出 `TypeError`
  - [ ] `Dispatcher.emit()`: 键冲突抛出 `KeyConflictError`
  - [ ] `Dispatcher.emit()`: 监听器内递归 `emit()` 直接递归执行
  - [ ] `Dispatcher.emit()`: 监听器异常直接 propagate
  - [ ] `AsyncDispatcher.emit()`: 同优先级层 `asyncio.TaskGroup` 并行执行
  - [ ] `AsyncDispatcher.emit()`: 递归事件 `await self.emit()` 直接递归
  - [ ] `AsyncDispatcher.emit()`: 多监听器同时失败产生 `ExceptionGroup`
  - [ ] `Dispatcher.shutdown()`: 幂等，设置 `_is_shutting_down = True`
  - [ ] `AsyncDispatcher.shutdown()`: 同 `Dispatcher.shutdown()` 行为
  - [ ] `merge_dict()`: 键冲突抛出 `KeyConflictError`，无冲突时正确合并
  - [ ] `_inject_metadata()`: 通过 `object.__setattr__` 注入 `event_id` 和 `timestamp`
- **涉及文件**:
  - `src/eventd/dispatcher.py`
  - `tests/unit/test_sync_emit.py`
  - `tests/unit/test_async_emit.py`
  - `tests/unit/test_registration.py`（注册/取消注册通过 Dispatcher API 的测试）
  - `tests/unit/test_shutdown.py`
- **预计 commit**:
  - `feat(dispatcher): implement BaseDispatcher, Dispatcher sync emit`
  - `feat(dispatcher): implement AsyncDispatcher async emit with TaskGroup`
- **并发注意点**:
  - `AsyncDispatcher.emit()` 同优先级层使用 `asyncio.TaskGroup` 并行执行，需注意闭包变量捕获（使用默认参数 `idx=i, e=entry`）
  - 并发 `emit()` 调用的行为为悬置项（S-001），MVP 阶段不做特殊处理，记录在 `TODO.md` TD-002

---

## 阶段 3: 公开 API 导出 + 集成测试

- **目标**: 完成 `__init__.py` 的公开 API 导出（包含 `default_dispatcher`），编写跨组件集成测试
- **组件**: 无新组件（整合已有组件）
- **验收标准**:
  - [ ] `from eventd import Event, MetaEvent, Dispatcher, AsyncDispatcher` 可正常导入
  - [ ] `from eventd import default_dispatcher` 返回模块级 `Dispatcher` 实例
  - [ ] `from eventd import EventdError, EventValidationError, CyclicDependencyError, KeyConflictError` 可正常导入
  - [ ] 集成测试: 完整同步流程（定义事件 → 注册监听器 → emit → 验证返回值）
  - [ ] 集成测试: 完整异步流程（同上，异步版本）
  - [ ] 集成测试: MRO 继承链 + priority + after 组合场景
  - [ ] 集成测试: 递归 emit 场景（监听器内触发新事件）
  - [ ] 集成测试: shutdown 后 emit 被拒绝
  - [ ] ruff format + ruff check 全项目通过
  - [ ] 全部测试通过
- **涉及文件**:
  - `src/eventd/__init__.py`
  - `tests/integration/test_full_sync_flow.py`
  - `tests/integration/test_full_async_flow.py`
- **预计 commit**: `feat(init): add public API exports and integration tests`
- **并发注意点**: 无

---

## 实施节奏

每个阶段内部严格遵循三步骤流程（`HOW_TO.md` §6.1）：

| 步骤 | 内容 | 用户审批点 |
|------|------|-----------|
| **步骤 A — 骨架** | 生成 API + 类骨架（签名、docstring、`raise NotImplementedError`） | 用户审阅骨架后批准 |
| **步骤 B — 测试** | 依据契约编写测试（预期全部失败） | 用户审阅测试后批准 |
| **步骤 C — 实现** | 填充具体逻辑，运行测试确保通过 | 用户审阅实现后批准进入下一阶段 |

**阶段间过渡**：当前阶段步骤 C 完成且测试全部通过后，必须经用户显式批准方可进入下一阶段。
