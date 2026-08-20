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
│   └── yaml_handler.py         # YAML 配置读取
├── config/
│   ├── config.yaml             # 多环境配置（dev/prod）
│   └── testdata/               # 测试数据（YAML）
│       ├── login.yaml
│       └── order.yaml
├── testcases/                  # 测试用例
│   ├── conftest.py             # 业务级 fixture（数据工厂）
│   ├── test_login.py           # 登录模块
│   ├── test_order.py           # 订单模块
│   ├── test_profile.py         # 个人信息模块
│   ├── test_project_task.py    # 项目与任务模块
│   ├── test_file_upload.py     # 文件上传模块
│   └── test_generic_isolated.py # 通用隔离数据驱动用例
├── utils/                      # 工具类
│   ├── data_loader.py          # 测试数据加载器
│   ├── jsonpath_util.py        # 简易 JSONPath 提取
│   └── db.py                   # 数据库操作客户端
├── mock_flask.py               # Mock API 服务（并发安全）
├── init.sql                    # 数据库建表 + 种子数据
├── conftest.py                 # 全局 fixture（HTTP 客户端、登录、DB）
├── pytest.ini                  # pytest 配置
├── Jenkinsfile                 # Jenkins Pipeline 脚本
├── requirements.txt            # Python 依赖
└── main.py                     # 入口（未使用，可删除）
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

```bash
python mock_flask.py
```

服务默认运行在 `http://127.0.0.1:5000`，使用多线程模式处理并发请求。

Mock 服务会连接本地 MySQL（`localhost:3306`，用户 `root`，密码 `Root@123456`，数据库 `api_test`）。如果你的 MySQL 配置不同，需要修改 `mock_flask.py` 中的 `DB_POOL` 配置。

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
    timeout: 10
  prod:
    base_url: "https://api.example.com"
    timeout: 15
```

通过 `--env` 参数切换环境：

```bash
pytest --env=prod
```

### pytest 配置 `pytest.ini`

| 配置项 | 说明 |
|--------|------|
| `testpaths` | 用例目录：`testcases` |
| `markers` | 自定义标记：`smoke`（冒烟）、`regression`（回归） |
| `addopts` | 默认参数：`-v -s --alluredir=./reports/allure-results --reruns 2 --reruns-delay 3` |

> `--reruns 2` 表示失败用例自动重试 2 次，间隔 3 秒。这是全局默认值，命令行参数可以覆盖。

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

### 数据驱动

在 `config/testdata/` 下创建 YAML 数据文件：

```yaml
test_login:
  - case_id: "login_001"
    title: "正常登录"
    mark: smoke
    request:
      method: post
      url: /api/auth/login
      json:
        username: "testuser"
        password: "Test@123"
    expect:
      status_code: 200
      json_path:
        - ["$.code", 0]
        - ["$.data.token", "not_null"]
```

用例中加载并参数化：

```python
from utils.data_loader import load_test_data

LOGIN_DATA = load_test_data("login.yaml", "test_login")

@pytest.mark.parametrize("case_id, case_data", LOGIN_DATA,
                         ids=[d[0] for d in LOGIN_DATA])
def test_login(self, http, case_id, case_data):
    ...
```

### 隔离数据工厂

`testcases/conftest.py` 提供了 function 级 fixture，每条用例独立创建、独立清理，天然并发安全：

```python
def test_query_order(self, fresh_order, logged_in_http):
    """fresh_order 自动创建独立订单，用例结束后自动删除"""
    resp = logged_in_http.get(f"/api/orders/{fresh_order}")
    assert resp.status_code == 200
```

可用的 fixture：

| Fixture | 说明 |
|---------|------|
| `http` | 未登录的 HTTP 客户端 |
| `logged_in_http` | 已登录的 HTTP 客户端（session 级，每个 worker 登录一次） |
| `db` | 数据库客户端 |
| `fresh_order` | 独立订单（自动创建 + 清理） |
| `fresh_project` | 独立项目（自动创建 + 清理） |
| `fresh_task` | 独立任务（依赖 fresh_project） |
| `fresh_upload_token` | 独立上传凭证 |

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

# 组合使用
pytest -m smoke -n 4 --reruns 2 --env=dev -v
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
- 每条用例的请求/响应 JSON 附件
- 失败用例的断言堆栈 + 日志
- 趋势图（需配置 history）

## Jenkins 集成

### 前置条件

1. Jenkins 安装插件：Allure Jenkins Plugin、Git Plugin、Pipeline、Email Extension
2. Jenkins 服务器上有 Python 3.9+ 环境
3. Allure Commandline 已配置（Manage Jenkins → Tools）
4. MySQL 已安装并执行过 `init.sql`

### Pipeline 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `ENV` | 运行环境 | `dev` |
| `MARK` | 用例标记 | `all` |
| `RERUNS` | 失败重试次数 | `3` |
| `PARALLEL` | 并发模式 | `off` |

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

Pipeline 构建完成后自动发送：

- **邮件通知**：通过 Email Extension 插件
- **钉钉通知**：通过钉钉机器人 Webhook

## 进阶功能

### 数据库校验

`utils/db.py` 提供了轻量级数据库操作客户端：

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

### 失败重试

三种粒度，优先级：**装饰器 > 命令行 > ini 配置**

```bash
# 命令行（推荐 Jenkins）
pytest --reruns 3 --reruns-delay 5
```

```ini
# pytest.ini 全局配置（当前已启用）
addopts = --reruns 2 --reruns-delay 3
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
- `logged_in_http` fixture 每个 worker 各自登录一次
- 数据工厂 fixture 为每条用例创建独立数据
- Mock 服务使用连接池 + 多线程，支持并发访问

> **注意**：并发模式下数据库连接数会随 worker 数增加，确保 MySQL 的 `max_connections` 足够（默认 151，一般够用）。

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

确认 MySQL 已启动，且 `mock_flask.py` 中的数据库连接配置（host/port/user/password）正确。默认连接 `localhost:3306`，用户 `root`，密码 `Root@123456`，数据库 `api_test`。

**Q: 报 `Table 'api_test.xxx' doesn't exist`？**

没有执行 `init.sql`。运行 `mysql -u root -p < init.sql` 初始化数据库。

**Q: 登录测试报 `用户名或密码错误`？**

确认 `users` 表中存在种子数据。执行：

```sql
USE api_test;
SELECT * FROM users;
```

应该有 `testuser` / `Test@123` 的记录。如果没有，重新执行 `init.sql`。

**Q: Allure 报告样式错乱？**

Jenkins 的 CSP 限制导致。在 Jenkins 脚本控制台执行：

```groovy
System.setProperty("hudson.model.DirectoryBrowserSupport.CSP", "")
```

**Q: pytest 有用例失败导致 Pipeline 中断？**

Pipeline 中已用 `catchError` 包裹测试阶段，保证报告阶段继续执行。

**Q: 如何切换测试环境？**

```bash
pytest --env=prod
```

对应 `config/config.yaml` 中的 `env.prod` 配置。

## License

MIT
