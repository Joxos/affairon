# Affairon

一个面向"需求接缝"的事务（affair）驱动框架：把需求**暴露为事务接缝**，让多个回调在一个接缝上协作并进行结果合并。

---

## 定位与理念

传统扩展往往要求"写新代码 + 改原代码"。
Affairon 的主张是：把需求看作是一个事务接缝，实现了事务功能的回调（callback）像**插件**一样挂载；
对接缝的调用（affair call）像调用一个**大型可扩展函数**：

- 多个回调可在同一接缝上协作
- 回调结果可进行结果合并并返回
- 事务即规约（affair-as-contract）

---

## 核心特性

- **类型安全**：事务为 Pydantic 模型
- **便于演化**：事务类支持继承
- **顺序可控**：通过 `after` 声明执行顺序，框架可以基于多种策略生成分层执行计划
- **天然并发**：由于控制了必须控制的执行顺序，接缝上的其他任务是天然并发的
- **结果聚合**：多个回调返回字典值，最终合并
- **插件系统**：通过 Python 入口点和 `pyproject.toml` 自动发现并加载插件
- **CLI 运行器（`fairun`）**：从命令行读取项目配置、组装插件并启动应用

---

## 快速开始

### 安装

```bash
pip install affairon
# 或者使用 uv
uv add affairon
```

### 定义事务

```python
from affairon import Affair, MutableAffair

class AddIngredients(Affair):
    """不可变事务 — 监听器只读字段，不能修改。"""
    ingredients: tuple[str, ...]

class PrepCondiments(MutableAffair):
    """可变事务 — 监听器可以就地修改字段。"""
    condiments: dict[str, int]
```

### 注册回调

```python
from affairon import default_dispatcher as dispatcher

@dispatcher.on(AddIngredients)
def extra_ingredients(affair: AddIngredients) -> dict[str, list[str]]:
    return {"extras": ["salt", "pepper"]}
```

### 触发事务

```python
result = dispatcher.emit(AddIngredients(ingredients=("egg",)))
# result == {"extras": ["salt", "pepper"]}
```

---

## 插件系统

Affairon 支持两种插件来源，均通过 `pyproject.toml` 声明：

### 外部插件（入口点）

外部包通过 `affairon.plugins` 入口点组注册。
入口点目标可以是模块中的任意符号；affairon 会导入该模块，
并自动注册模块级 `@listen` 回调。
宿主应用在 `[tool.affairon] plugins` 中使用 PEP 508 需求字符串声明包：

```toml
# 宿主的 pyproject.toml
[tool.affairon]
plugins = ["my-plugin>=1.0"]
```

```toml
# 插件的 pyproject.toml
[project.entry-points."affairon.plugins"]
my-plugin = "my_plugin.lib:any_symbol"
```

### 本地插件（模块导入）

宿主应用自身的模块可以通过 `local_plugins` 声明。
每一项都必须是模块路径：

```toml
[tool.affairon]
local_plugins = ["myapp.lib", "myapp.host"]
```

组装阶段会导入每个模块，并仅自动注册该模块内定义的 `@listen` 回调
（导入进来的回调会被忽略，避免重复注册）。

**加载顺序**：先加载本地插件，再加载外部插件。这样宿主回调会先注册好，
外部扩展才能安全地通过 `after=[...]` 依赖它们。

### 配置 profiles（命名插件组）

拥有多个 dispatcher 实例的应用常常需要为每个实例选择不同的插件组合。
Profiles 允许你在同一个 `pyproject.toml` 中声明多个命名组，再在组装时精确选中一个。

```toml
[tool.affairon]
local_plugins = ["myapp.main"]

[tool.affairon.profiles.duel]
local_plugins = ["duel_core.mr2020"]

[tool.affairon.profiles.kernel]
local_plugins = [
  "duel_core.kernel.bridges",
  "duel_core.kernel.planners",
  "duel_core.kernel.appliers",
]
```

`PluginComposer.compose_from_pyproject(pyproject, profile=None)` 精确选择一段配置：

- `profile=None`（默认）— 读取 `[tool.affairon]`，行为与以往完全一致
- `profile="kernel"` — 仅读取 `[tool.affairon.profiles.kernel]`
- 请求不存在的 profile 会抛出 `PluginConfigError`

被选中的配置段遵循与根表相同的加载顺序：先本地插件，再外部插件。
根配置与 profile 之间不发生继承或合并。

---

## CLI 运行器 — `fairun`

`fairun` 是内置的命令行工具：读取 `pyproject.toml`，先选择 dispatcher，
再在同一个 dispatcher 上组装插件并发射 `AffairMain` 事务：

```bash
fairun /path/to/project
# 或者在项目目录中直接运行：
fairun
```

应用通过监听 `AffairMain` 定义入口点：

```python
from affairon import AffairMain
from affairon.listen import listen

@listen(AffairMain)
def main(affair: AffairMain) -> None:
    print(f"Running from {affair.project_path}")
# affair.dispatcher 即 fairun 选择的 dispatcher 实例。
```

---

## 类式处理器 — `AffairAware`

如果希望以类的方式组织回调，可以继承 `AffairAware`。
类方法使用 `@listen` 装饰，并在实例化时传入 `dispatcher=`。
绑定回调会在 `__init__` 完成后自动注册，且仍然无需调用 `super().__init__()`：

```python
from affairon import AffairAware, Dispatcher
from affairon.listen import listen

d = Dispatcher()

class Kitchen(AffairAware):
    def __init__(self, chef: str):
        self.chef = chef

    @listen(AddIngredients)
    def cook(self, affair: AddIngredients) -> dict[str, str]:
        return {"chef": self.chef}

k = Kitchen("Alice", dispatcher=d)  # cook() 已注册为绑定方法
result = d.emit(AddIngredients(ingredients=("egg",)))
# result == {"chef": "Alice"}
```

- `on()` — 立即注册普通函数
- `listen()` — 仅标注延迟绑定元数据；用于模块级回调和类方法

支持 `@staticmethod` 和 `@classmethod`——放在 `@listen()` **外层**：

```python
class Handler(AffairAware):
    @staticmethod
    @listen(Ping)
    def static_handle(affair: Ping) -> dict[str, str]:
        return {"static": "yes"}

    @classmethod
    @listen(Ping)
    def class_handle(cls, affair: Ping) -> dict[str, str]:
        return {"cls": cls.__name__}
```

---

## 设计权衡

此范式并非"万能"，但它的收益明确、成本也明确：

**收益**

- 架构更清晰：接缝即契约
- 扩展更安全：事务类型可追踪、可重构、可验证
- 执行更可控：显式顺序/并发

**成本/风险**

- 调试需要更强的链路可视化
- 组合与扩展带来维护成本（版本、兼容、测试）
- 抽象带来性能损耗（可内聚热路径规避）

Affairon 的长期目标是：通过框架辅助减少成本与风险（事务栈、冲突检测、演化策略）

---

## 重要语义

- **回调返回值**：回调返回 `dict` 会被合并；返回 `None` 视为无贡献
- **冲突处理**：字典 key 冲突将抛出 `KeyConflictError`
- **依赖顺序**：通过 `after` 明确"必须先执行"的回调
- **异步并发**：同一层级回调并行运行；失败时可能出现 `ExceptionGroup`

---

## 项目愿景

如果你认同这种范式，欢迎参与讨论与贡献。
