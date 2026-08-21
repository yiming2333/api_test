# Python 接口自动化测试框架

基于 **requests + pytest + Allure** 的分层接口自动化测试框架，支持数据驱动、并发执行、失败重试、数据库校验，可通过 Jenkins Pipeline 实现持续集成。

## 目录

- [项目结构](#项目结构)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [编写用例](#编写用例)
- [运行测试](#运行测试)
- [Allure 报告](#allure-报告)
- [Jenkins 集成](#jenkins-集成)
- [进阶功能](#进阶功能)
- [常见问题](#常见问题)

## 项目结构

```
api_test/
├── common/                     # 公共模块
│   ├── http_client.py          # requests 封装（重试、日志、Allure 附件）
│   ├── logger.py               # 日志模块（控制台 + 按天滚动文件）
│   ├── yaml_handler.py         # YAML 配置读取
│   ├── db_pool.py              # 共享 MySQL 连接池（mock + 测试共用）
│   └── sanitize.py             # 敏感字段脱敏（密码/token 不入报告）
├── config/
│   ├── config.yaml             # 多环境配置（dev/prod）
│   ├── test_accounts.yaml      # 测试账号统一配置（conftest 与 YAML 数据驱动共用）
│   └── testdata/               # 测试数据（YAML）
│       ├── login.yaml
│       └── order.yaml
├── testcases/                  # 测试用例
│   ├── conftest.py             # 业务级 fixture（独立数据工厂 + 用户隔离）
│   ├── test_login.py           # 登录模块（YAML 数据驱动）
│   ├── test_order.py           # 订单模块（DB 校验）
│   ├── test_profile.py         # 个人信息模块（含跨用户安全校验）
│   ├── test_register.py        # 注册模块（正向/幂等/异常参数）
│   ├── test_project_task.py    # 项目与任务模块（级联删除）
│   ├── test_file_upload.py     # 文件上传模块（含跨用户 commit 安全校验）
│   └── test_generic_isolated.py # 隔离数据驱动用例 + 多用户身份隔离
├── utils/                      # 工具类
│   ├── data_loader.py          # 测试数据加载器（自动 mark 映射）
│   ├── case_runner.py          # YAML 用例执行引擎（模板解析/setup/teardown）
│   ├── jsonpath_util.py        # JSONPath 提取（基于 jsonpath-ng，支持完整语法）
│   ├── accounts.py             # 测试账号加载（lru_cache）
│   └── db.py                   # 数据库操作客户端（基于共享连接池，含标识符白名单校验）
├── scripts/
│   └── ensure_mock.py          # Mock 生命周期管理（start/stop/status/reset-db/db-status）
├── mock_flask.py               # Mock API 服务（多线程 + 线程锁并发安全）
├── init.sql                    # 数据库建表 + 种子数据
├── conftest.py                 # 全局 fixture（http / logged_in_http / db）
├── pytest.ini                  # pytest 配置
├── Jenkinsfile                 # Jenkins Pipeline 脚本
├── requirements.txt            # Python 依赖
└── README.md
```

## 技术栈

| 组件 | 用途 |
|------|------|
| Python 3.9+ | 运行环境 |
| requests | HTTP 请求 |
| pytest | 测试框架 |
| pytest-xdist | 并发执行 |
| pytest-rerunfailures | 失败重试 |
| allure-pytest | 测试报告 |
| PyYAML | 配置 / 数据管理 |
| PyMySQL | 数据库校验 |
| Flask | Mock API 服务 |
| DBUtils | 数据库连接池 |
| jsonpath-ng | JSONPath 断言（支持通配符/过滤器/递归下降） |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

Allure 命令行工具需要单独安装（依赖 Java）：

```bash
npm install -g allure-commandline
# 或从 https://github.com/allure-framework/allure2/releases 下载
allure --version
```

### 2. 初始化数据库

项目依赖 MySQL，需要先创建数据库和表。

```bash
# 方式一：直接执行 SQL（会自动创建 api_test 数据库、建表、插入种子数据）
mysql -u root -p < init.sql

# 方式二：手动连接后执行
mysql -u root -p
> source init.sql
```

`init.sql` 会创建以下内容：

| 表名 | 用途 |
|------|------|
| `users` | 用户表（含种子用户 `testuser`） |
| `orders` | 订单表 |
| `projects` | 项目表 |
| `tasks` | 任务表（外键关联 projects，级联删除） |
| `file_uploads` | 文件上传记录表 |

> **注意**：种子用户的密码是明文 `Test@123`，仅限测试环境使用。

如果数据库已存在，`init.sql` 使用 `IF NOT EXISTS` 和 `ON DUPLICATE KEY UPDATE`，重复执行不会报错。

### 3. 启动 Mock 服务

**方式一：直接启动**（适合本地调试，前台运行可看日志）

```bash
python mock_flask.py
```

**方式二：用 `ensure_mock.py` 托管**（推荐，Jenkins 也用这种方式）

```bash
# 检查并启动（已运行则直接退出 0；未运行则后台启动并等待就绪）
python scripts/ensure_mock.py start --env dev

# 检查服务状态（exit 0=正常，exit 1=未响应）
python scripts/ensure_mock.py status --env dev

# 停止服务（按 PID 文件 → 按端口占用兜底清理）
python scripts/ensure_mock.py stop --env dev

# 清空业务表残留（orders/projects/tasks/file_uploads，保留 users）
python scripts/ensure_mock.py reset-db --env dev

# 打印各表数据量快照（不清空，用于失败时诊断现场）
python scripts/ensure_mock.py db-status --env dev
```

> **prod 环境跳过所有 Mock 相关操作**：`ensure_mock.py` 检测到 `env != dev` 会直接退出 0，便于同一套 Jenkinsfile 在 prod 环境只跑接口测试不启 Mock。

服务默认运行在 `http://127.0.0.1:5000`，使用多线程模式处理并发请求。Mock 服务提供两个探测端点：

- `GET /` — 首页，返回简单 HTML（`ensure_mock.py status` 用它判断是否存活）
- `GET /api/ping` — 健康检查，返回 `{"status": "ok", "service": "mock_api"}` 并附带 DB 连通性检测

数据库连接配置统一从 `config/config.yaml` 的 `dev` 环境读取，不需要修改 `mock_flask.py`。如果你的 MySQL 配置不同，只需修改 `config.yaml`：

```yaml
env:
  dev:
    base_url: "http://127.0.0.1:5000"
    db_host: "localhost"
    db_port: 3306
    db_user: "root"
    db_password: "你的密码"
```

### 4. 运行测试

```bash
# 全部用例
pytest

# 指定环境
pytest --env=dev

# 冒烟测试
pytest -m smoke

# 并发执行（4 个 worker）
pytest -n 4
```

### 5. 查看报告

```bash
allure serve reports/allure-results
```

## 配置说明

### 多环境配置 `config/config.yaml`

```yaml
env:
  dev:
    base_url: "http://127.0.0.1:5000"
    db_host: "localhost"
    db_port: 3306
    db_user: "root"
    db_password: "Root@123456"
  prod:
    base_url: "https://api.example.com"
    db_host: "10.0.0.1"
    db_port: 3306
    db_user: "readonly"
    db_password: "xxx"

timeout: 10
retry: 2
```

所有组件（HTTP 客户端、Mock 服务、数据库客户端）统一从这里读取配置，改密码只改一处。

通过 `--env` 参数切换环境：

```bash
pytest --env=prod
```

### 测试账号配置 `config/test_accounts.yaml`

集中管理测试账号，conftest.py 的 fixture 与 YAML 数据驱动用例**共用同一份账号**，避免散落维护：

```yaml
accounts:
  default:                # ← 主测试用户（默认 session 级 logged_in_http 用）
    username: testuser
    password: Test@123
  user_b:                  # ← 备用账号（new_user fixture 用，注册时附随机后缀）
    username: user_b
    password: pass_b_123
```

代码侧通过 `utils/accounts.py` 读取：

```python
from utils.accounts import get_account

account = get_account("default")     # → {"username": "testuser", "password": "Test@123"}
```

YAML 数据驱动用例中通过模板变量引用（由 `utils/case_runner.py` 解析）：

```yaml
json:
  username: "${accounts.default.username}"
  password: "${accounts.default.password}"
```

### pytest 配置 `pytest.ini`

| 配置项 | 说明 |
|--------|------|
| `testpaths` | 用例目录：`testcases` |
| `python_files` | 测试文件匹配：`test_*.py` |
| `python_classes` | 测试类匹配：`Test*`（无参构造） |
| `python_functions` | 测试函数匹配：`test_*` |
| `markers` | 自定义标记：`smoke`（冒烟）、`regression`（回归） |
| `addopts` | 默认参数：`-v -s --alluredir=./reports/allure-results --reruns 2 --reruns-delay 1 --env=dev` |

> `--reruns 2 --reruns-delay 1` 表示失败用例自动重试 2 次，间隔 1 秒。`--env=dev` 是默认环境，命令行 `--env=prod` 可覆盖。所有 addopts 参数都可被命令行覆盖。

## 编写用例

### 基本结构

```python
import pytest
import allure

@allure.epic("订单中心")
@allure.feature("订单管理")
class TestOrder:

    def test_create_order(self, logged_in_http, db):
        """创建订单 + DB 校验"""
        with allure.step("创建订单"):
            resp = logged_in_http.post("/api/orders", json={
                "product_id": "SKU_001",
                "quantity": 2,
                "address": "测试地址"
            })
            assert resp.status_code == 201
            order_id = resp.json()["data"]["order_id"]

        with allure.step("DB 校验"):
            db.assert_field_value(
                "orders", "order_id = %s", (order_id,),
                field="status", expected="pending"
            )

        # 清理
        logged_in_http.delete(f"/api/orders/{order_id}")
```

### 数据驱动 + 动态标记

在 `config/testdata/` 下创建 YAML 数据文件，支持 `mark` 字段自动打 pytest 标记，并支持 `${accounts.xxx}` 模板变量引用 `test_accounts.yaml` 中的账号：

```yaml
test_login:
  - case_id: LOGIN_001
    title: "正确账号密码登录成功"
    mark: smoke                    # ← 自动打 @pytest.mark.smoke
    request:
      method: post
      url: /api/auth/login
      json:
        username: "${accounts.default.username}"   # ← 引用 test_accounts.yaml
        password: "${accounts.default.password}"
    expect:
      status_code: 200
      json_path:
        - ["$.code", 0]
        - ["$.data.token", "not_null"]             # ← 内置匹配器：非空校验

  - case_id: LOGIN_002
    title: "密码错误返回401"
    mark: regression               # ← 自动打 @pytest.mark.regression
    request:
      method: post
      url: /api/auth/login
      json:
        username: "${accounts.default.username}"
        password: wrong_pwd
    expect:
      status_code: 401
      json_path:
        - ["$.message", "用户名或密码错误"]
```

用例侧只需一行加载，`mark` 字段会自动映射为 pytest 标记：

```python
from utils.case_runner import run_simple_case
from utils.data_loader import load_parametrize_data

LOGIN_DATA = load_parametrize_data("login.yaml", "test_login")

@pytest.mark.parametrize("case_id, case_data", LOGIN_DATA)
def test_login(self, http, case_id, case_data):
    allure.dynamic.title(f"[{case_id}] {case_data['title']}")
    run_simple_case(http, case_data)
```

这样 `pytest -m smoke` 就能找到 YAML 中标记了 `mark: smoke` 的用例。`run_simple_case` 是无 setup/teardown 的单请求执行器，适合登录这类无副作用的接口。

### YAML 数据驱动 + DB 校验

`test_generic_isolated.py` 中的 `TestOrderIsolated` 用 `run_flow_case` 执行器跑完整流程：setup → request → json_path 断言 → db_check 数据库断言 → teardown。setup 返回的 JSON 数据会写入 context，后续 request / db_check / teardown 可通过 `${setup.xxx}` 引用。

```yaml
test_order_isolated:
  - case_id: ORDER_ISO_001
    title: "创建订单后查询"
    mark: smoke
    setup:                              # ← 前置：创建订单
      method: post
      url: /api/orders
      json:
        product_id: "SKU_ISO_001"
        quantity: 1
    request:
      method: get
      url: "/api/orders/${setup.order_id}"    # ← 模板变量，引用 setup 返回的数据
    expect:
      status_code: 200
      json_path:
        - ["$.data.status", "pending"]
      db_check:                                # ← 数据库校验
        - table: orders
          where: "order_id = %s"
          params: ["${setup.order_id}"]        # ← 模板变量也支持在 params 中使用
          field: status
          expected: "pending"
    teardown:                           # ← 清理：删除订单（失败会记 warning，不中断）
      method: delete
      url: "/api/orders/${setup.order_id}"
```

用例侧调用：

```python
from utils.case_runner import run_flow_case
from utils.data_loader import load_parametrize_data

ORDER_ISO_DATA = load_parametrize_data("order.yaml", "test_order_isolated")

@pytest.mark.parametrize("case_id, case_data", ORDER_ISO_DATA)
def test_order_flow(self, logged_in_http, db, case_id, case_data):
    allure.dynamic.title(f"[{case_id}] {case_data['title']}")
    run_flow_case(logged_in_http, case_data, db=db, case_id=case_id)
```

**模板变量解析规则**（由 `utils/case_runner.py` 实现）：

- `${accounts.default.username}` → 引用 `test_accounts.yaml` 中的账号
- `${setup.order_id}` → 引用 setup 阶段返回 JSON 的 `data.order_id` 字段
- 支持 str / list / dict 递归解析（任何层级的字符串字段都可含模板）
- 如果变量路径不存在，抛出 `KeyError` 并指明失败的路径 + 当前可用 context keys（如 `['accounts', 'setup']`）

**`expect.json_path` 匹配器**：

- 普通值 → 严格相等（`==`）
- `"not_null"` → 仅校验非 None（适合 token 等动态字段）
- 路径语法基于 [jsonpath-ng](https://github.com/h2non/jsonpath-ng)，除 `$.a.b.c` / `$.list[0].name` 外，还支持：
  - `$.list[*].name` — 数组通配符
  - `$..key` — 递归下降
  - `$[?(@.status=='ok')]` — 过滤器表达式

**`expect.db_check` 数据库断言**：列表，每项含 `table / where / params / field / expected` 五个键，参数走 `%s` 占位符防注入。`table` 和 `field` 在 `DBClient` 入口处走正则白名单校验（仅允许字母数字下划线），避免拼接到 SQL 时被注入。`where` / `params` 中的 `${...}` 模板变量会被 `resolve_value` 递归解析，支持嵌套 list / dict。

### 隔离数据工厂 & 用户身份隔离

`testcases/conftest.py` 提供两类 fixture：**业务数据工厂**（用 default 用户身份造数据）和**用户身份隔离**（每条用例注册全新用户、独立 HttpClient 实例）。所有 fixture 都是 function 级，每条用例独立创建、独立清理，天然并发安全。

```python
def test_query_order(self, fresh_order, logged_in_http):
    """fresh_order 自动创建独立订单，用例结束后自动删除"""
    resp = logged_in_http.get(f"/api/orders/{fresh_order}")
    assert resp.status_code == 200
```

**可用的 fixture**：

| Fixture | 作用域 | 说明 |
|---------|--------|------|
| `case_boundary` | function (autouse) | 每条用例打印分隔线（含 worker_id），纯日志无状态 |
| `http` | session | 未登录的 HTTP 客户端（每个 worker 一份） |
| `logged_in_http` | session | 已登录的 HTTP 客户端（用 default 账号，session 级，登录一次） |
| `db` | session | 数据库客户端（跟随 `--env` 参数选择环境） |
| `user_http` | function | 独立 HttpClient 实例（与 session 级 http 完全隔离，用例结束自动 close） |
| `new_user` | function | 注册一个随机用户（username 加 uuid 后缀），返回 `{token, user_id, username, auth_header}`；teardown 从 DB 按外键依赖逐表清理 |
| `authed_user_http` | function | `user_http + new_user` 组合体：独立实例上设置新用户 token，调用方拿到的 client 已带 Authorization header |
| `fresh_order` | function | 独立订单（default 用户身份创建，用例结束 DELETE 清理） |
| `fresh_project` | function | 独立项目（default 用户身份，自动 DELETE 清理） |
| `fresh_task` | function | 独立任务（依赖 `fresh_project`，task 随 project 级联删除） |
| `fresh_upload_token` | function | 独立上传凭证（default 用户身份，teardown 调 `DELETE /api/files/<file_key>`） |
| `another_user_file_key` | function | 以**新用户身份**获取 upload token（复用 `authed_user_http`），用于跨用户权限校验用例 |

**多用户身份隔离模式**（`test_generic_isolated.py::TestUserScoped`）：

`authed_user_http` 是 `user_http`（独立 HttpClient 实例）+ `new_user`（随机注册的新用户）的组合：在独立实例上设置新用户 token，不影响 session 级 `logged_in_http`。用例拿到时已带好 `Authorization` header，可直接发请求；用例结束后 `user_http` 被销毁，header 随之消失，零残留。

```python
@allure.story("跨用户权限隔离")
def test_user_http_cannot_see_others_order(
    self, authed_user_http, fresh_order
):
    """新用户访问 default 用户的订单，应返回 404。
    authed_user_http 自带新用户 token（由 new_user 提供），
    fresh_order 由 default 用户创建，两者身份天然不同。"""
    resp = authed_user_http.get(f"/api/orders/{fresh_order}")
    assert resp.status_code == 404
```

这种模式天然避免了"shared HttpClient 实例导致 token 污染"的并发隐患，是测试多用户权限隔离场景的标准写法。

> **注册接口用例**（`testcases/test_register.py`）：因为 `new_user` fixture 是已注册完成的状态，不能用于测试 `POST /api/auth/register` 本身，所以这个文件用 `user_http` + 随机用户名 + `db.execute` 直连清理的方式自包含测试 register 的正向 / 幂等 / 缺参数 / 空 body 行为。

> **跨用户 commit 安全校验**（`test_file_upload.py::test_commit_cross_user_forbidden`）：用 `authed_user_http`（新用户身份）提交 `fresh_upload_token`（default 用户创建的 file_key），断言 Mock 的 `commit_file` 通过 `user_id` 归属校验返回 400。这是 commit 接口的核心安全用例。

## 运行测试

```bash
# 全部用例
pytest

# 指定标记
pytest -m smoke
pytest -m regression

# 并发执行
pytest -n auto          # 自动检测 CPU 核心数
pytest -n 4             # 指定 4 个 worker

# 失败重试（覆盖 pytest.ini 的默认值）
pytest --reruns 3 --reruns-delay 5

# 指定环境
pytest --env=dev

# 清空 allure-results 后重新跑（避免旧报告残留）
pytest --clean-alluredir

# 组合使用
pytest -m smoke -n 4 --reruns 2 --reruns-delay 1 --env=dev --clean-alluredir -v
```

## Allure 报告

```bash
# 生成报告
allure generate reports/allure-results -o reports/allure-report --clean

# 本地预览
allure open reports/allure-report

# 一步到位（启动临时服务器）
allure serve reports/allure-results
```

报告包含：

- **Epic → Feature → Story** 三级业务视图
- 每条用例的请求/响应 JSON 附件（敏感字段已脱敏：password/token/authorization 自动替换为 `***`）
- 失败用例的断言堆栈 + 日志
- environment.properties（环境参数）+ executor.json（Jenkins 构建信息）
- 趋势图（需配置 history）

> **敏感字段脱敏**：`common/sanitize.py` 在 `HttpClient` 写日志/Allure 附件前递归脱敏，覆盖 `password / token / authorization / secret / access_token / db_password / refresh_token` 等键名。`Authorization` header 显示为 `Bearer ***`。报告和日志都不会泄露真实凭证。

## Jenkins 集成

### 前置条件

1. Jenkins 安装插件：Allure Jenkins Plugin、Git Plugin、Pipeline、Email Extension、HTTP Request Plugin、Build User Vars
2. Jenkins 服务器上有 Python 3.9+ 环境（路径在 `Jenkinsfile` 的 `environment.PYTHON_PATH` 中配置）
3. Allure Commandline 已配置（Manage Jenkins → Tools）
4. MySQL 已安装并执行过 `init.sql`
5. **创建 Jenkins 凭证**（避免硬编码敏感信息）：
   - 类型 `Secret text`，ID 填 `dingtalk_webhook`，Secret 粘贴钉钉机器人 Webhook 完整 URL
   - （可选）类型 `Username with password`，ID 填入 `environment.GIT_CREDENTIALS_ID` 用作私有仓库 Git 拉取

### Pipeline 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `ENV` | 运行环境 | `dev` |
| `MARK` | 用例标记 | `all` |
| `RERUNS` | 失败重试次数 | `3` |
| `RERUNS_DELAY` | 失败重试间隔（秒） | `1` |
| `PARALLEL` | 并发模式（off/auto/2/3/4/5/10） | `off` |

### Pipeline 阶段结构

`Jenkinsfile` 分四个主阶段，每个主阶段下含子阶段：

| 阶段 | 子阶段 | 说明 |
|------|--------|------|
| **1. 信息采集 & 准备** | 1.1 清理工作区 | 删除 `__pycache__` / `.pytest_cache` / 旧报告 / 旧日志 / `diagnostics` |
| | 1.2 获取构建用户 | 通过 Build User Vars 插件拿到触发者 ID |
| | 1.3 拉取代码 | `git` 步骤（retry 3 次应对网络抖动） |
| | 1.4 安装 Python 依赖 | `pip install -r requirements.txt`（retry 3 次 + 10 分钟超时） |
| **2. Mock 与数据重置** | 2.1 启动 Mock 服务 | 调 `ensure_mock.py start` + `status` 健康检查（最多等 30 秒） |
| | 2.2 重置测试数据 | 调 `ensure_mock.py reset-db` 清空业务表（**失败即 `error` 终止流水线，拒绝在脏数据上跑测试**） |
| **3. 执行测试 & 写环境信息** | 3.1 执行 Pytest 测试 | 按 `MARK` / `PARALLEL` / `RERUNS` 拼接命令，`catchError` 包裹保证失败不中断报告生成 |
| | 3.2 写入 Allure 环境 & 执行器信息 | 写 `environment.properties` + `executor.json` |
| **4. 生成 Allure 报告** | — | `allure` 步骤（`reportBuildPolicy: 'ALWAYS'` 总是生成） |
| **post** | always | 停止 Mock + 归档 `logs/*.log` + 打印构建耗时大盘点 |
| | success | 发送成功通知 |
| | failure | 收集 `diagnostics/`（`db-status` 快照 + 日志）+ 归档 + 发送失败通知 |

> **dev 环境专有逻辑**：阶段 2 全程只在 `ENV == 'dev'` 时执行；`post.always` 中停止 Mock 也只针对 dev。prod 环境跳过所有 Mock 操作，直接进入阶段 3 跑接口测试。

> **统一 Python 命令封装**：所有 Python 调用走 `pythonCmd(pyArgs, extraArgs)` 辅助函数，自动加 `chcp 65001`（中文不乱码）+ 拼接 `PYTHON_PATH`，避免每个 `bat` 块重复样板代码。

> **失败诊断信息**：测试失败时自动收集 `diagnostics/db_status.txt`（各业务表数据量快照）+ 复制 `logs/*.log`，归档到 Jenkins Artifacts 的 `diagnostics/` 目录，便于事后定位"是数据残留还是用例本身的问题"。

### 触发方式

**定时构建** — 每天凌晨 2 点执行回归测试：

```
H 2 * * *
```

**轮询代码** — 每 5 分钟检查 Git 是否有新提交：

```
TZ=Asia/Shanghai
H/5 * * * *
```

**GitHub Webhook** — 推送代码即时触发（需安装 GitHub 插件）。

### 通知

Pipeline 构建完成后通过 `notifyAll(status, color, icon)` 统一入口发送：

- **邮件通知**：通过 Email Extension 插件（HTML 邮件，含构建号/状态/触发人/并发模式/重试次数/报告链接）
- **钉钉通知**：通过钉钉机器人 Webhook（Markdown 格式，含与邮件相同的关键信息 + 报告链接）
- 钉钉 Webhook URL 走 Jenkins Credentials（ID: `dingtalk_webhook`），不硬编码在 Jenkinsfile 中

## 进阶功能

### 数据库校验

`utils/db.py` 基于 PooledDB 连接池，数据库配置从 `config.yaml` 读取：

```python
# 查询多条
rows = db.query("SELECT * FROM orders WHERE user_id = %s", (10086,))

# 查询单条
row = db.query_one("SELECT * FROM orders WHERE order_id = %s", ("ORD001",))

# 计数
cnt = db.count("orders", "user_id = %s AND status = %s", (10086, "pending"))

# 断言字段值
db.assert_field_value(
    "orders", "order_id = %s", ("ORD001",),
    field="status", expected="pending"
)

# 断言记录存在
db.assert_record_exists("orders", "order_id = %s", ("ORD001",))
```

> **SQL 注入防护**：`count` / `assert_field_value` 等接收外部 `table` / `field` 的方法会在执行前通过 `_validate_identifier` 正则校验（仅允许 `[A-Za-z_][A-Za-z0-9_]*`），不合法直接 `ValueError` 拒绝。`query` / `execute` / `query_one` 中的 `cursor.execute` 包了 try-except，异常会经 `log.error` 落盘后再向上抛，保证 Jenkins 失败归档日志完整。

### 失败重试

三种粒度，优先级：**装饰器 > 命令行 > ini 配置**

```bash
# 命令行（推荐 Jenkins）
pytest --reruns 3 --reruns-delay 5
```

```ini
# pytest.ini 全局配置（当前已启用）
addopts = --reruns 2 --reruns-delay 1
```

```python
# 装饰器（单条用例精细控制）
@pytest.mark.flaky(reruns=5, reruns_delay=2)
def test_unstable_case(self):
    ...
```

### 并发执行

基于 `pytest-xdist`，每条用例独立、互不干扰：

```bash
pytest -n auto    # 自动检测核心数
pytest -n 4       # 指定 worker 数
```

并发模式下：
- `logged_in_http` fixture 每个 worker 各自登录一次（session 级 + xdist 隔离）
- `user_http / new_user / authed_user_http` 每条用例独立实例 + 随机用户名，多 worker 互不冲突
- 数据工厂 fixture（`fresh_order` 等）为每条用例创建独立数据
- Mock 服务使用共享连接池（`common/db_pool.py`，`maxconnections=20`）+ 多线程，支持并发访问；token 存储、故障计数器均使用线程锁

> **注意**：并发模式下数据库连接数会随 worker 数增加（每个 worker 独立连接池），确保 MySQL 的 `max_connections` 足够（默认 151，一般够用）。

### Mock 服务故障注入

`mock_flask.py` 内置了故障注入机制（`FAULT_COUNT=2`），登录接口在**密码错误**时，前 2 次返回 500 而非 401，用于模拟服务临时故障场景。

故障计数器**按用户名隔离**（`_fault_counters` dict + `_fault_lock` 线程锁），多 worker 并发请求不同用户互不干扰，不会出现"全局计数器被其他 worker 消耗掉"的问题。

这意味着：
- **LOGIN_002（密码错误）** 用例会先触发 2 次 500，靠 `--reruns` 重试后才拿到 401 通过
- 这是预期行为，验证了框架的重试机制在服务抖动时仍能正常工作
- 如果要测试纯业务逻辑（不关心故障注入），可以将 `mock_flask.py` 中的 `FAULT_COUNT` 改为 `0`

> **Mock 服务日志**：`mock_flask.py` 复用 `common.logger`（与 pytest 同一 logger），故障注入触发记 `log.warning`，登录失败记 `log.info`，`/api/ping` DB 健康检查异常记 `log.error`，启动时打印一行 `log.info`。所有日志会落到 `logs/{当天日期}.log`，Jenkins `post.always` 会自动归档，便于事后定位。

## 数据库表结构

`init.sql` 创建的表结构如下：

```
users
├── user_id (PK, AUTO_INCREMENT)
├── username (UNIQUE)
├── password
└── avatar

orders
├── order_id (PK)
├── user_id (INDEX)
├── product_id
├── quantity
├── address
└── status

projects
├── id (PK)
├── name
└── user_id (INDEX)

tasks
├── id (PK)
├── project_id (FK → projects.id, CASCADE DELETE)
├── title
├── priority
└── status

file_uploads
├── file_key (PK)
├── file_name
├── file_type
├── user_id (INDEX)
└── committed
```

## 常见问题

**Q: 启动 mock_flask.py 报 `pymysql.err.OperationalError: Can't connect to MySQL`？**

确认 MySQL 已启动，且 `config/config.yaml` 中 `dev` 环境的数据库配置（db_host/db_port/db_user/db_password）正确。

**Q: 报 `Table 'api_test.xxx' doesn't exist`？**

没有执行 `init.sql`。运行 `mysql -u root -p < init.sql` 初始化数据库。

**Q: 登录测试报 `用户名或密码错误`？**

确认 `users` 表中存在种子数据。执行：

```sql
USE api_test;
SELECT * FROM users;
```

应该有 `testuser` / `Test@123` 的记录。如果没有，重新执行 `init.sql`。

**Q: LOGIN_002（密码错误）先返回 500 再重试才通过？**

这是 `mock_flask.py` 故障注入机制的预期行为。登录接口前 2 次错误请求会返回 500 模拟服务故障，`pytest.ini` 中的 `--reruns 2` 会自动重试。如果不想触发故障注入，将 `mock_flask.py` 中的 `FAULT_COUNT` 改为 `0`。

**Q: Allure 报告样式错乱？**

Jenkins 的 CSP 限制导致。在 Jenkins 脚本控制台执行：

```groovy
System.setProperty("hudson.model.DirectoryBrowserSupport.CSP", "")
```

**Q: pytest 有用例失败导致 Pipeline 中断？**

Pipeline 中已用 `catchError` 包裹测试阶段（stage 3.1），保证报告阶段继续执行。

**Q: 如何切换测试环境？**

```bash
pytest --env=prod
```

对应 `config/config.yaml` 中的 `env.prod` 配置。数据库和 HTTP 客户端都会跟随切换。

**Q: `ensure_mock.py` 怎么用？为什么 Jenkins 不直接 `python mock_flask.py`？**

`ensure_mock.py` 托管了 Mock 服务的完整生命周期：start / status / stop / reset-db / db-status。直接 `python mock_flask.py` 是前台进程，Jenkins 构建结束时会被 Windows JobObject 自动 kill，且没有 PID 文件管理、没有健康检查、没有数据重置兜底。Jenkinsfile 用 `ensure_mock.py` 实现了：

- **start** — 已在跑就跳过；没在跑就后台启动 + 写 PID 文件 + 探测就绪（最多 30 秒）
- **status** — 健康检查（探测 `/` 端点 + 检查 PID 进程是否存活）
- **stop** — 按 PID 文件 kill；PID 失效则按端口占用兜底清理
- **reset-db** — 跑测试前清空业务表残留（`tasks / file_uploads / orders / projects`，保留 `users` 种子数据）；**失败即终止流水线**，拒绝在脏数据上跑测试
- **db-status** — 失败时打印各表数据量快照到 `diagnostics/db_status.txt`

**Q: 数据库业务表数据为什么会越积越多？**

正常情况下 fixture teardown 会清理自己造的数据。但有两种情况会残留：

1. **构建被中断** — teardown 来不及执行，`fresh_order` / `fresh_upload_token` 等创建的数据留在表里
2. **fixture 缺 teardown** — 历史版本部分 fixture（如 `fresh_upload_token`）曾经没有清理逻辑，现在已修复

Jenkinsfile stage 2.2 在每次跑测试前调 `ensure_mock.py reset-db` 兜底清空，确保每次构建都从干净状态开始。手动清理用：

```bash
python scripts/ensure_mock.py reset-db --env dev
python scripts/ensure_mock.py db-status --env dev   # 查看清理后状态
```

**Q: Windows CMD 下 `python -c "..."` 多行命令报语法错误？**

Windows CMD 会把 `python -c` 后的参数按空格拆成多条命令。解决办法：用双引号包裹整段代码，且写在一行（用 `;` 分隔）。Jenkinsfile 中提供了 `pythonCmd(pyArgs, extraArgs)` 辅助函数统一处理 `chcp 65001` 编码 + `PYTHON_PATH` 拼接，避免每次手写样板。

**Q: 钉钉通知发送失败？**

检查三件事：
1. Jenkins 后台是否已创建 ID 为 `dingtalk_webhook` 的 Secret text 凭证（值为钉钉机器人完整 Webhook URL）
2. 钉钉机器人是否设置了安全关键词（Jenkinsfile 中默认关键词为 `测试`，见 `environment.DINGTALK_KEYWORD`）
3. Jenkins 是否安装了 HTTP Request Plugin（用于发 HTTP 请求到钉钉 Webhook）

**Q: 怎么在 Jenkins 失败时排查是数据残留还是用例本身的问题？**

打开该次构建的 Artifacts → `diagnostics/` 目录：
- `db_status.txt` — 各业务表数据量快照（失败现场）
- `*.log` — 复制过来的 pytest / mock 日志

如果 `orders / projects / tasks / file_uploads` 任一表数据量异常大，多半是上一次构建中断导致的数据残留；下次构建的 stage 2.2 会自动清空。

## License

MIT
