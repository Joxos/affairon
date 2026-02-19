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

Affairon 支持两种插件，均通过 `pyproject.toml` 声明：

### 外部插件（入口点）

外部包通过 `affairon.plugins` 入口点组注册。
宿主应用在 `[tool.affairon] plugins` 中使用 PEP 508 需求字符串声明：

```toml
# 宿主的 pyproject.toml
[tool.affairon]
plugins = ["my-plugin>=1.0"]
```

```toml
# 插件的 pyproject.toml
[project.entry-points."affairon.plugins"]
my-plugin = "my_plugin.lib"
```

### 本地插件（直接导入）

宿主应用自身的模块可以通过 `local_plugins` 声明。
它们会被直接导入，通过装饰器触发回调注册：

```toml
[tool.affairon]
local_plugins = ["myapp.lib", "myapp.host"]
```

**加载顺序**：先加载外部插件，再加载本地插件。

---

## CLI 运行器 — `fairun`

`fairun` 是内置的命令行工具，读取 `pyproject.toml`，组装所有插件，然后发射 `AffairMain` 事务以启动应用：

```bash
fairun /path/to/project
# 或者在项目目录中直接运行：
fairun
```

应用通过监听 `AffairMain` 定义入口点：

```python
from affairon import AffairMain, default_dispatcher as dispatcher

@dispatcher.on(AffairMain)
def main(affair: AffairMain) -> None:
    print(f"Running from {affair.project_path}")
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
