# Python 接口自动化测试框架 · 手把手完整教程 

## 📋 阶段一：整体架构设计（先想清楚再动手）

```
┌─────────────────────────────────────────────────┐
│                  Jenkins (CI调度层)               │
│         定时触发 / Git提交触发 / 手动触发          │
├─────────────────────────────────────────────────┤
│            pytest (测试执行引擎)                  │
│   用例收集 → 执行 → fixture管理 → 断言            │
├──────────────┬──────────────┬───────────────────┤
│  requests    │  yaml 配置    │   allure 报告     │
│  (HTTP请求)  │  (数据驱动)   │   (结果展示)      │
├──────────────┴──────────────┴───────────────────┤
│              公共层：日志 / 数据库 / 工具类         │
└─────────────────────────────────────────────────┘
```

核心设计思想：分层解耦

配置层：环境地址、账号密码不写死在代码里

请求层：封装 requests，统一处理 header、日志、重试

用例层：只做断言，不关心底层实现

数据层：测试数据用 YAML 管理，与代码分离

## 📋 阶段二：环境准备

### 2.1 安装 Python 3.9+ 后，创建项目目录

```
api_test/
├── common/                 # 公共模块
│   ├── __init__.py
│   ├── http_client.py      # requests 封装
│   ├── logger.py           # 日志
│   └── yaml_handler.py     # YAML 读写
├── config/                 # 配置文件
│   ├── config.yaml         # 环境配置
│   └── testdata/           # 测试数据
│       └── login.yaml
├── testcases/              # 测试用例
│   ├── __init__.py
│   ├── conftest.py         # pytest fixture
│   └── test_login.py
├── utils/                  # 工具类
│   ├── __init__.py
│   ├── data_loader.py      # 数据加载器
│   ├── db.py               # 数据库操作
│   └── jsonpath_util.py    # JSONPath 提取工具
├── reports/                # 测试报告输出
├── logs/                   # 日志输出
├── conftest.py             # 全局 fixture
├── pytest.ini              # pytest 配置
└── requirements.txt        # 依赖清单
```

### 2.2 安装依赖

pip install -r requirements.txt

```
pip install -r requirements.txt
```

requirements.txt：

```
requests==2.31.0       
pytest==7.4.4          
allure-pytest==2.13.2  
PyYAML==6.0.1          
pytest-html>=4.0.0     
```

⚠️ Allure 还需要单独下载 Allure Commandline（Java 环境）：

从 https://github.com/allure-framework/allure2/releases 下载，解压后把 bin 目录加入系统 PATH，验证：allure --version

npm install -g allure-commandline --force

把 dist\bin 加到用户及系统 PATH 最前面（优先级最高）$allurePath = "C:\Users\27088\AppData\Roaming\npm\node_modules\allure-commandline\dist\bin"

## 📋 阶段三：配置文件管理（config 层）

### 3.1 config/config.yaml

```
# 多环境配置，通过命令行参数切换
env:
  dev:
    base_url: "http://127.0.0.1:5000"
    db_host: "192.168.1.100"
    db_port: 3306
    db_user: "test"
    db_password: "test123"
  prod:
    base_url: "https://api.example.com"
    db_host: "10.0.0.1"
    db_port: 3306
    db_user: "readonly"
    db_password: "xxx"

timeout: 10
retry: 2
```

### 3.2 common/yaml_handler.py

```
import yaml
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def read_yaml(file_path):
    """读取 YAML 文件，返回字典"""
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_config(env="dev"):
    """获取指定环境配置"""
    config = read_yaml(os.path.join(BASE_DIR, "config", "config.yaml"))
    return config["env"][env]
```

## 📋 阶段四：日志模块（common/logger.py）

日志是排查失败用例的命脉，一定要先搭好。

```
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def get_logger(name="api_test"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if logger.handlers:  # 避免重复添加
        return logger

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )

    # 控制台
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # 文件（按天 + 大小滚动）
    log_file = os.path.join(LOG_DIR, f"{datetime.now():%Y-%m-%d}.log")
    fh = RotatingFileHandler(log_file, maxBytes=10*1024*1024,
                             backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger

log = get_logger()
```

## 📋 阶段五：requests 核心封装 ⭐（框架的心脏）

common/http_client.py——这是整个框架最关键的文件：

```
import requests
import allure
import json
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from common.logger import log

class HttpClient:
    def __init__(self, base_url, timeout=10, token=None):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

        # 自动重试机制：网络抖动时自动重试
        retry = Retry(total=2, backoff_factor=0.5,
                      status_forcelist=[502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def request(self, method, url, **kwargs):
        """统一请求入口：拼接URL + 日志 + Allure附件"""
        full_url = url if url.startswith("http") else self.base_url + url

        # 请求前日志
        log.info(f"➡️  请求: {method.upper()} {full_url}")
        log.info(f"   参数: {kwargs}")

        # Allure 记录请求详情
        allure.attach(
            json.dumps(kwargs, ensure_ascii=False, indent=2, default=str),
            name=f"请求-{method.upper()} {url}",
            attachment_type=allure.attachment_type.JSON
        )

        try:
            resp = self.session.request(
                method, full_url, timeout=self.timeout, **kwargs
            )
        except requests.exceptions.RequestException as e:
            log.error(f"❌ 请求异常: {e}")
            raise

        # 响应日志
        log.info(f"⬅️  状态码: {resp.status_code} | 耗时: {resp.elapsed.total_seconds()}s")
        try:
            log.info(f"   响应体: {resp.json()}")
        except Exception:
            log.info(f"   响应体(非JSON): {resp.text[:500]}")

        # Allure 记录响应
        allure.attach(
            resp.text,
            name=f"响应-{resp.status_code}",
            attachment_type=allure.attachment_type.JSON
            if "json" in resp.headers.get("Content-Type","")
            else allure.attachment_type.TEXT
        )
        return resp

    # 语法糖
    def get(self, url, **kwargs):    return self.request("GET", url, **kwargs)
    def post(self, url, **kwargs):   return self.request("POST", url, **kwargs)
    def put(self, url, **kwargs):    return self.request("PUT", url, **kwargs)
    def delete(self, url, **kwargs): return self.request("DELETE", url, **kwargs)
```

这个封装帮你解决了什么？

痛点

方案

每个用例都要写 base_url

构造时注入，自动拼接

失败了不知道请求了啥

日志 + Allure 自动记录请求/响应

网络抖动导致误报

Retry 自动重试

token 到处传

Session 级别统一注入 header

## 📋 阶段六：pytest 配置与 Fixture（全局 conftest.py）

### 6.1 根目录 pytest.ini

### 6.2 根目录 conftest.py（全局 fixture）

```
import pytest
import allure
from common.http_client import HttpClient
from common.yaml_handler import get_config

# 命令行传入环境：pytest --env=prod
def pytest_addoption(parser):
    parser.addoption("--env", default="dev", help="运行环境: dev/prod")

@pytest.fixture(scope="session")
def env_name(request):
    return request.config.getoption("--env")

@pytest.fixture(scope="session")
def http(env_name):
    """全局 HTTP 客户端，整个会话共用"""
    cfg = get_config(env_name)
    client = HttpClient(base_url=cfg["base_url"], timeout=cfg.get("timeout", 10))
    return client
```

### 6.3 testcases/conftest.py（业务级 fixture）

```
import pytest
import allure

@pytest.fixture(scope="class")
def login_token(http):
    """前置：登录获取 token，登录失败则后续用例直接跳过"""
    with allure.step("前置操作：用户登录"):
        resp = http.post("/api/auth/login", json={
            "username": "testuser",
            "password": "Test@123"
        })
        assert resp.status_code == 200, "登录失败，终止用例"
        token = resp.json()["data"]["token"]
        http.session.headers["Authorization"] = f"Bearer {token}"
        return token

@pytest.fixture(autouse=True)
def case_boundary(request):
    """每个用例前后自动打印分隔线"""
    print(f"\n{'='*50}\n▶ 开始用例: {request.node.name}\n{'='*50}")
    yield
    print(f"◀ 结束用例: {request.node.name}")
```

💡 fixture 的 scope 是性能关键：session 级登录只做一次，不要每个用例都登录！

## 📋 阶段七：数据驱动 + 用例编写 ⭐

### 7.1 测试数据外置：config/testdata/login.yaml

```
test_login:
  - case_id: LOGIN_001
    title: "正确账号密码登录成功"
    mark: smoke
    request:
      method: post
      url: /api/auth/login
      json:
        username: testuser
        password: Test@123
    expect:
      status_code: 200
      json_path:
        - ["$.code", 0]
        - ["$.data.token", "not_null"]

  - case_id: LOGIN_002
    title: "密码错误返回401"
    mark: regression
    request:
      method: post
      url: /api/auth/login
      json:
        username: testuser
        password: wrong_pwd
    expect:
      status_code: 401
      json_path:
        - ["$.message", "用户名或密码错误"]

  - case_id: LOGIN_003
    title: "缺少用户名参数返回400"
    mark: regression
    request:
      method: post
      url: /api/auth/login
      json:
        password: Test@123
    expect:
      status_code: 400
```

### 7.2 数据加载工具：utils/data_loader.py

```
import os
from common.yaml_handler import read_yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_test_data(file_name, key):
    """加载测试数据并转为 pytest 参数化格式"""
    path = os.path.join(BASE_DIR, "config", "testdata", file_name)
    data = read_yaml(path)[key]
    # 转成 (case_id, case_dict) 元组，方便参数化时显示用例ID
    return [(item["case_id"], item) for item in data]
```

### 7.3 编写用例：testcases/test_login.py

```
import pytest
import allure
from utils.data_loader import load_test_data
from utils.jsonpath_util import extract_json

# 加载 YAML 数据
LOGIN_DATA = load_test_data("login.yaml", "test_login")

@allure.epic("用户中心")
@allure.feature("登录模块")
class TestLogin:

    @pytest.mark.parametrize("case_id, case_data", LOGIN_DATA,
                             ids=[d[0] for d in LOGIN_DATA])
    def test_login(self, http, case_id, case_data):
        # 动态打标记
        if case_data.get("mark") == "smoke":
            pytest.mark.smoke

        allure.dynamic.story(case_data["title"])
        allure.dynamic.title(f"[{case_id}] {case_data['title']}")

        req = case_data["request"]
        expect = case_data["expect"]

        # 发起请求
        with allure.step(f"发送 {req['method'].upper()} 请求: {req['url']}"):
            resp = getattr(http, req["method"])(
                req["url"], **{k: v for k, v in req.items()
                               if k in ("json", "params", "data", "headers")}
            )

        # 断言状态码
        with allure.step(f"断言状态码 == {expect['status_code']}"):
            assert resp.status_code == expect["status_code"], \
                f"期望 {expect['status_code']}，实际 {resp.status_code}"

        # 断言 JSON 字段
        for path, expected_value in expect.get("json_path", []):
            with allure.step(f"断言 {path} == {expected_value}"):
                actual = extract_json(resp.json(), path)
                if expected_value == "not_null":
                    assert actual is not None, f"{path} 为空"
                else:
                    assert actual == expected_value, \
                        f"{path} 期望 {expected_value}，实际 {actual}"
```

### 7.4 JSONPath 提取工具：utils/jsonpath_util.py

```
def extract_json(data, path):
    """简易 JSONPath 实现，支持 $.a.b.c 和 $.list[0].name"""
    if path.startswith("$."):
        path = path[2:]
    keys = []
    for part in path.split("."):
        if "[" in part:  # 处理数组索引 user[0]
            key, idx = part.split("[")
            keys.append(key)
            keys.append(int(idx.rstrip("]")))
        else:
            keys.append(part)
    result = data
    for key in keys:
        try:
            result = result[key]
        except (KeyError, IndexError, TypeError):
            return None
    return result
```

## 📋 阶段八：Allure 报告生成

### 8.1 本地运行命令

# 1. 执行测试，生成结果数据pytest --env=dev --alluredir=./reports/allure-results --clean-alluredir# 2. 生成报告并打开网页allure generate ./reports/allure-results -o ./reports/allure-report --clean# 查看产物ls ./reports/allure-report# 打开报告allure serve ./reports/allure-results

```
# 1. 执行测试，生成结果数据
pytest --env=dev --alluredir=./reports/allure-results --clean-alluredir

# 2. 生成报告并打开网页
allure generate ./reports/allure-results -o ./reports/allure-report --clean

# 查看产物
ls ./reports/allure-report

# 打开报告
allure serve ./reports/allure-results
```

### 8.2 报告里能看到什么

✅ Epic → Feature → Story 三级业务视图

✅ 每个用例的请求/响应 JSON 附件

✅ 失败用例的完整断言堆栈 + 日志

✅ 趋势图（需要配置 history，Jenkins 部分会讲）

## 📋 阶段九：Jenkins 持续集成 ⭐

### 9.0 Jenkins 2.577 Windows 安装全流程总结

📋 安装流程

1️⃣ 下载安装包

从 Jenkins 官网下载 Windows 安装包（.msi 或 .exe）

2️⃣ 运行安装程序，逐步配置

步骤

页面

操作

①

Service Logon Credentials

选 Run service as LocalSystem（第一个选项），跳过账号密码

②

Select Java home directory

指定 JDK 21 的安装路径（点 Change 选择）

③

Custom Setup

Start Service ✅ + Firewall Exception ✅，点 Next

④

完成

等待安装结束

3️⃣ 安装完成后

浏览器访问 http://localhost:8080

按提示输入初始管理员密码（在安装目录的 secrets/initialAdminPassword 文件中）

安装推荐插件 → 创建管理员账号 → 开始使用

⚠️ 遇到的问题及解决

问题：Java 版本不兼容

报错信息：

```
Failed to find compatible Java version (21 or 25) in
"C:\Program Files\Eclipse Adoptium\jdk-17.0.20.8-hotspot"
```

原因：

Jenkins 2.577 要求 Java 21 或 25

系统现有的是 Java 17，版本太低

解决方案：额外安装 JDK 21（与现有 Java 17 共存）

下载 JDK 21（清华镜像）：

```
https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/x64/windows/
```

下载 .msi 文件

安装时选择自定义安装，关键设置：

选项

设置

原因

修改 PATH 变量值

❌ 不勾选

不污染现有 Java 环境

Associate .jar

❌ 不勾选

无所谓

设置或重写 JAVA_HOME

❌ 不勾选

最关键！不改 JAVA_HOME

JavaSoft registry keys

❌ 不勾选

不改注册表

全部保持红 ❌，直接点下一步

安装完成后，回到 Jenkins 安装界面，点 Change...，浏览到：

```
C:\Program Files\Eclipse Adoptium\jdk-21.x.x-hotspot\
```

选中该文件夹，点确定，继续安装

结果： JDK 21 安静安装在独立目录，不影响系统现有的 Java 17，只有 Jenkins 通过指定路径使用它。

💡 经验教训

Jenkins 新版本对 Java 版本要求越来越高，安装前先确认 Java 版本是否满足要求

多个 Java 版本可以共存，关键是安装新版本时不要改 PATH 和 JAVA_HOME

LocalSystem 跑服务对个人学习完全够用，不用纠结账号配置

防火墙规则记得勾上，省得后面访问不了再排查

### 9.1 Jenkins 前置准备

安装插件：

如果初始化进入安装失败，就跳过，随后再处理；Jenkins → Manage Jenkins → Plugins → Available plugins，搜索安装了；如果总是失败下载hpi文件：访问 Jenkins 插件官网：https://plugins.jenkins.io/；

搜索 Git及Allure，下载最新版的 .hpi 文件；

回到 Jenkins 的 Plugins -> Advanced settings 页面；

在 Deploy Plugin 区域，上传刚才下载的 .hpi 文件；

勾选 "Deploy when no jobs are running"，点击 Deploy。

系统配置 → 全局工具配置 → 添加 Allure Commandline

确保 Jenkins 服务器上有 Python 环境和依赖

目的：Jenkins 是个调度员，它需要调用你电脑上的 Python 来跑代码。

确认 Python 已安装：

打开你电脑上的 CMD（命令提示符），输入 python --version，如果能显示版本号（如 Python 3.9.x），说明你电脑上有 Python。

确认 Jenkins 能调用到它：

因为 Jenkins 是在你电脑上运行的服务，它默认能读取你电脑的环境变量。只要你电脑上有 Python，并且之前安装时勾选了“Add Python to PATH”，Jenkins 就能直接找到它。

安装项目依赖：

这一步不需要在 Jenkins 里配，而是写在 Jenkins 任务（Job）的构建脚本里。当 Jenkins 拉取你的代码后，会自动执行 pip install -r requirements.txt 来安装依赖（我们在后面的 Jenkinsfile 里已经写好了这一步）。

解除CSP限制

方法一：通过“脚本控制台”临时修改 (立即生效)

这个方法最快捷，修改后立即生效，但 Jenkins 重启后会失效。

在 Jenkins 首页，点击左侧菜单的 “系统管理” (Manage Jenkins)。

找到并点击 “脚本控制台” (Script Console)。

在文本框中输入以下命令，然后点击 “运行” (Run)：

groovy

这个命令会清空安全策略，允许加载所有资源

重新运行一次构建，Allure 报告应该就能正常显示了。

方法二：修改 jenkins.xml 配置文件 (永久生效)

如果你希望修改是永久性的，可以修改 Jenkins 的配置文件。这里以 Windows 系统常见的 .msi 安装方式为例

在 Jenkins 的安装目录中找到 jenkins.xml 文件

用记事本等文本编辑器打开它。

找到文件中的 <arguments> 标签

在 -jar 参数之前，添加 -Dhudson.model.DirectoryBrowserSupport.CSP=

保存文件，然后重启 Jenkins 服务使配置生效

### 9.2 新建 Pipeline 任务，Jenkinsfile 如下：

```
pipeline {
    agent any

    options {
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }

    parameters {
        choice(name: 'ENV', choices: ['dev', 'prod'], description: '选择运行环境')
        choice(name: 'MARK', choices: ['all', 'smoke', 'regression'], description: '选择用例标记')
    }

    environment {
        // ========== 系统路径 ==========
        PYTHON_PATH = 'C:/Users/27088/AppData/Local/Programs/Python/Python310/python.exe'

        // ========== Allure 命令完整路径（不依赖 PATH）==========
        ALLURE_CMD = 'C:/Users/27088/AppData/Roaming/npm/node_modules/allure-commandline/dist/bin/allure.bat'

        // ========== pip 依赖源 ==========
        PIP_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'

        // ========== Allure 报告相关 ==========
        ALLURE_RESULTS = 'reports/allure-results'
        ALLURE_REPORT_DIR = 'reports/allure-report'
        ALLURE_REPORT_NAME = 'AllureReport'

        // ========== 【关键】History 固定存储目录 ==========
        ALLURE_HISTORY_DIR = "C:/work/yss/allure-history/${env.JOB_NAME}"

        // ========== 邮件配置 ==========
        MAIL_RECIPIENT = 'yiming_2333@sina.com'

        // ========== 编码设置 ==========
        PYTHONIOENCODING = 'utf-8'

        // ========== Git 配置 ==========
        GIT_URL = 'https://github.com/yiming2333/api_test.git'
        GIT_BRANCH = 'master'
        GIT_CREDENTIALS_ID = ''

        // ========== 报告链接 ==========
        REPORT_LINK = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/${env.ALLURE_REPORT_NAME}/"
    }

    stages {
        stage('0. 获取构建用户') {
            steps {
                script {
                    try {
                        wrap([$class: 'BuildUser']) {
                            env.TRIGGER_USER = env.BUILD_USER_ID ?: '未知(插件未生效)'
                        }
                    } catch (e) {
                        echo "⚠️ 无法获取构建用户: ${e.message}"
                        env.TRIGGER_USER = '未知'
                    }
                    echo "本次构建触发人: ${env.TRIGGER_USER}"
                }
            }
        }

        stage('1. 拉取代码') {
            options { retry(60) }
            steps {
                echo "正在从 Git 拉取代码..."
                script {
                    def gitConfig = [branch: env.GIT_BRANCH, url: env.GIT_URL]
                    if (env.GIT_CREDENTIALS_ID?.trim()) {
                        gitConfig.credentialsId = env.GIT_CREDENTIALS_ID
                    }
                    git gitConfig
                }
            }
        }

        stage('2. 安装依赖') {
            steps {
                echo "正在安装 Python 依赖..."
                bat """
                    chcp 65001
                    "${PYTHON_PATH}" -m pip install -r requirements.txt -q -i ${PIP_INDEX_URL}
                """
            }
        }

        stage('3. 执行测试') {
            steps {
                echo "开始执行 Pytest 测试..."
                script {
                    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                        def markArg = params.MARK != 'all' ? "-m ${params.MARK}" : ""
                        bat """
                            chcp 65001
                            "${PYTHON_PATH}" -m pytest ${markArg} ^
                                --env=${params.ENV} ^
                                --alluredir=${ALLURE_RESULTS} ^
                                --clean-alluredir ^
                                -v
                        """
                    }
                }
            }
        }

        // ================================================================
        //  stage 3.5：写入 Allure Environment + Executor 元数据
        // ================================================================
        stage('3.5 写入 Allure 环境 & 执行器信息') {
            steps {
                script {
                    // ---------- 1. environment.properties ----------
                    def envProps = """
                        Environment=${params.ENV}
                        Python.Version=3.10
                        Pytest.Mark=${params.MARK}
                        Trigger.User=${env.TRIGGER_USER ?: 'unknown'}
                        Build.Number=${env.BUILD_NUMBER}
                        Git.Branch=${env.GIT_BRANCH}
                        Base.URL=${getBaseUrl(params.ENV)}
                        OS=Windows
                    """.stripIndent().trim()
                    writeFile file: "${ALLURE_RESULTS}/environment.properties", text: envProps, encoding: 'UTF-8'
                    echo "✅ environment.properties 已写入"

                    // ---------- 2. executor.json（纯 Groovy 手写，无需额外插件）----------
                    def reportUrl = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/${ALLURE_REPORT_NAME}/"
                    def buildUrl  = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/"
                    def jsonStr   = """{
                        "name": "Jenkins",
                        "type": "jenkins",
                        "url": "${env.JENKINS_URL}",
                        "buildOrder": ${env.BUILD_NUMBER},
                        "buildName": "#${env.BUILD_NUMBER}",
                        "buildUrl": "${buildUrl}",
                        "reportUrl": "${reportUrl}",
                        "reportName": "${ALLURE_REPORT_NAME}"
                    }"""
                    writeFile file: "${ALLURE_RESULTS}/executor.json", text: jsonStr, encoding: 'UTF-8'
                    echo "✅ executor.json 已写入"
                }
            }
        }

        // ================================================================
        //  stage 4：生成 Allure 报告 + Trend（完善版）
        // ================================================================
        stage('4. 生成并发布 Allure 报告') {
            steps {
                script {
                    // ---------- Step 1: 确保 history 固定目录存在 ----------
                    bat """
                        if not exist "${ALLURE_HISTORY_DIR}" mkdir "${ALLURE_HISTORY_DIR}"
                    """

                    // ---------- Step 2: 从固定目录拷贝 history 到本次 results ----------
                    if (fileExists("${ALLURE_HISTORY_DIR}/history.json")) {
                        echo "✅ 找到历史 Trend 数据，正在注入..."
                        bat """
                            chcp 65001
                            if not exist "${ALLURE_RESULTS}\\history" mkdir "${ALLURE_RESULTS}\\history"
                            xcopy /E /I /Y "${ALLURE_HISTORY_DIR}\\*" "${ALLURE_RESULTS}\\history\\" >nul
                        """
                    } else {
                        echo "ℹ️ 首次构建或无历史数据，跳过 history 注入"
                    }

                    // ---------- Step 3: 生成报告（写死 allure 路径，不依赖 PATH）----------
                    try {
                        bat """
                            chcp 65001
                            "${ALLURE_CMD}" generate "${ALLURE_RESULTS}" -o "${ALLURE_REPORT_DIR}" --clean
                        """
                        echo "✅ Allure 报告生成成功"
                    } catch (e) {
                        echo "❌ Allure 报告生成失败: ${e.message}"
                    }

                    // ---------- Step 4: 把新生成的 history 拷回固定目录（供下次使用）----------
                    if (fileExists("${ALLURE_REPORT_DIR}/history")) {
                        bat """
                            chcp 65001
                            xcopy /E /I /Y "${ALLURE_REPORT_DIR}\\history\\*" "${ALLURE_HISTORY_DIR}\\" >nul
                        """
                        echo "✅ History 已同步到固定目录: ${ALLURE_HISTORY_DIR}"
                    }
                }

                // ---------- Step 5: 发布 HTML 报告 ----------
                publishHTML([
                    reportDir: env.ALLURE_REPORT_DIR,
                    reportFiles: 'index.html',
                    reportName: env.ALLURE_REPORT_NAME,
                    allowMissing: true,
                    keepAll: true,
                    alwaysLinkToLastBuild: false
                ])
            }
        }
    }

    post {
        always {
            echo "流水线执行结束"
            archiveArtifacts artifacts: 'logs/*.log', allowEmptyArchive: true
            archiveArtifacts artifacts: 'reports/allure-report/history/**', allowEmptyArchive: true
        }

        success {
            echo "✅ 恭喜！所有测试用例通过！"
            script { sendEmailNotification('SUCCESS', 'green', '✅') }
        }

        failure {
            echo "❌ 存在失败的测试用例，请查看 Allure 报告。"
            script { sendEmailNotification('FAILURE', 'red', '❌') }
        }
    }
}

// ========== 根据环境参数返回 base_url ==========
def getBaseUrl(String envName) {
    def urls = [
        'dev' : 'http://127.0.0.1:5000',
        'prod': 'https://api.example.com'
    ]
    return urls[envName] ?: 'unknown'
}

// ========== 邮件发送函数 ==========
def sendEmailNotification(String status, String color, String icon) {
    emailext (
        to: env.MAIL_RECIPIENT,
        subject: "${icon} 测试${status == 'SUCCESS' ? '通过' : '失败'} - ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
        body: """
            <p>各位同事，大家好！</p>
            <p>项目 <strong>${env.JOB_NAME}</strong> 构建${status == 'SUCCESS' ? '成功' : '失败'}！</p>
            <ul>
                <li>构建编号：<strong>#${env.BUILD_NUMBER}</strong></li>
                <li>构建状态：<span style="color: ${color};">${icon} ${status}</span></li>
                <li>触发人：${env.TRIGGER_USER ?: '未知'}</li>
                <li>测试报告：<a href="${env.REPORT_LINK}">${env.REPORT_LINK}</a></li>
            </ul>
            <p>请点击上方链接查看 Allure 测试报告详情。</p>
            <hr/>
            <p style="font-size: 12px; color: gray;">此邮件由 Jenkins 自动发送，请勿回复。</p>
        """,
        mimeType: 'text/html'
    )
}
```

⚠️ 注意 || true：pytest 有用例失败时返回非 0 会导致 Pipeline 中断，加上它让报告阶段继续执行，最后再按测试结果标记构建状态。

### 9.3 配置触发方式

在 Jenkins 任务配置里选择：

定时构建

定时构建（Build periodically），它的核心作用是：无论代码有没有更新，只要时间到了，Jenkins 就会自动跑一次。这非常适合用来做“每日/每周回归测试”或者“定时清理/备份任务”。

以下是详细的设置步骤和语法说明：

🛠️ 第一步：进入配置页面

登录 Jenkins，点击你之前建好的任务（比如 api_test）。

在左侧菜单点击 Configure（配置）。

⏱️ 第二步：设置定时触发器

往下滚动，找到 Build Triggers（构建触发器） 区域。

勾选 Build periodically（定时构建）。

在下方出现的 Schedule（调度） 文本框中，输入 Cron 表达式。

📝 第三步：填写 Cron 表达式（核心语法）

Jenkins 的定时表达式和 Linux 的 Cron 语法基本一致，格式为 5 个字段，用空格隔开：

分(MINUTE) 时(HOUR) 日(DOM) 月(MONTH) 周(DOW)

你提到的需求是：每天凌晨2点执行回归测试。

你需要填写的表达式是：

text编辑

H 2 * * *

```
H 2 * * *
```

💡 为什么用 H 而不是 0？

如果你写 0 2 * * *：意味着每天凌晨 2点0分0秒 准时执行。如果 Jenkins 上有几十个任务都这么写，2点整的时候服务器会瞬间满载，导致卡顿。

如果你写 H 2 * * *：H 代表 Hash（哈希）。Jenkins 会根据这个任务的名字算出一个固定的分钟数（比如 2点13分，或者 2点47分）。这样既保证了在凌晨 2 点到 3 点之间执行，又把负载均匀分散了，避免服务器“扎堆”崩溃。

📌 其他常见场景示例：

每 15 分钟跑一次：H/15 * * * *

周一到周五的上午 9 点到下午 5 点，每两小时跑一次：H 9-17/2 * * 1-5

每个月 1 号和 15 号的中午 12 点跑：0 12 1,15 * *

💾 第四步：保存并验证

点击页面底部的 Save（保存）。

回到任务主页，看左侧的 Build History（构建历史） 或时间轴，Jenkins 会显示下一次预计执行的时间（Next Build）。

⚠️ 避坑指南（新手必看）

定时构建 vs 轮询代码（Poll SCM）：

Build periodically（定时构建）：不管代码变没变，到点就拉代码跑测试。适合回归测试。

Poll SCM（轮询SCM）：到点去查一下 Git 有没有新提交，有更新才跑，没更新就不跑。适合冒烟测试。

如果你希望“开发提代码才跑”，你应该勾选的是 Poll SCM，表达式写 H/5 * * * *（每5分钟查一次）。

不要写得太频繁：

千万不要写 * * * * *（每分钟跑一次），除非你的测试只需要 1 秒钟就能跑完，否则 Jenkins 的构建队列会瞬间堵死。

Git Webhook

开发提代码自动跑冒烟，在你 Pipeline 任务的配置页，勾选 “Poll SCM"

TZ=Asia/Shanghai

H/5 * * * *

即使 Jenkins 全局没改时区，这个任务也会严格按照北京时间来执行。每周期去轮询是否有新的提交。如果有，下一个周期build

Would last have run at 2026年8月14日星期五 中国标准时间 14:44:00; would next run at 2026年8月14日星期五 中国标准时间 14:49:00.

这句话的意思是：

上一次本该检查的时间：今天下午 14:44:00

下一次即将检查的时间：今天下午 14:49:00

这说明了什么？

说明 Jenkins 已经算好了时间表，它会在 14:49 准时去你的代码仓库“看一眼”。

如果 14:44 到 14:49 之间，有人 push 了新代码，Jenkins 在 14:49 检查时发现代码变了，就会自动触发构建。

如果这段时间没人动代码，Jenkins 在 14:49 检查完发现没变化，就会什么都不做，安静地等下一个 5 分钟（14:54）。

构建后触发

上游部署任务成功后自动触发

改用 GitHub 插件专用 Webhook（最稳定、无需 token）

安装 GitHub 插件：如果插件中心搜不到，请去 Jenkins 插件官网 手动下载 .hpi 并上传安装（系统管理 → 插件管理 → 高级）。

任务配置：在你 Pipeline 任务的配置页，勾选 “GitHub hook trigger for GITScm polling”。

Content type：选 application/json。

Secret：留空（或填 Jenkins 用户的 API Token，但非必须）。

这样 GitHub 发送的请求会被 Jenkins 内部的 GitHub 插件自动处理，无需 token，也不会被 CSRF 拦截。

### 9.4 发送邮件&钉钉通知

安装插件Email Extension、Build User Vars

安装Cloudflare Tunnel获取公网域名供邮件使用并打开

操作步骤（Windows）

下载 cloudflared

访问 Cloudflare Tunnel 下载页，选择 Windows 64位版本，下载 cloudflared-windows-amd64.exe，将其重命名为 cloudflared.exe，并放到一个你喜欢的目录（如 C:\cloudflared）。

运行隧道

打开命令行（CMD 或 PowerShell），进入该目录，执行：

cmd

稳定版本：

（如果提示需要登录，按提示在浏览器中完成 Cloudflare 账号授权，免费注册即可）

获取公网地址

运行后，终端会输出类似：

text

https://xxxx-xxxx-xxxx.trycloudflare.com

这就是您的 Jenkins 新公网地址。

更新配置

将 Jenkins 系统配置中的 Jenkins URL 改为这个新地址。

将 GitHub Webhook 的 Payload URL 改为这个新地址 + /github-webhook/。

重新触发一次 push，测试是否正常工作。

jenkins配置post发送邮件

```
post {
        always {
            echo "流水线执行结束"
            archiveArtifacts artifacts: 'logs/*.log', allowEmptyArchive: true
        }

        success {
            echo "✅ 恭喜！所有测试用例通过！"
            script { sendEmailNotification('SUCCESS', 'green', '✅') }
        }

        failure {
            echo "❌ 存在失败的测试用例，请查看 Allure 报告。"
            script { sendEmailNotification('FAILURE', 'red', '❌') }
        }
    }
```

```
// ================================================================
//  钉钉机器人通知
// ================================================================
def sendDingTalkNotification(String status, String icon) {
    def keyword = env.DINGTALK_KEYWORD
    def titleText = "${keyword}${icon} Jenkins ${status == 'SUCCESS' ? '构建成功 ✅' : '构建失败 ❌'}"

    def text = """### ${titleText}

- **项目**: ${env.JOB_NAME}
- **构建号**: #${env.BUILD_NUMBER}
- **环境**: ${params.ENV}
- **并发模式**: ${params.PARALLEL}
- **重试次数**: ${params.RERUNS}
- **触发人**: ${env.TRIGGER_USER ?: '未知'}
- **[📊 查看测试报告](${env.REPORT_LINK})**
""".trim()

    def payload = JsonOutput.toJson([
        msgtype : 'markdown',
        markdown: [title: titleText, text: text]
    ])

    httpRequest(
        url              : env.DINGTALK_WEBHOOK,
        httpMode         : 'POST',
        contentType      : 'APPLICATION_JSON',
        requestBody      : payload,
        validResponseCodes: '200',
        quiet            : true
    )
}

```

### 9.5 补充allure报告趋势、环境、执行者等信息

Allure history 目录拷贝

固定目录存储 history（最稳健）

核心思想：不依赖 Jenkins 的 builds 目录，用一个固定路径（如 D:\allure-history\你的任务名）作为 history 的"永久仓库"。每次构建：

生成前：从固定目录拷贝 history → allure-results/history

生成后：从新生成的报告里把 history 拷回固定目录

这样无论中间失败多少次、Jenkins 怎么重启，history 永远在。

改造后的jenkins文件：

```
pipeline {
    agent any

    options {
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }

    parameters {
        choice(name: 'ENV', choices: ['dev', 'prod'], description: '选择运行环境')
        choice(name: 'MARK', choices: ['all', 'smoke', 'regression'], description: '选择用例标记')
    }

    environment {
        // ========== 系统路径 ==========
        PYTHON_PATH = 'C:/Users/27088/AppData/Local/Programs/Python/Python310/python.exe'

        // ========== Allure 命令完整路径（不依赖 PATH）==========
        ALLURE_CMD = 'C:/Users/27088/AppData/Roaming/npm/node_modules/allure-commandline/dist/bin/allure.bat'

        // ========== pip 依赖源 ==========
        PIP_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'

        // ========== Allure 报告相关 ==========
        ALLURE_RESULTS = 'reports/allure-results'
        ALLURE_REPORT_DIR = 'reports/allure-report'
        ALLURE_REPORT_NAME = 'AllureReport'

        // ========== 【关键】History 固定存储目录 ==========
        ALLURE_HISTORY_DIR = "C:/work/yss/allure-history/${env.JOB_NAME}"

        // ========== 邮件配置 ==========
        MAIL_RECIPIENT = 'yiming_2333@sina.com'

        // ========== 编码设置 ==========
        PYTHONIOENCODING = 'utf-8'

        // ========== Git 配置 ==========
        GIT_URL = 'https://github.com/yiming2333/api_test.git'
        GIT_BRANCH = 'master'
        GIT_CREDENTIALS_ID = ''

        // ========== 报告链接 ==========
        REPORT_LINK = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/${env.ALLURE_REPORT_NAME}/"
    }

    stages {
        stage('0. 获取构建用户') {
            steps {
                script {
                    try {
                        wrap([$class: 'BuildUser']) {
                            env.TRIGGER_USER = env.BUILD_USER_ID ?: '未知(插件未生效)'
                        }
                    } catch (e) {
                        echo "⚠️ 无法获取构建用户: ${e.message}"
                        env.TRIGGER_USER = '未知'
                    }
                    echo "本次构建触发人: ${env.TRIGGER_USER}"
                }
            }
        }

        stage('1. 拉取代码') {
            options { retry(60) }
            steps {
                echo "正在从 Git 拉取代码..."
                script {
                    def gitConfig = [branch: env.GIT_BRANCH, url: env.GIT_URL]
                    if (env.GIT_CREDENTIALS_ID?.trim()) {
                        gitConfig.credentialsId = env.GIT_CREDENTIALS_ID
                    }
                    git gitConfig
                }
            }
        }

        stage('2. 安装依赖') {
            steps {
                echo "正在安装 Python 依赖..."
                bat """
                    chcp 65001
                    "${PYTHON_PATH}" -m pip install -r requirements.txt -q -i ${PIP_INDEX_URL}
                """
            }
        }

        stage('3. 执行测试') {
            steps {
                echo "开始执行 Pytest 测试..."
                script {
                    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                        def markArg = params.MARK != 'all' ? "-m ${params.MARK}" : ""
                        bat """
                            chcp 65001
                            "${PYTHON_PATH}" -m pytest ${markArg} ^
                                --env=${params.ENV} ^
                                --alluredir=${ALLURE_RESULTS} ^
                                --clean-alluredir ^
                                -v
                        """
                    }
                }
            }
        }

        // ================================================================
        //  stage 3.5：写入 Allure Environment + Executor 元数据
        // ================================================================
        stage('3.5 写入 Allure 环境 & 执行器信息') {
            steps {
                script {
                    // ---------- 1. environment.properties ----------
                    def envProps = """
                        Environment=${params.ENV}
                        Python.Version=3.10
                        Pytest.Mark=${params.MARK}
                        Trigger.User=${env.TRIGGER_USER ?: 'unknown'}
                        Build.Number=${env.BUILD_NUMBER}
                        Git.Branch=${env.GIT_BRANCH}
                        Base.URL=${getBaseUrl(params.ENV)}
                        OS=Windows
                    """.stripIndent().trim()
                    writeFile file: "${ALLURE_RESULTS}/environment.properties", text: envProps, encoding: 'UTF-8'
                    echo "✅ environment.properties 已写入"

                    // ---------- 2. executor.json（纯 Groovy 手写，无需额外插件）----------
                    def reportUrl = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/${ALLURE_REPORT_NAME}/"
                    def buildUrl  = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/"
                    def jsonStr   = """{
                        "name": "Jenkins",
                        "type": "jenkins",
                        "url": "${env.JENKINS_URL}",
                        "buildOrder": ${env.BUILD_NUMBER},
                        "buildName": "#${env.BUILD_NUMBER}",
                        "buildUrl": "${buildUrl}",
                        "reportUrl": "${reportUrl}",
                        "reportName": "${ALLURE_REPORT_NAME}"
                    }"""
                    writeFile file: "${ALLURE_RESULTS}/executor.json", text: jsonStr, encoding: 'UTF-8'
                    echo "✅ executor.json 已写入"
                }
            }
        }

        // ================================================================
        //  stage 4：生成 Allure 报告 + Trend（完善版）
        // ================================================================
        stage('4. 生成并发布 Allure 报告') {
            steps {
                script {
                    // ---------- Step 1: 确保 history 固定目录存在 ----------
                    bat """
                        if not exist "${ALLURE_HISTORY_DIR}" mkdir "${ALLURE_HISTORY_DIR}"
                    """

                    // ---------- Step 2: 从固定目录拷贝 history 到本次 results ----------
                    if (fileExists("${ALLURE_HISTORY_DIR}/history.json")) {
                        echo "✅ 找到历史 Trend 数据，正在注入..."
                        bat """
                            chcp 65001
                            if not exist "${ALLURE_RESULTS}\\history" mkdir "${ALLURE_RESULTS}\\history"
                            xcopy /E /I /Y "${ALLURE_HISTORY_DIR}\\*" "${ALLURE_RESULTS}\\history\\" >nul
                        """
                    } else {
                        echo "ℹ️ 首次构建或无历史数据，跳过 history 注入"
                    }

                    // ---------- Step 3: 生成报告（写死 allure 路径，不依赖 PATH）----------
                    try {
                        bat """
                            chcp 65001
                            "${ALLURE_CMD}" generate "${ALLURE_RESULTS}" -o "${ALLURE_REPORT_DIR}" --clean
                        """
                        echo "✅ Allure 报告生成成功"
                    } catch (e) {
                        echo "❌ Allure 报告生成失败: ${e.message}"
                    }

                    // ---------- Step 4: 把新生成的 history 拷回固定目录（供下次使用）----------
                    if (fileExists("${ALLURE_REPORT_DIR}/history")) {
                        bat """
                            chcp 65001
                            xcopy /E /I /Y "${ALLURE_REPORT_DIR}\\history\\*" "${ALLURE_HISTORY_DIR}\\" >nul
                        """
                        echo "✅ History 已同步到固定目录: ${ALLURE_HISTORY_DIR}"
                    }
                }

                // ---------- Step 5: 发布 HTML 报告 ----------
                publishHTML([
                    reportDir: env.ALLURE_REPORT_DIR,
                    reportFiles: 'index.html',
                    reportName: env.ALLURE_REPORT_NAME,
                    allowMissing: true,
                    keepAll: true,
                    alwaysLinkToLastBuild: false
                ])
            }
        }
    }

    post {
        always {
            echo "流水线执行结束"
            archiveArtifacts artifacts: 'logs/*.log', allowEmptyArchive: true
            archiveArtifacts artifacts: 'reports/allure-report/history/**', allowEmptyArchive: true
        }

        success {
            echo "✅ 恭喜！所有测试用例通过！"
            script { sendEmailNotification('SUCCESS', 'green', '✅') }
        }

        failure {
            echo "❌ 存在失败的测试用例，请查看 Allure 报告。"
            script { sendEmailNotification('FAILURE', 'red', '❌') }
        }
    }
}

// ========== 根据环境参数返回 base_url ==========
def getBaseUrl(String envName) {
    def urls = [
        'dev' : 'http://127.0.0.1:5000',
        'prod': 'https://api.example.com'
    ]
    return urls[envName] ?: 'unknown'
}

// ========== 邮件发送函数 ==========
def sendEmailNotification(String status, String color, String icon) {
    emailext (
        to: env.MAIL_RECIPIENT,
        subject: "${icon} 测试${status == 'SUCCESS' ? '通过' : '失败'} - ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
        body: """
            <p>各位同事，大家好！</p>
            <p>项目 <strong>${env.JOB_NAME}</strong> 构建${status == 'SUCCESS' ? '成功' : '失败'}！</p>
            <ul>
                <li>构建编号：<strong>#${env.BUILD_NUMBER}</strong></li>
                <li>构建状态：<span style="color: ${color};">${icon} ${status}</span></li>
                <li>触发人：${env.TRIGGER_USER ?: '未知'}</li>
                <li>测试报告：<a href="${env.REPORT_LINK}">${env.REPORT_LINK}</a></li>
            </ul>
            <p>请点击上方链接查看 Allure 测试报告详情。</p>
            <hr/>
            <p style="font-size: 12px; color: gray;">此邮件由 Jenkins 自动发送，请勿回复。</p>
        """,
        mimeType: 'text/html'
    )
}
```

Jenkins Allure 插件自动处理

```
import groovy.json.JsonOutput

pipeline {
    agent any

    options {
        timeout(time: params?.MARK == 'regression' ? 60 : 30, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }

    parameters {
        choice(name: 'ENV', choices: ['dev', 'prod'], description: '选择运行环境')
        choice(name: 'MARK', choices: ['all', 'smoke', 'regression'], description: '选择用例标记')
    }

    environment {
        PYTHON_PATH        = 'C:/Users/27088/AppData/Local/Programs/Python/Python310/python.exe'
        PIP_INDEX_URL      = 'https://pypi.tuna.tsinghua.edu.cn/simple'
        ALLURE_RESULTS     = 'reports/allure-results'
        ALLURE_REPORT_NAME = 'AllureReport'
        MAIL_RECIPIENT     = 'yiming_2333@sina.com'
        PYTHONIOENCODING   = 'utf-8'
        GIT_URL            = 'https://github.com/yiming2333/api_test.git'
        GIT_BRANCH         = 'master'
        GIT_CREDENTIALS_ID = ''
//         REPORT_LINK        = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/${ALLURE_REPORT_NAME}/"
        REPORT_LINK        = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/allure/"
    }

    stages {
        stage('0. 获取构建用户') {
            steps {
                script {
                    try {
                        wrap([$class: 'BuildUser']) {
                            env.TRIGGER_USER = env.BUILD_USER_ID ?: '未知(插件未生效)'
                        }
                    } catch (e) {
                        echo "⚠️ 无法获取构建用户: ${e.message}"
                        env.TRIGGER_USER = '未知'
                    }
                    echo "本次构建触发人: ${env.TRIGGER_USER}"
                }
            }
        }

        stage('1. 拉取代码') {
            options { retry(60) }
            steps {
                echo "正在从 Git 拉取代码..."
                script {
                    def gitConfig = [branch: env.GIT_BRANCH, url: env.GIT_URL]
                    if (env.GIT_CREDENTIALS_ID?.trim()) {
                        gitConfig.credentialsId = env.GIT_CREDENTIALS_ID
                    }
                    git gitConfig
                }
            }
        }

        stage('2. 安装依赖') {
            steps {
                echo "正在安装 Python 依赖..."
                bat """
                    chcp 65001
                    "${PYTHON_PATH}" -m pip install -r requirements.txt -q -i ${PIP_INDEX_URL} --cache-dir .pip-cache
                """
            }
        }

        stage('3. 执行测试') {
            steps {
                echo "开始执行 Pytest 测试..."
                script {
                    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                        def markArg = params.MARK != 'all' ? "-m ${params.MARK}" : ""
                        bat """
                            chcp 65001
                            "${PYTHON_PATH}" -m pytest ${markArg} ^
                                --env=${params.ENV} ^
                                --alluredir=${ALLURE_RESULTS} ^
                                --clean-alluredir ^
                                -v
                        """
                    }
                }
            }
        }

        stage('3.5 写入 Allure 环境 & 执行器信息') {
            steps {
                script {
                    def envProps = """
                        Environment=${params.ENV}
                        Python.Version=3.10
                        Pytest.Mark=${params.MARK}
                        Trigger.User=${env.TRIGGER_USER ?: 'unknown'}
                        Build.Number=${env.BUILD_NUMBER}
                        Git.Branch=${env.GIT_BRANCH}
                        Base.URL=${getBaseUrl(params.ENV)}
                        OS=Windows
                    """.stripIndent().trim()
                    writeFile file: "${ALLURE_RESULTS}/environment.properties", text: envProps, encoding: 'UTF-8'
                    echo "✅ environment.properties 已写入"

                    def executorData = [
                        name       : 'Jenkins',
                        type       : 'jenkins',
                        url        : env.JENKINS_URL,
                        buildOrder : env.BUILD_NUMBER.toInteger(),
                        buildName  : "#${env.BUILD_NUMBER}",
                        buildUrl   : "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/",
                        reportUrl  : "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/${ALLURE_REPORT_NAME}/",
                        reportName : ALLURE_REPORT_NAME
                    ]
                    def jsonStr = JsonOutput.toJson(executorData)
                    writeFile file: "${ALLURE_RESULTS}/executor.json", text: jsonStr, encoding: 'UTF-8'
                    echo "✅ executor.json 已写入: ${jsonStr}"
                }
            }
        }

        stage('4. 生成 Allure 报告') {
    steps {
        allure includeProperties: false,
               jdk: '',
               results: [[path: 'reports/allure-results']],
               reportBuildPolicy: 'ALWAYS'
    }
}
    }

    post {
        always {
            echo "流水线执行结束"
            archiveArtifacts artifacts: 'logs/*.log', allowEmptyArchive: true
        }
        success {
            echo "✅ 恭喜！所有测试用例通过！"
            script { sendEmailNotification('SUCCESS', 'green', '✅') }
        }
        failure {
            echo "❌ 存在失败的测试用例，请查看 Allure 报告。"
            script { sendEmailNotification('FAILURE', 'red', '❌') }
        }
    }
}

def getBaseUrl(String envName) {
    def urls = ['dev': 'http://127.0.0.1:5000', 'prod': 'https://api.example.com']
    return urls[envName] ?: 'unknown'
}

def sendEmailNotification(String status, String color, String icon) {
    emailext(
        to      : env.MAIL_RECIPIENT,
        subject : "${icon} 测试${status == 'SUCCESS' ? '通过' : '失败'} - ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
        body    : """
            <p>各位同事，大家好！</p>
            <p>项目 <strong>${env.JOB_NAME}</strong> 构建${status == 'SUCCESS' ? '成功' : '失败'}！</p>
            <ul>
                <li>构建编号：<strong>#${env.BUILD_NUMBER}</strong></li>
                <li>构建状态：<span style="color: ${color};">${icon} ${status}</span></li>
                <li>触发人：${env.TRIGGER_USER ?: '未知'}</li>
                <li>测试报告：<a href="${env.REPORT_LINK}">${env.REPORT_LINK}</a></li>
            </ul>
            <p>请点击上方链接查看 Allure 测试报告详情。</p>
            <hr/>
            <p style="font-size: 12px; color: gray;">此邮件由 Jenkins 自动发送，请勿回复。</p>
        """,
        mimeType: 'text/html'
    )
}
```

本地先起mock_flask.py

```
from flask import Flask, request, jsonify
import uuid
import time

app = Flask(__name__)

# ============================================================
#  内存数据存储（模拟数据库，重启后清空）
# ============================================================
_users = {
    "testuser": {
        "user_id": 10086,
        "username": "testuser",
        "password": "Test@123",
        "avatar": None
    }
}
_tokens = {}          # token -> user_id
_orders = {}          # order_id -> order_dict
_projects = {}        # project_id -> project_dict
_tasks = {}           # task_id -> task_dict
_upload_tokens = {}   # file_key -> file_info


# ============================================================
#  工具函数
# ============================================================
def _verify_token(req):
    """校验 Bearer Token，返回 user_id 或 None"""
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    return _tokens.get(token)


def _require_auth(req):
    """必须登录，否则返回 401"""
    user_id = _verify_token(req)
    if user_id is None:
        return None, (jsonify({"code": 401, "message": "未登录或token已过期", "data": None}), 401)
    return user_id, None


# ============================================================
#  首页 & 旧表单（保留）
# ============================================================
@app.route('/', methods=['GET', 'POST'])
def home():
    return '<h1>Home</h1>'


@app.route('/signin', methods=['GET'])
def signin_form():
    return '''<form action="/signin" method="post">
              <p><input name="username"></p>
              <p><input name="password" type="password"></p>
              <p><button type="submit">Sign In</button></p>
              </form>'''


# ============================================================
#  认证模块
# ============================================================
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True)

    if not data or 'username' not in data:
        return jsonify({"code": 400, "message": "缺少用户名参数", "data": None}), 400

    username = data.get('username')
    password = data.get('password')

    user = _users.get(username)
    if user and user["password"] == password:
        token = f"mock-jwt-{uuid.uuid4().hex[:16]}"
        _tokens[token] = user["user_id"]
        return jsonify({
            "code": 0,
            "message": "success",
            "data": {
                "token": token,
                "user_id": user["user_id"],      # ← 补上 user_id
                "username": username
            }
        }), 200

    return jsonify({"code": 401, "message": "用户名或密码错误", "data": None}), 401


# ============================================================
#  用户模块
# ============================================================
@app.route('/api/users/<int:user_id>/profile', methods=['GET'])
def get_profile(user_id):
    uid, err = _require_auth(request)
    if err:
        return err

    for u in _users.values():
        if u["user_id"] == user_id:
            return jsonify({
                "code": 0,
                "message": "success",
                "data": {
                    "user_id": u["user_id"],
                    "username": u["username"],
                    "avatar": u.get("avatar")
                }
            }), 200

    return jsonify({"code": 404, "message": "用户不存在", "data": None}), 404


@app.route('/api/users/me/avatar', methods=['PUT'])
def update_avatar():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "file_key" not in data:
        return jsonify({"code": 400, "message": "缺少file_key", "data": None}), 400

    file_key = data["file_key"]
    if file_key not in _upload_tokens:
        return jsonify({"code": 400, "message": "无效的file_key", "data": None}), 400

    # 更新头像
    for u in _users.values():
        if u["user_id"] == uid:
            u["avatar"] = file_key
            break

    return jsonify({"code": 0, "message": "success", "data": {"avatar": file_key}}), 200


# ============================================================
#  文件上传模块
# ============================================================
@app.route('/api/files/upload-token', methods=['POST'])
def get_upload_token():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "file_name" not in data:
        return jsonify({"code": 400, "message": "缺少file_name", "data": None}), 400

    file_key = f"fk-{uuid.uuid4().hex[:12]}"
    _upload_tokens[file_key] = {
        "file_name": data["file_name"],
        "file_type": data.get("file_type", ""),
        "user_id": uid,
        "created_at": time.time()
    }

    return jsonify({
        "code": 0,
        "message": "success",
        "data": {"file_key": file_key}
    }), 200


@app.route('/api/files/commit', methods=['POST'])
def commit_file():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "file_key" not in data:
        return jsonify({"code": 400, "message": "缺少file_key", "data": None}), 400

    file_key = data["file_key"]
    if file_key not in _upload_tokens:
        return jsonify({"code": 400, "message": "无效的file_key", "data": None}), 400

    return jsonify({
        "code": 0,
        "message": "success",
        "data": {"file_key": file_key, "status": "committed"}
    }), 200


# ============================================================
#  订单模块
# ============================================================
@app.route('/api/orders', methods=['POST'])
def create_order():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "product_id" not in data:
        return jsonify({"code": 400, "message": "缺少product_id", "data": None}), 400

    order_id = f"ORD{int(time.time())}{uuid.uuid4().hex[:4].upper()}"
    _orders[order_id] = {
        "order_id": order_id,
        "user_id": uid,
        "product_id": data["product_id"],
        "quantity": data.get("quantity", 1),
        "address": data.get("address", ""),
        "status": "pending"
    }

    return jsonify({
        "code": 0,
        "message": "success",
        "data": {"order_id": order_id}
    }), 201


@app.route('/api/orders/<order_id>', methods=['GET'])
def get_order(order_id):
    uid, err = _require_auth(request)
    if err:
        return err

    order = _orders.get(order_id)
    if not order or order["user_id"] != uid:
        return jsonify({"code": 404, "message": "订单不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": order}), 200


@app.route('/api/orders/<order_id>/cancel', methods=['PUT'])
def cancel_order(order_id):
    uid, err = _require_auth(request)
    if err:
        return err

    order = _orders.get(order_id)
    if not order or order["user_id"] != uid:
        return jsonify({"code": 404, "message": "订单不存在", "data": None}), 404

    order["status"] = "cancelled"
    return jsonify({"code": 0, "message": "success", "data": {"order_id": order_id, "status": "cancelled"}}), 200


# ============================================================
#  项目模块
# ============================================================
@app.route('/api/projects', methods=['POST'])
def create_project():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "name" not in data:
        return jsonify({"code": 400, "message": "缺少name", "data": None}), 400

    project_id = f"PRJ{uuid.uuid4().hex[:8].upper()}"
    _projects[project_id] = {
        "id": project_id,
        "name": data["name"],
        "user_id": uid
    }

    return jsonify({
        "code": 0,
        "message": "success",
        "data": {"id": project_id}
    }), 201


@app.route('/api/projects/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    uid, err = _require_auth(request)
    if err:
        return err

    if project_id in _projects and _projects[project_id]["user_id"] == uid:
        del _projects[project_id]
        # 级联删除该项目下的任务
        to_del = [tid for tid, t in _tasks.items() if t["project_id"] == project_id]
        for tid in to_del:
            del _tasks[tid]

    return jsonify({"code": 0, "message": "success", "data": None}), 200


# ============================================================
#  任务模块
# ============================================================
@app.route('/api/projects/<project_id>/tasks', methods=['POST'])
def create_task(project_id):
    uid, err = _require_auth(request)
    if err:
        return err

    proj = _projects.get(project_id)
    if not proj or proj["user_id"] != uid:
        return jsonify({"code": 404, "message": "项目不存在", "data": None}), 404

    data = request.get_json(silent=True)
    if not data or "title" not in data:
        return jsonify({"code": 400, "message": "缺少title", "data": None}), 400

    task_id = f"TSK{uuid.uuid4().hex[:8].upper()}"
    _tasks[task_id] = {
        "id": task_id,
        "project_id": project_id,
        "title": data["title"],
        "priority": data.get("priority", "medium"),
        "status": "open"
    }

    return jsonify({
        "code": 0,
        "message": "success",
        "data": {"id": task_id}
    }), 201


@app.route('/api/projects/<project_id>/tasks/<task_id>', methods=['GET'])
def get_task(project_id, task_id):
    uid, err = _require_auth(request)
    if err:
        return err

    task = _tasks.get(task_id)
    if not task or task["project_id"] != project_id:
        return jsonify({"code": 404, "message": "任务不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": task}), 200


@app.route('/api/projects/<project_id>/tasks/<task_id>', methods=['PUT'])
def update_task(project_id, task_id):
    uid, err = _require_auth(request)
    if err:
        return err

    task = _tasks.get(task_id)
    if not task or task["project_id"] != project_id:
        return jsonify({"code": 404, "message": "任务不存在", "data": None}), 404

    data = request.get_json(silent=True)
    if data:
        for key in ("title", "priority", "status"):
            if key in data:
                task[key] = data[key]

    return jsonify({"code": 0, "message": "success", "data": task}), 200


if __name__ == '__main__':
    app.run(debug=True, port=5000)
```

## 📋 阶段十：进阶优化方向

方向

方案

接口依赖传参

fixture 里把登录 token 写入全局 context 字典，后续接口动态取值

数据库校验

utils/db.py 封装 pymysql，断言时查库验证数据落库

失败重试

pip install pytest-rerunfailures，配置 --reruns 2

并发执行

pytest-xdist，-n auto 多进程加速

Mock 服务

本地起 Flask/FastAPI 模拟第三方依赖

通知集成

post 阶段调用企业微信机器人 webhook 推送结果

报告趋势

Allure history 目录拷贝，或 Jenkins Allure 插件自动处理

10.1 接口依赖传参

testcases/conftest.py

```
import pytest
import allure
from common.context import ctx


# ============================================================
#  每条用例的分隔线（autouse，放最前面）
# ============================================================
@pytest.fixture(autouse=True)
def case_boundary(request, context):
    print(f"\n{'='*50}")
    print(f"▶ 开始用例: {request.node.name}")
    print(f"  Context keys: {context.keys()}")
    print(f"{'='*50}")
    yield
    print(f"◀ 结束用例: {request.node.name}")


# ============================================================
#  登录 fixture（session 级，整个会话只登录 1 次）
# ============================================================
@pytest.fixture(scope="session")
def login_token(http, context):
    with allure.step("前置操作：用户登录"):
        resp = http.post("/api/auth/login", json={
            "username": "testuser",
            "password": "Test@123"
        })
        assert resp.status_code == 200, f"登录失败: {resp.text}"

        data = resp.json()["data"]
        token = data["token"]
        user_id = data["user_id"]       # ← Flask 现在正确返回了

        context.set("token", token)
        context.set("user_id", user_id)
        http.session.headers["Authorization"] = f"Bearer {token}"

        return token


# ============================================================
#  创建订单 fixture（class 级，依赖 login_token）
# ============================================================
@pytest.fixture(scope="class")
def created_order(http, context, login_token):
    with allure.step("前置操作：创建测试订单"):
        resp = http.post("/api/orders", json={
            "product_id": "SKU_001",
            "quantity": 1,
            "address": "测试地址"
        })
        assert resp.status_code == 201, f"创建订单失败: {resp.text}"

        order_id = resp.json()["data"]["order_id"]
        context.set("order_id", order_id)

        yield order_id

        # teardown
        with allure.step("清理：取消测试订单"):
            http.delete(f"/api/orders/{order_id}")


# ============================================================
#  上传凭证 fixture（class 级）
# ============================================================
@pytest.fixture(scope="class")
def upload_credential(http, context, login_token):
    with allure.step("前置操作：获取上传凭证"):
        resp = http.post("/api/files/upload-token", json={
            "file_name": "test.png",
            "file_type": "image/png"
        })
        assert resp.status_code == 200, f"获取上传凭证失败: {resp.text}"

        file_key = resp.json()["data"]["file_key"]
        context.set("file_key", file_key)
        return file_key


# ============================================================
#  项目 fixture（class 级）
# ============================================================
@pytest.fixture(scope="class")
def project(http, context, login_token):
    with allure.step("前置操作：创建测试项目"):
        resp = http.post("/api/projects", json={"name": "自动化测试项目"})
        assert resp.status_code == 201, f"创建项目失败: {resp.text}"

        project_id = resp.json()["data"]["id"]
        context.set("project_id", project_id)

        yield project_id

        with allure.step("清理：删除测试项目"):
            http.delete(f"/api/projects/{project_id}")


# ============================================================
#  任务 fixture（class 级，依赖 project）
# ============================================================
@pytest.fixture(scope="class")
def task(http, context, project):
    with allure.step("前置操作：创建测试任务"):
        project_id = context.get_or_fail("project_id")
        resp = http.post(f"/api/projects/{project_id}/tasks", json={
            "title": "测试任务",
            "priority": "high"
        })
        assert resp.status_code == 201, f"创建任务失败: {resp.text}"

        task_id = resp.json()["data"]["id"]
        context.set("task_id", task_id)

        yield task_id
```

testcases/test_order.py

```
# testcases/test_order.py

import pytest
import allure
from utils.data_loader import load_test_data
from utils.jsonpath_util import extract_json
from utils.context_resolver import resolve   # ← 新增

ORDER_QUERY_DATA = load_test_data("order.yaml", "test_order_query")


@allure.epic("订单中心")
@allure.feature("订单查询")
class TestOrderQuery:

    @pytest.mark.parametrize(
        "case_id, case_data", ORDER_QUERY_DATA,
        ids=[d[0] for d in ORDER_QUERY_DATA]
    )
    def test_order(self, http, context, request, case_id, case_data):
        allure.dynamic.title(f"[{case_id}] {case_data['title']}")

        # ★ 如果声明了 depends_on，动态获取对应 fixture 的返回值
        #   确保前置 fixture 已执行（pytest 会自动处理依赖顺序）
        if case_data.get("depends_on"):
            request.getfixturevalue(case_data["depends_on"])

        req = case_data["request"]
        expect = case_data["expect"]

        # ★ 替换占位符
        resolved_req = resolve(req)

        with allure.step(f"发送请求: {resolved_req.get('url', '')}"):
            resp = getattr(http, resolved_req["method"])(
                resolved_req["url"],
                **{k: v for k, v in resolved_req.items()
                   if k in ("json", "params", "data", "headers")}
            )

        with allure.step(f"断言状态码 == {expect['status_code']}"):
            assert resp.status_code == expect["status_code"], \
                f"期望 {expect['status_code']}，实际 {resp.status_code}"

        for path, expected_value in expect.get("json_path", []):
            with allure.step(f"断言 {path} == {expected_value}"):
                actual = extract_json(resp.json(), path)
                if expected_value == "not_null":
                    assert actual is not None
                else:
                    assert actual == expected_value, \
                        f"{path} 期望 {expected_value}，实际 {actual}"


@allure.epic("订单中心")
@allure.feature("订单管理")
class TestOrder:

    def test_query_order(self, http, context, created_order):
        """
        查询订单详情。
        created_order fixture 已经创建好订单并写入 context，
        这里直接取 order_id 用。
        """
        # 方式一：从 context 取
        order_id = context.get_or_fail("order_id")

        # 方式二：直接用 fixture 返回值（效果一样）
        # order_id = created_order

        with allure.step(f"查询订单 {order_id}"):
            resp = http.get(f"/api/orders/{order_id}")

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "pending"

    def test_cancel_order(self, http, context, created_order):
        """取消订单"""
        order_id = context.get_or_fail("order_id")

        resp = http.put(f"/api/orders/{order_id}/cancel")
        assert resp.status_code == 200
```

testcases/test_profile.py

```
import allure
import pytest


@allure.epic("用户中心")
@allure.feature("个人信息")
class TestProfile:

    def test_get_profile(self, http, context, login_token):
        """获取个人信息（只需要登录态）"""
        # login_token 确保已登录，http.session 已带 Authorization
        user_id = context.get_or_fail("user_id")

        resp = http.get(f"/api/users/{user_id}/profile")
        assert resp.status_code == 200
        assert resp.json()["data"]["username"] == "testuser"

    def test_update_avatar(self, http, context, login_token, upload_credential):
        """
        更新头像：
        1. upload_credential 先拿到 file_key
        2. 用 file_key 提交更新
        """
        file_key = context.get_or_fail("file_key")

        resp = http.put("/api/users/me/avatar", json={
            "file_key": file_key
        })
        assert resp.status_code == 200
```

testcases/test_task_flow.py

```
class TestTaskFlow:

    def test_query_task(self, http, context, task):
        """查询任务（task fixture 已保证 登录→项目→任务 全部就绪）"""
        project_id = context.get_or_fail("project_id")
        task_id    = context.get_or_fail("task_id")

        resp = http.get(f"/api/projects/{project_id}/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "测试任务"
        assert resp.json()["data"]["priority"] == "high"

    def test_update_task_status(self, http, context, task):
        """更新任务状态"""
        project_id = context.get_or_fail("project_id")
        task_id    = context.get_or_fail("task_id")

        resp = http.put(
            f"/api/projects/{project_id}/tasks/{task_id}",
            json={"status": "done"}
        )
        assert resp.status_code == 200
```

common/context.py

"""全局上下文管理器用于在 fixture 和用例之间传递接口依赖数据"""import threadingclass Context:    """    线程安全的共享字典。    所有 fixture / 用例通过同一个实例读写数据。    """    def __init__(self):        self._data = {}        self._lock = threading.Lock()    # ---------- 写入 ----------    def set(self, key, value):        """存一个值"""        with self._lock:            self._data[key] = value    def set_many(self, mapping: dict):        """批量存"""        with self._lock:            self._data.update(mapping)    # ---------- 读取 ----------    def get(self, key, default=None):        """取一个值，不存在返回 default"""        return self._data.get(key, default)    def get_or_fail(self, key):        """取一个值，不存在直接报错（说明前置没跑）"""        if key not in self._data:            raise KeyError(                f"❌ Context 中找不到 '{key}'，"                f"请检查对应的 fixture 是否已执行。"                f"当前已有 keys: {list(self._data.keys())}"            )        return self._data[key]    # ---------- 工具方法 ----------    def has(self, key):        return key in self._data    def keys(self):        return list(self._data.keys())    def clear(self):        """清空（session 结束时调用）"""        with self._lock:            self._data.clear()    def dump(self):        """调试用：打印当前所有数据"""        return dict(self._data)    def __repr__(self):        return f"<Context keys={self.keys()}>"# 全局单例（整个进程只有一个）ctx = Context()

```
"""
全局上下文管理器
用于在 fixture 和用例之间传递接口依赖数据
"""
import threading


class Context:
    """
    线程安全的共享字典。
    所有 fixture / 用例通过同一个实例读写数据。
    """

    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()

    # ---------- 写入 ----------
    def set(self, key, value):
        """存一个值"""
        with self._lock:
            self._data[key] = value

    def set_many(self, mapping: dict):
        """批量存"""
        with self._lock:
            self._data.update(mapping)

    # ---------- 读取 ----------
    def get(self, key, default=None):
        """取一个值，不存在返回 default"""
        return self._data.get(key, default)

    def get_or_fail(self, key):
        """取一个值，不存在直接报错（说明前置没跑）"""
        if key not in self._data:
            raise KeyError(
                f"❌ Context 中找不到 '{key}'，"
                f"请检查对应的 fixture 是否已执行。"
                f"当前已有 keys: {list(self._data.keys())}"
            )
        return self._data[key]

    # ---------- 工具方法 ----------
    def has(self, key):
        return key in self._data

    def keys(self):
        return list(self._data.keys())

    def clear(self):
        """清空（session 结束时调用）"""
        with self._lock:
            self._data.clear()

    def dump(self):
        """调试用：打印当前所有数据"""
        return dict(self._data)

    def __repr__(self):
        return f"<Context keys={self.keys()}>"


# 全局单例（整个进程只有一个）
ctx = Context()
```

config/testdata/order.yaml

```
# config/testdata/order.yaml

test_order_query:
  - case_id: ORDER_001
    title: "查询已创建的订单"
    depends_on: created_order        # ← 声明依赖哪个 fixture
    request:
      method: get
      url: "/api/orders/${order_id}"  # ← 占位符
    expect:
      status_code: 200
      json_path:
        - ["$.data.status", "pending"]

  - case_id: ORDER_002
    title: "取消订单"
    depends_on: created_order
    request:
      method: put
      url: "/api/orders/${order_id}/cancel"
    expect:
      status_code: 200

test_file_upload:
  - case_id: FILE_001
    title: "用凭证提交文件"
    depends_on: upload_credential
    request:
      method: post
      url: "/api/files/commit"
      json:
        file_key: "${file_key}"       # ← 占位符
        file_name: "test.png"
    expect:
      status_code: 200
```

conftest.py

```
# 确认你的根目录 conftest.py 包含以下内容（已有则不动）
import pytest
from common.http_client import HttpClient
from common.yaml_handler import get_config
from common.context import ctx


def pytest_addoption(parser):
    parser.addoption("--env", default="dev", help="运行环境: dev/prod")


@pytest.fixture(scope="session")
def env_name(request):
    return request.config.getoption("--env")


@pytest.fixture(scope="session")
def http(env_name):
    cfg = get_config(env_name)
    client = HttpClient(base_url=cfg["base_url"], timeout=cfg.get("timeout", 10))
    return client


@pytest.fixture(scope="session")
def context():
    yield ctx
    ctx.clear()

```

utils/context_resolver.py

```
"""
从 Context 中解析 ${xxx} 占位符
"""
import re
from common.context import ctx

PATTERN = re.compile(r'\$\{(\w+)\}')


def resolve(value):
    """
    递归替换字符串 / 字典 / 列表中的 ${key} 占位符。

    示例:
        ctx.set("order_id", "ORD001")
        resolve("/api/orders/${order_id}")
        → "/api/orders/ORD001"
    """
    if isinstance(value, str):
        def _replace(match):
            key = match.group(1)
            resolved = ctx.get(key)
            if resolved is None:
                raise ValueError(
                    f"占位符 ${{{key}}} 无法解析，"
                    f"Context 中没有这个值。"
                    f"当前 keys: {ctx.keys()}"
                )
            return str(resolved)
        return PATTERN.sub(_replace, value)

    elif isinstance(value, dict):
        return {k: resolve(v) for k, v in value.items()}

    elif isinstance(value, list):
        return [resolve(item) for item in value]

    return value  # int / float / bool 原样返回
```

10.2 数据库校验

安装依赖

requirements.txt追加依赖

PyMySQL==1.2.0

cryptography==50.0.0

util/db.py

```
"""
数据库操作工具类
用于接口测试后的数据校验
"""
import pymysql
from contextlib import contextmanager
from common.logger import log


# ============================================================
#  数据库配置（后续可改为从 config.yaml 读取）
# ============================================================
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'Root@123456',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,  # ← 关键：返回字典而非元组
}


class DBClient:
    """轻量级数据库客户端，支持上下文管理器自动关闭连接"""

    def __init__(self, database=None, **overrides):
        self.config = {**DB_CONFIG, **overrides}
        if database:
            self.config['database'] = database

    @contextmanager
    def connect(self):
        """上下文管理器：自动提交/回滚/关闭"""
        conn = None
        try:
            conn = pymysql.connect(**self.config)
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            log.error(f"❌ 数据库异常: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def query(self, sql, params=None, database=None):
        """
        查询多条记录，返回 list[dict]

        示例:
            db.query("SELECT * FROM orders WHERE user_id = %s", (10086,))
        """
        cfg = {**self.config}
        if database:
            cfg['database'] = database

        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as cursor:
                log.info(f"🔍 SQL: {sql} | 参数: {params}")
                cursor.execute(sql, params)
                results = cursor.fetchall()
                log.info(f"   返回 {len(results)} 条记录")
                return results

    def query_one(self, sql, params=None, database=None):
        """查询单条记录，返回 dict 或 None"""
        results = self.query(sql, params, database)
        return results[0] if results else None

    def execute(self, sql, params=None, database=None):
        """执行写操作（INSERT/UPDATE/DELETE），返回影响行数"""
        cfg = {**self.config}
        if database:
            cfg['database'] = database

        with self.connect() as conn:
            with conn.cursor() as cursor:
                log.info(f"✏️  SQL: {sql} | 参数: {params}")
                affected = cursor.execute(sql, params)
                log.info(f"   影响 {affected} 行")
                return affected

    def count(self, table, where=None, params=None, database=None):
        """
        快捷计数

        示例:
            db.count("orders", "user_id = %s AND status = %s", (10086, "pending"))
        """
        sql = f"SELECT COUNT(*) AS cnt FROM {table}"
        if where:
            sql += f" WHERE {where}"
        row = self.query_one(sql, params, database)
        return row["cnt"] if row else 0

    def exists(self, table, where, params=None, database=None):
        """判断记录是否存在"""
        return self.count(table, where, params, database) > 0

    def assert_record_exists(self, table, where, params=None, database=None, msg=""):
        """断言记录存在，不存在直接抛 AssertionError"""
        if not self.exists(table, where, params, database):
            raise AssertionError(
                f"{msg}数据库中未找到记录: {table} WHERE {where} | 参数: {params}"
            )

    def assert_field_value(self, table, where, params, field, expected, database=None):
        """
        断言某条记录的某个字段值等于预期值

        示例:
            db.assert_field_value(
                "orders", "order_id = %s", ("ORD001",),
                field="status", expected="pending"
            )
        """
        row = self.query_one(
            f"SELECT {field} FROM {table} WHERE {where}", params, database
        )
        assert row is not None, \
            f"数据库中未找到记录: {table} WHERE {where} | 参数: {params}"

        actual = row[field]
        assert actual == expected, \
            f"字段 {field} 期望 '{expected}'，实际 '{actual}'"


# ============================================================
#  全局单例（按需指定 database）
# ============================================================
db = DBClient(database="api_test")
```

mock_flask.py改造适配数据库读写

```
from flask import Flask, request, jsonify
import uuid
import time
import pymysql

app = Flask(__name__)

# ============================================================
#  内存数据存储（模拟数据库，重启后清空）
# ============================================================
_users = {
    "testuser": {
        "user_id": 10086,
        "username": "testuser",
        "password": "Test@123",
        "avatar": None
    }
}

_orders = {}          # order_id -> order_dict
_projects = {}        # project_id -> project_dict
_tasks = {}           # task_id -> task_dict
_upload_tokens = {}   # file_key -> file_info

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'Root@123456',
    'database': 'api_test',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
}
def get_db():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


# ============================================================
#  Token 仍然用内存存储（模拟 JWT 无状态特性）
# ============================================================
_tokens = {}  # token -> user_id


# ============================================================
#  工具函数
# ============================================================
def _verify_token(req):
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    return _tokens.get(token)


def _require_auth(req):
    user_id = _verify_token(req)
    if user_id is None:
        return None, (jsonify({"code": 401, "message": "未登录或token已过期", "data": None}), 401)
    return user_id, None


# ============================================================
#  首页 & 旧表单（保留）
# ============================================================
@app.route('/', methods=['GET', 'POST'])
def home():
    return '<h1>Home</h1>'


@app.route('/signin', methods=['GET'])
def signin_form():
    return '''<form action="/signin" method="post">
              <p><input name="username"></p>
              <p><input name="password" type="password"></p>
              <p><button type="submit">Sign In</button></p>
              </form>'''


# ============================================================
#  认证模块（查库验证用户名密码）
# ============================================================
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True)
    if not data or 'username' not in data:
        return jsonify({"code": 400, "message": "缺少用户名参数", "data": None}), 400

    username = data.get('username')
    password = data.get('password')

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, username, password FROM users WHERE username = %s",
                (username,)
            )
            user = cur.fetchone()
    finally:
        conn.close()

    if user and user["password"] == password:
        token = f"mock-jwt-{uuid.uuid4().hex[:16]}"
        _tokens[token] = user["user_id"]
        return jsonify({
            "code": 0, "message": "success",
            "data": {"token": token, "user_id": user["user_id"], "username": username}
        }), 200

    return jsonify({"code": 401, "message": "用户名或密码错误", "data": None}), 401


# ============================================================
#  用户模块
# ============================================================
@app.route('/api/users/<int:user_id>/profile', methods=['GET'])
def get_profile(user_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, username, avatar FROM users WHERE user_id = %s", (user_id,))
            user = cur.fetchone()
    finally:
        conn.close()

    if not user:
        return jsonify({"code": 404, "message": "用户不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": user}), 200


@app.route('/api/users/me/avatar', methods=['PUT'])
def update_avatar():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "file_key" not in data:
        return jsonify({"code": 400, "message": "缺少file_key", "data": None}), 400

    file_key = data["file_key"]

    conn = get_db()
    try:
        with conn.cursor() as cur:
            # 验证 file_key 有效
            cur.execute("SELECT file_key FROM file_uploads WHERE file_key = %s AND user_id = %s",
                        (file_key, uid))
            if not cur.fetchone():
                return jsonify({"code": 400, "message": "无效的file_key", "data": None}), 400

            cur.execute("UPDATE users SET avatar = %s WHERE user_id = %s", (file_key, uid))
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"avatar": file_key}}), 200


# ============================================================
#  文件上传模块
# ============================================================
@app.route('/api/files/upload-token', methods=['POST'])
def get_upload_token():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "file_name" not in data:
        return jsonify({"code": 400, "message": "缺少file_name", "data": None}), 400

    file_key = f"fk-{uuid.uuid4().hex[:12]}"

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO file_uploads (file_key, file_name, file_type, user_id, committed)
                   VALUES (%s, %s, %s, %s, 0)""",
                (file_key, data["file_name"], data.get("file_type", ""), uid)
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"file_key": file_key}}), 200


@app.route('/api/files/commit', methods=['POST'])
def commit_file():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "file_key" not in data:
        return jsonify({"code": 400, "message": "缺少file_key", "data": None}), 400

    file_key = data["file_key"]

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE file_uploads SET committed = 1 WHERE file_key = %s AND user_id = %s",
                (file_key, uid)
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    if affected == 0:
        return jsonify({"code": 400, "message": "无效的file_key", "data": None}), 400

    return jsonify({"code": 0, "message": "success",
                     "data": {"file_key": file_key, "status": "committed"}}), 200


# ============================================================
#  订单模块（写入真实数据库）
# ============================================================
@app.route('/api/orders', methods=['POST'])
def create_order():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "product_id" not in data:
        return jsonify({"code": 400, "message": "缺少product_id", "data": None}), 400

    order_id = f"ORD{int(time.time())}{uuid.uuid4().hex[:4].upper()}"

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO orders (order_id, user_id, product_id, quantity, address, status)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (order_id, uid, data["product_id"],
                 data.get("quantity", 1), data.get("address", ""), "pending")
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"order_id": order_id}}), 201


@app.route('/api/orders/<order_id>', methods=['GET'])
def get_order(order_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM orders WHERE order_id = %s AND user_id = %s",
                (order_id, uid)
            )
            order = cur.fetchone()
    finally:
        conn.close()

    if not order:
        return jsonify({"code": 404, "message": "订单不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": order}), 200


@app.route('/api/orders/<order_id>/cancel', methods=['PUT'])
def cancel_order(order_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET status = 'cancelled' WHERE order_id = %s AND user_id = %s",
                (order_id, uid)
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    if affected == 0:
        return jsonify({"code": 404, "message": "订单不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success",
                     "data": {"order_id": order_id, "status": "cancelled"}}), 200

@app.route('/api/orders/<order_id>', methods=['DELETE'])
def delete_order(order_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM orders WHERE order_id = %s AND user_id = %s",
                (order_id, uid)
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    if affected == 0:
        return jsonify({"code": 404, "message": "订单不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": None}), 200


# ============================================================
#  项目模块
# ============================================================
@app.route('/api/projects', methods=['POST'])
def create_project():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "name" not in data:
        return jsonify({"code": 400, "message": "缺少name", "data": None}), 400

    project_id = f"PRJ{uuid.uuid4().hex[:8].upper()}"

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO projects (id, name, user_id) VALUES (%s, %s, %s)",
                (project_id, data["name"], uid)
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"id": project_id}}), 201


@app.route('/api/projects/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tasks WHERE project_id = %s", (project_id,))
            cur.execute("DELETE FROM projects WHERE id = %s AND user_id = %s", (project_id, uid))
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": None}), 200


# ============================================================
#  任务模块
# ============================================================
@app.route('/api/projects/<project_id>/tasks', methods=['POST'])
def create_task(project_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM projects WHERE id = %s AND user_id = %s", (project_id, uid))
            if not cur.fetchone():
                return jsonify({"code": 404, "message": "项目不存在", "data": None}), 404

        data = request.get_json(silent=True)
        if not data or "title" not in data:
            return jsonify({"code": 400, "message": "缺少title", "data": None}), 400

        task_id = f"TSK{uuid.uuid4().hex[:8].upper()}"
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO tasks (id, project_id, title, priority, status)
                   VALUES (%s, %s, %s, %s, %s)""",
                (task_id, project_id, data["title"], data.get("priority", "medium"), "open")
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"id": task_id}}), 201


@app.route('/api/projects/<project_id>/tasks/<task_id>', methods=['GET'])
def get_task(project_id, task_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tasks WHERE id = %s AND project_id = %s",
                (task_id, project_id)
            )
            task = cur.fetchone()
    finally:
        conn.close()

    if not task:
        return jsonify({"code": 404, "message": "任务不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": task}), 200


@app.route('/api/projects/<project_id>/tasks/<task_id>', methods=['PUT'])
def update_task(project_id, task_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tasks WHERE id = %s AND project_id = %s",
                (task_id, project_id)
            )
            task = cur.fetchone()
            if not task:
                return jsonify({"code": 404, "message": "任务不存在", "data": None}), 404

            data = request.get_json(silent=True)
            if data:
                updates = []
                values = []
                for key in ("title", "priority", "status"):
                    if key in data:
                        updates.append(f"{key} = %s")
                        values.append(data[key])
                if updates:
                    values.extend([task_id, project_id])
                    cur.execute(
                        f"UPDATE tasks SET {', '.join(updates)} WHERE id = %s AND project_id = %s",
                        values
                    )
            conn.commit()

            # 重新查询返回最新数据
            cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
            updated = cur.fetchone()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": updated}), 200


if __name__ == '__main__':
    app.run(debug=True, port=5000)
```

init.sql

```
CREATE DATABASE IF NOT EXISTS api_test DEFAULT CHARSET utf8mb4;
USE api_test;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    user_id     INT NOT NULL UNIQUE,
    username    VARCHAR(50) NOT NULL,
    password    VARCHAR(100) NOT NULL,
    avatar      VARCHAR(255) DEFAULT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 订单表
CREATE TABLE IF NOT EXISTS orders (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    order_id    VARCHAR(50) NOT NULL UNIQUE,
    user_id     INT NOT NULL,
    product_id  VARCHAR(50) NOT NULL,
    quantity    INT DEFAULT 1,
    address     VARCHAR(255) DEFAULT '',
    status      VARCHAR(20) DEFAULT 'pending',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 项目表
CREATE TABLE IF NOT EXISTS projects (
    id          VARCHAR(20) PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    user_id     INT NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 任务表
CREATE TABLE IF NOT EXISTS tasks (
    id          VARCHAR(20) PRIMARY KEY,
    project_id  VARCHAR(20) NOT NULL,
    title       VARCHAR(200) NOT NULL,
    priority    VARCHAR(20) DEFAULT 'medium',
    status      VARCHAR(20) DEFAULT 'open',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 文件上传记录表
CREATE TABLE IF NOT EXISTS file_uploads (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    file_key    VARCHAR(50) NOT NULL UNIQUE,
    file_name   VARCHAR(255) NOT NULL,
    file_type   VARCHAR(50) DEFAULT '',
    user_id     INT NOT NULL,
    committed   TINYINT DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 插入测试用户
INSERT IGNORE INTO users (user_id, username, password)
VALUES (10086, 'testuser', 'Test@123');
```

在 根目录conftest.py 中注入 db fixture，追加 session 级清理

```
from utils.db import db as db_client
from common.logger import get_logger
logger = get_logger(__name__)

@pytest.fixture(scope="session")
def db():
    """全局数据库客户端，session 级别复用"""
    yield db_client
    
@pytest.fixture(scope="session", autouse=True)
def clean_test_data(db):
    """整个测试会话结束后清理测试数据"""
    yield
    # 按外键依赖顺序删除
    tables = ["tasks", "projects", "orders", "file_uploads"]
    for table in tables:
        try:
            db.execute(f"DELETE FROM {table}")
            logger.info(f"🧹 已清理表: {table}")
        except Exception as e:
            logger.warning(f"清理表 {table} 失败: {e}")
```

在 config/testdata/order.yaml 中增加 db_check 字段

```
test_order_query:
  - case_id: ORDER_001
    title: "查询已创建的订单"
    depends_on: created_order
    request:
      method: get
      url: "/api/orders/${order_id}"
    expect:
      status_code: 200
      json_path:
        - ["$.data.status", "pending"]
      # ★ 新增：数据库校验声明
      db_check:
        - table: orders
          where: "order_id = %s"
          params: ["${order_id}"]
          field: status
          expected: "pending"

  - case_id: ORDER_002
    title: "取消订单并验证DB"
    depends_on: created_order
    request:
      method: put
      url: "/api/orders/${order_id}/cancel"
    expect:
      status_code: 200
      db_check:
        - table: orders
          where: "order_id = %s"
          params: ["${order_id}"]
          field: status
          expected: "cancelled"
```

用例中加入数据库断言

testcases/test_order.py

```
# testcases/test_order.py

import pytest
import allure
from utils.data_loader import load_test_data
from utils.jsonpath_util import extract_json
from utils.context_resolver import resolve

ORDER_QUERY_DATA = load_test_data("order.yaml", "test_order_query")


@allure.epic("订单中心")
@allure.feature("订单查询")
class TestOrderQuery:

    @pytest.mark.parametrize(
        "case_id, case_data", ORDER_QUERY_DATA,
        ids=[d[0] for d in ORDER_QUERY_DATA]
    )
    def test_order(self, http, context, request, db, case_id, case_data):
        allure.dynamic.title(f"[{case_id}] {case_data['title']}")

        if case_data.get("depends_on"):
            request.getfixturevalue(case_data["depends_on"])

        req = case_data["request"]
        expect = case_data["expect"]
        resolved_req = resolve(req)

        with allure.step(f"发送请求: {resolved_req.get('url', '')}"):
            resp = getattr(http, resolved_req["method"])(
                resolved_req["url"],
                **{k: v for k, v in resolved_req.items()
                   if k in ("json", "params", "data", "headers")}
            )

        with allure.step(f"断言状态码 == {expect['status_code']}"):
            assert resp.status_code == expect["status_code"]

        for path, expected_value in expect.get("json_path", []):
            with allure.step(f"断言 {path} == {expected_value}"):
                actual = extract_json(resp.json(), path)
                if expected_value == "not_null":
                    assert actual is not None
                else:
                    assert actual == expected_value

        # DB 校验
        for check in expect.get("db_check", []):
            resolved_check = resolve(check)
            with allure.step(f"DB校验: {resolved_check['table']}.{resolved_check['field']} == {resolved_check['expected']}"):
                db.assert_field_value(
                    table=resolved_check["table"],
                    where=resolved_check["where"],
                    params=tuple(resolved_check["params"]),
                    field=resolved_check["field"],
                    expected=resolved_check["expected"]
                )


@allure.epic("订单中心")
@allure.feature("订单管理")
class TestOrder:

    def test_create_and_verify_in_db(self, http, context, login_token, db):
        """创建订单后，验证数据库记录正确落库"""
        with allure.step("创建订单"):
            resp = http.post("/api/orders", json={
                "product_id": "SKU_DB_TEST",
                "quantity": 3,
                "address": "数据库校验测试地址"
            })
            assert resp.status_code == 201
            order_id = resp.json()["data"]["order_id"]

        with allure.step("DB校验：订单记录存在"):
            db.assert_record_exists(
                "orders", "order_id = %s", (order_id,),
                msg=f"订单 {order_id} "
            )

        with allure.step("DB校验：product_id 正确"):
            db.assert_field_value(
                "orders", "order_id = %s", (order_id,),
                field="product_id", expected="SKU_DB_TEST"
            )

        with allure.step("DB校验：quantity 正确"):
            db.assert_field_value(
                "orders", "order_id = %s", (order_id,),
                field="quantity", expected=3
            )

        with allure.step("DB校验：初始状态为 pending"):
            db.assert_field_value(
                "orders", "order_id = %s", (order_id,),
                field="status", expected="pending"
            )

        # 清理：用 PUT cancel 代替 DELETE（Flask 没有 DELETE 订单路由）
        http.put(f"/api/orders/{order_id}/cancel")

    def test_cancel_order_updates_db(self, http, context, login_token, db):
        """取消订单后，验证数据库状态变更（独立创建订单，不与其他用例共享）"""
        with allure.step("创建待取消的订单"):
            resp = http.post("/api/orders", json={
                "product_id": "SKU_CANCEL_TEST",
                "quantity": 1,
                "address": "取消测试"
            })
            assert resp.status_code == 201
            order_id = resp.json()["data"]["order_id"]

        with allure.step("取消订单"):
            resp = http.put(f"/api/orders/{order_id}/cancel")
            assert resp.status_code == 200

        with allure.step("DB校验：状态变为 cancelled"):
            db.assert_field_value(
                "orders", "order_id = %s", (order_id,),
                field="status", expected="cancelled"
            )

    def test_query_order_pending(self, http, context, login_token, db):
        """查询刚创建的订单，状态应为 pending（独立订单，不受其他用例影响）"""
        with allure.step("创建待查询的订单"):
            resp = http.post("/api/orders", json={
                "product_id": "SKU_QUERY_TEST",
                "quantity": 1,
                "address": "查询测试"
            })
            assert resp.status_code == 201
            order_id = resp.json()["data"]["order_id"]

        with allure.step(f"查询订单 {order_id}"):
            resp = http.get(f"/api/orders/{order_id}")

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "pending"

        # 清理
        http.put(f"/api/orders/{order_id}/cancel")

    def test_cancel_order_api(self, http, context, login_token):
        """取消订单接口返回 200（独立订单）"""
        with allure.step("创建待取消的订单"):
            resp = http.post("/api/orders", json={
                "product_id": "SKU_API_TEST",
                "quantity": 1,
                "address": "API测试"
            })
            assert resp.status_code == 201
            order_id = resp.json()["data"]["order_id"]

        resp = http.put(f"/api/orders/{order_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cancelled"
```

testcases/test_task_flow.py

```
# testcases/test_task_flow.py

import allure


@allure.epic("项目管理")
@allure.feature("任务流程")
class TestTaskFlow:

    def test_create_task_verify_db(self, http, context, task, db):
        """创建任务后验证数据库"""
        task_id = context.get_or_fail("task_id")
        project_id = context.get_or_fail("project_id")

        with allure.step("DB校验：任务记录存在"):
            db.assert_record_exists(
                "tasks", "id = %s AND project_id = %s",
                (task_id, project_id),
                msg=f"任务 {task_id} "
            )

        with allure.step("DB校验：优先级为 high"):
            db.assert_field_value(
                "tasks", "id = %s", (task_id,),
                field="priority", expected="high"
            )

        with allure.step("DB校验：初始状态为 open"):
            db.assert_field_value(
                "tasks", "id = %s", (task_id,),
                field="status", expected="open"
            )

    def test_update_task_status_verify_db(self, http, context, task, db):
        """更新任务状态后验证数据库"""
        project_id = context.get_or_fail("project_id")
        task_id = context.get_or_fail("task_id")

        with allure.step("更新任务状态为 done"):
            resp = http.put(
                f"/api/projects/{project_id}/tasks/{task_id}",
                json={"status": "done"}
            )
            assert resp.status_code == 200

        with allure.step("DB校验：状态已更新为 done"):
            db.assert_field_value(
                "tasks", "id = %s", (task_id,),
                field="status", expected="done"
            )

    def test_query_task(self, http, context, task):
        project_id = context.get_or_fail("project_id")
        task_id = context.get_or_fail("task_id")
        resp = http.get(f"/api/projects/{project_id}/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "测试任务"
        assert resp.json()["data"]["priority"] == "high"
```

10.3 失败重试

1. 安装插件

在你的项目虚拟环境中执行：

pip install pytest-rerunfailures==14.0

```
pip install pytest-rerunfailures==14.0
```

⚠️ 记得同步更新 requirements.txt，加入 pytest-rerunfailures==14.0，保证 Jenkins 环境一致。

2. 三种配置方式（由粗到细）

方式一：命令行参数（最灵活，推荐 Jenkins 使用）

# 所有失败用例最多重试 2 次，每次间隔 3 秒pytest --reruns 2 --reruns-delay 3 -v

```
# 所有失败用例最多重试 2 次，每次间隔 3 秒

pytest --reruns 2 --reruns-delay 3 -v
```

参数

说明

--reruns N

失败后最多重试 N 次

--reruns-delay S

每次重试前等待 S 秒（避免瞬间重压）

--only-rerun ERR

只对特定异常重试，如 --only-rerun ConnectionError

方式二：pytest.ini 全局配置（本地开发省心）

修改你现有的 pytest.ini：

```
addopts = -v -s --alluredir=./reports/allure-results --reruns 2 --reruns-delay 3

```

💡 addopts 里加了 --reruns 2 后，本地直接 pytest 就会自动重试，不用每次手敲。

方式三：装饰器精细控制（个别用例特殊处理）

某些用例本身就不稳定（比如依赖外部短信验证码），可以单独加重试：

```
import pytest

@pytest.mark.flaky(reruns=5, reruns_delay=2)

def test_send_sms_code(http):

    """短信接口偶尔超时，给它更多机会"""

    resp = http.post("/api/sms/send", json={"phone": "13800138000"})

    assert resp.status_code == 200
```

🎯 优先级：装饰器 > 命令行 > ini 配置。装饰器设了 reruns=5，即使全局配了 --reruns 2，这个用例也会重试 5 次。

进阶建议：可以把重试次数做成 Pipeline 参数，方便临时调整：

也可以随时修改build配置parameter

```
parameters {
       string(name: 'RERUNS', defaultValue: '2', description: '失败重试次数')
}

```

然后命令里用 --reruns ${params.RERUNS}。

10.4 并发执行

依赖安装和使用

pytest-xdist==3.8.0，pip安装及追加requirements

DBUtils==3.1.2

# 默认：按负载均衡分发（推荐）、 自动检测 CPU 核心数，开对应数量的 workerpytest -n auto# 按 test 文件分组（同一文件的用例在同一个 worker）pytest -n auto --dist loadfile# 按 class 分组（同一 class 的用例在同一个 worker）pytest -n auto --dist loadscope# 按模块分组pytest -n auto --dist loadmodule指定 4 个并发 workerpytest -n 4

```
# 默认：按负载均衡分发（推荐）、 自动检测 CPU 核心数，开对应数量的 worker
pytest -n auto

# 按 test 文件分组（同一文件的用例在同一个 worker）
pytest -n auto --dist loadfile

# 按 class 分组（同一 class 的用例在同一个 worker）
pytest -n auto --dist loadscope

# 按模块分组
pytest -n auto --dist loadmodule

指定 4 个并发 worker
pytest -n 4

```

Jenkins Pipeline 适配

```
stage('3. 执行测试') {
    steps {
        script {
            catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                def markArg = params.MARK != 'all' ? "-m ${params.MARK}" : ""
                // 并发数：auto 或指定数字
                def xdistArg = "-n auto"
                bat """
                    chcp 65001
                    "${PYTHON_PATH}" -m pytest ${markArg} ${xdistArg} ^
                        --env=${params.ENV} ^
                        --alluredir=${ALLURE_RESULTS} ^
                        --clean-alluredir ^
                        -v
                """
            }
        }
    }
}
```

改造后的 mock_flask.py（并发安全版）

💡 如果并发量更大（比如 50+ worker），建议用 waitress 替代 Flask 内置服务器：

bash

pip install waitress

```
"""
mock_flask.py - 并发安全版
支持 pytest-xdist 多 worker 同时请求
"""
from flask import Flask, request, jsonify
import uuid
import time
import threading
import pymysql
from dbutils.pooled_db import PooledDB

app = Flask(__name__)

# ============================================================
#  数据库连接池（关键改造）
# ============================================================
DB_POOL = PooledDB(
    creator=pymysql,
    maxconnections=20,      # 最大连接数（根据 worker 数调整）
    mincached=2,            # 初始空闲连接
    maxcached=5,            # 最大空闲连接
    blocking=True,          # 连接用完时等待而非报错
    host='localhost',
    port=3306,
    user='root',
    password='Root@123456',
    database='api_test',
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=False
)


def get_db():
    """从连接池获取连接"""
    return DB_POOL.connection()


# ============================================================
#  Token 存储（内存 + 线程锁）
# ============================================================
_tokens = {}
_token_lock = threading.Lock()


def _store_token(token, user_id):
    with _token_lock:
        _tokens[token] = user_id


def _get_token_user(token):
    with _token_lock:
        return _tokens.get(token)


# ============================================================
#  认证校验
# ============================================================
def _verify_token(req):
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    return _get_token_user(token)


def _require_auth(req):
    user_id = _verify_token(req)
    if user_id is None:
        return None, (jsonify({"code": 401, "message": "未登录或token已过期", "data": None}), 401)
    return user_id, None


FAULT_COUNT= 2
_login_fault_remaining = FAULT_COUNT       # 每次触发消耗的总次数
_login_fault_counter = FAULT_COUNT         # 当前剩余次数（运行时递减）
# ============================================================
#  认证模块
# ============================================================
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    global _login_fault_counter
    data = request.get_json(silent=True)
    if not data or 'username' not in data:
        return jsonify({"code": 400, "message": "缺少用户名参数", "data": None}), 400

    username = data.get('username')
    password = data.get('password')

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, username, password FROM users WHERE username = %s",
                (username,)
            )
            user = cur.fetchone()
    finally:
        conn.close()

    if user and user["password"] == password:
        token = f"mock-jwt-{uuid.uuid4().hex[:16]}"
        _store_token(token, user["user_id"])
        return jsonify({
            "code": 0, "message": "success",
            "data": {"token": token, "user_id": user["user_id"], "username": username}
        }), 200
    else:
        if _login_fault_counter > 0:
            _login_fault_counter -= 1
            print(f"⚡ [FAULT] 剩余{_login_fault_counter}次")
            return jsonify({"code": 500, "message": "临时故障", "data": None}), 500

        else:
            # ★ 归零后立刻重置，然后本次请求走正常错误返回
            _login_fault_counter = _login_fault_remaining
            # 不 return，继续往下走正常的 400/401 逻辑

        if not data or 'username' not in data:
            return jsonify({"code": 400, "message": "缺少用户名参数", "data": None}), 400
        return jsonify({"code": 401, "message": "用户名或密码错误", "data": None}), 401


# ============================================================
#  用户模块
# ============================================================
@app.route('/api/users/<int:user_id>/profile', methods=['GET'])
def get_profile(user_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, username, avatar FROM users WHERE user_id = %s", (user_id,))
            user = cur.fetchone()
    finally:
        conn.close()

    if not user:
        return jsonify({"code": 404, "message": "用户不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": user}), 200


@app.route('/api/users/me/avatar', methods=['PUT'])
def update_avatar():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "file_key" not in data:
        return jsonify({"code": 400, "message": "缺少file_key", "data": None}), 400

    file_key = data["file_key"]
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT file_key FROM file_uploads WHERE file_key = %s AND user_id = %s",
                        (file_key, uid))
            if not cur.fetchone():
                return jsonify({"code": 400, "message": "无效的file_key", "data": None}), 400
            cur.execute("UPDATE users SET avatar = %s WHERE user_id = %s", (file_key, uid))
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"avatar": file_key}}), 200


# ============================================================
#  文件上传模块
# ============================================================
@app.route('/api/files/upload-token', methods=['POST'])
def get_upload_token():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "file_name" not in data:
        return jsonify({"code": 400, "message": "缺少file_name", "data": None}), 400

    file_key = f"fk-{uuid.uuid4().hex[:12]}"
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO file_uploads (file_key, file_name, file_type, user_id, committed)
                   VALUES (%s, %s, %s, %s, 0)""",
                (file_key, data["file_name"], data.get("file_type", ""), uid)
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"file_key": file_key}}), 200


@app.route('/api/files/commit', methods=['POST'])
def commit_file():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "file_key" not in data:
        return jsonify({"code": 400, "message": "缺少file_key", "data": None}), 400

    file_key = data["file_key"]
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE file_uploads SET committed = 1 WHERE file_key = %s AND user_id = %s",
                (file_key, uid)
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    if affected == 0:
        return jsonify({"code": 400, "message": "无效的file_key", "data": None}), 400

    return jsonify({"code": 0, "message": "success",
                    "data": {"file_key": file_key, "status": "committed"}}), 200


# ============================================================
#  订单模块
# ============================================================
@app.route('/api/orders', methods=['POST'])
def create_order():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "product_id" not in data:
        return jsonify({"code": 400, "message": "缺少product_id", "data": None}), 400

    order_id = f"ORD{int(time.time())}{uuid.uuid4().hex[:4].upper()}"
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO orders (order_id, user_id, product_id, quantity, address, status)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (order_id, uid, data["product_id"],
                 data.get("quantity", 1), data.get("address", ""), "pending")
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"order_id": order_id}}), 201


@app.route('/api/orders/<order_id>', methods=['GET'])
def get_order(order_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM orders WHERE order_id = %s AND user_id = %s",
                (order_id, uid)
            )
            order = cur.fetchone()
    finally:
        conn.close()

    if not order:
        return jsonify({"code": 404, "message": "订单不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": order}), 200


@app.route('/api/orders/<order_id>/cancel', methods=['PUT'])
def cancel_order(order_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET status = 'cancelled' WHERE order_id = %s AND user_id = %s",
                (order_id, uid)
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    if affected == 0:
        return jsonify({"code": 404, "message": "订单不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success",
                    "data": {"order_id": order_id, "status": "cancelled"}}), 200


@app.route('/api/orders/<order_id>', methods=['DELETE'])
def delete_order(order_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM orders WHERE order_id = %s AND user_id = %s",
                (order_id, uid)
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    if affected == 0:
        return jsonify({"code": 404, "message": "订单不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": None}), 200


# ============================================================
#  项目模块
# ============================================================
@app.route('/api/projects', methods=['POST'])
def create_project():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "name" not in data:
        return jsonify({"code": 400, "message": "缺少name", "data": None}), 400

    project_id = f"PRJ{uuid.uuid4().hex[:8].upper()}"
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO projects (id, name, user_id) VALUES (%s, %s, %s)",
                (project_id, data["name"], uid)
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"id": project_id}}), 201


@app.route('/api/projects/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tasks WHERE project_id = %s", (project_id,))
            cur.execute("DELETE FROM projects WHERE id = %s AND user_id = %s", (project_id, uid))
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": None}), 200


# ============================================================
#  任务模块
# ============================================================
@app.route('/api/projects/<project_id>/tasks', methods=['POST'])
def create_task(project_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM projects WHERE id = %s AND user_id = %s", (project_id, uid))
            if not cur.fetchone():
                return jsonify({"code": 404, "message": "项目不存在", "data": None}), 404

        data = request.get_json(silent=True)
        if not data or "title" not in data:
            return jsonify({"code": 400, "message": "缺少title", "data": None}), 400

        task_id = f"TSK{uuid.uuid4().hex[:8].upper()}"
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO tasks (id, project_id, title, priority, status)
                   VALUES (%s, %s, %s, %s, %s)""",
                (task_id, project_id, data["title"], data.get("priority", "medium"), "open")
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"id": task_id}}), 201


@app.route('/api/projects/<project_id>/tasks/<task_id>', methods=['GET'])
def get_task(project_id, task_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tasks WHERE id = %s AND project_id = %s",
                (task_id, project_id)
            )
            task = cur.fetchone()
    finally:
        conn.close()

    if not task:
        return jsonify({"code": 404, "message": "任务不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": task}), 200


@app.route('/api/projects/<project_id>/tasks/<task_id>', methods=['PUT'])
def update_task(project_id, task_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tasks WHERE id = %s AND project_id = %s",
                (task_id, project_id)
            )
            task = cur.fetchone()
            if not task:
                return jsonify({"code": 404, "message": "任务不存在", "data": None}), 404

            data = request.get_json(silent=True)
            if data:
                updates = []
                values = []
                for key in ("title", "priority", "status"):
                    if key in data:
                        updates.append(f"{key} = %s")
                        values.append(data[key])
                if updates:
                    values.extend([task_id, project_id])
                    cur.execute(
                        f"UPDATE tasks SET {', '.join(updates)} WHERE id = %s AND project_id = %s",
                        values
                    )
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
            updated = cur.fetchone()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": updated}), 200


# ============================================================
#  首页
# ============================================================
@app.route('/', methods=['GET'])
def home():
    return '<h1>Mock API Server (Concurrent Safe)</h1>'


if __name__ == '__main__':
    # ★ 关键：关闭 debug，开启多线程
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,          # 生产模式，不开 reloader
        threaded=True         # 每个请求一个线程，支持并发
    )
```

用例解耦改造

conftest.py（根目录）

```
# conftest.py（根目录）

import pytest
from common.http_client import HttpClient
from common.yaml_handler import get_config


def pytest_addoption(parser):
    parser.addoption("--env", default="dev", help="运行环境: dev/prod")


@pytest.fixture(scope="session")
def env_name(request):
    return request.config.getoption("--env")


@pytest.fixture(scope="session")
def http(env_name):
    """
    全局 HTTP 客户端。
    注意：xdist 下每个 worker 会各自创建一个，互不干扰。
    """
    cfg = get_config(env_name)
    client = HttpClient(base_url=cfg["base_url"], timeout=cfg.get("timeout", 10))
    return client


@pytest.fixture(scope="session")
def logged_in_http(http):
    """
    已登录的 HTTP 客户端（session 级，每个 worker 登录一次）。
    登录是幂等操作，多个 worker 各登录一次完全没问题。
    """
    resp = http.post("/api/auth/login", json={
        "username": "testuser",
        "password": "Test@123"
    })
    assert resp.status_code == 200, f"登录失败: {resp.text}"
    data = resp.json()["data"]
    token = data["token"]
    user_id = data["user_id"]

    # 把 token 注入 session headers
    http.session.headers["Authorization"] = f"Bearer {token}"

    # 通过 fixture 的 request 对象存储，方便后续取 user_id
    http._user_id = user_id
    http._token = token

    return http


@pytest.fixture(scope="session")
def db():
    """全局数据库客户端"""
    from utils.db import db as db_client
    return db_client
```

testcases/conftest.py

```
# testcases/conftest.py

import pytest
import allure


@pytest.fixture(autouse=True)
def case_boundary(request):
    """每条用例的分隔线（纯日志，无状态）"""
    worker_id = request.config.workerinput.get("workerid", "master") \
        if hasattr(request.config, "workerinput") else "master"
    print(f"\n{'='*50}")
    print(f"▶ [{worker_id}] 开始用例: {request.node.name}")
    print(f"{'='*50}")
    yield
    print(f"◀ [{worker_id}] 结束用例: {request.node.name}")


# ============================================================
#  独立数据工厂 fixture（每条用例独立创建、独立清理）
# ============================================================

@pytest.fixture()
def fresh_order(logged_in_http):
    """
    每条用例独立的订单（function 级，默认就是 function）。
    创建 → yield → 清理，完全自包含。
    """
    with allure.step("前置：创建独立订单"):
        resp = logged_in_http.post("/api/orders", json={
            "product_id": "SKU_ISOLATED",
            "quantity": 1,
            "address": "隔离测试地址"
        })
        assert resp.status_code == 201, f"创建订单失败: {resp.text}"
        order_id = resp.json()["data"]["order_id"]

    yield order_id

    # teardown：清理自己创建的订单
    with allure.step("清理：删除订单"):
        logged_in_http.delete(f"/api/orders/{order_id}")


@pytest.fixture()
def fresh_project(logged_in_http):
    """每条用例独立的项目"""
    with allure.step("前置：创建独立项目"):
        resp = logged_in_http.post("/api/projects", json={"name": "隔离测试项目"})
        assert resp.status_code == 201, f"创建项目失败: {resp.text}"
        project_id = resp.json()["data"]["id"]

    yield project_id

    with allure.step("清理：删除项目"):
        logged_in_http.delete(f"/api/projects/{project_id}")


@pytest.fixture()
def fresh_task(logged_in_http, fresh_project):
    """
    每条用例独立的任务。
    依赖 fresh_project，但都是 function 级，每条用例独立一套。
    """
    with allure.step("前置：创建独立任务"):
        resp = logged_in_http.post(f"/api/projects/{fresh_project}/tasks", json={
            "title": "隔离测试任务",
            "priority": "high"
        })
        assert resp.status_code == 201, f"创建任务失败: {resp.text}"
        task_id = resp.json()["data"]["id"]

    yield {"project_id": fresh_project, "task_id": task_id}

    # task 会随 project 删除而级联删除，无需额外清理


@pytest.fixture()
def fresh_upload_token(logged_in_http):
    """每条用例独立的上传凭证"""
    with allure.step("前置：获取上传凭证"):
        resp = logged_in_http.post("/api/files/upload-token", json={
            "file_name": "isolated_test.png",
            "file_type": "image/png"
        })
        assert resp.status_code == 200, f"获取上传凭证失败: {resp.text}"
        file_key = resp.json()["data"]["file_key"]

    yield file_key
```

testcases/test_order.py（完全解耦版）

```
# testcases/test_order.py

import pytest
import allure


@allure.epic("订单中心")
@allure.feature("订单管理")
class TestOrder:

    def test_create_order(self, logged_in_http, db):
        """创建订单 + DB校验（自包含）"""
        with allure.step("创建订单"):
            resp = logged_in_http.post("/api/orders", json={
                "product_id": "SKU_CREATE_001",
                "quantity": 2,
                "address": "创建测试"
            })
            assert resp.status_code == 201
            order_id = resp.json()["data"]["order_id"]

        with allure.step("DB校验：记录存在且字段正确"):
            db.assert_field_value("orders", "order_id = %s", (order_id,),
                                  field="product_id", expected="SKU_CREATE_001")
            db.assert_field_value("orders", "order_id = %s", (order_id,),
                                  field="quantity", expected=2)
            db.assert_field_value("orders", "order_id = %s", (order_id,),
                                  field="status", expected="pending")

        # 自己清理
        logged_in_http.delete(f"/api/orders/{order_id}")

    def test_query_order(self, fresh_order, logged_in_http):
        """查询订单（用 fixture 创建的独立订单）"""
        with allure.step(f"查询订单 {fresh_order}"):
            resp = logged_in_http.get(f"/api/orders/{fresh_order}")

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "pending"
        assert resp.json()["data"]["product_id"] == "SKU_ISOLATED"

    def test_cancel_order(self, fresh_order, logged_in_http, db):
        """取消订单 + DB校验（独立订单，不影响别人）"""
        with allure.step(f"取消订单 {fresh_order}"):
            resp = logged_in_http.put(f"/api/orders/{fresh_order}/cancel")
            assert resp.status_code == 200
            assert resp.json()["data"]["status"] == "cancelled"

        with allure.step("DB校验：状态变为 cancelled"):
            db.assert_field_value("orders", "order_id = %s", (fresh_order,),
                                  field="status", expected="cancelled")

    def test_query_cancelled_order(self, fresh_order, logged_in_http):
        """取消后再查询，状态应为 cancelled"""
        # 先取消
        logged_in_http.put(f"/api/orders/{fresh_order}/cancel")

        # 再查询
        resp = logged_in_http.get(f"/api/orders/{fresh_order}")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cancelled"

    def test_query_nonexistent_order(self, logged_in_http):
        """查询不存在的订单返回 404（无前置依赖）"""
        resp = logged_in_http.get("/api/orders/ORD_NOT_EXIST_999")
        assert resp.status_code == 404

    def test_create_order_missing_product_id(self, logged_in_http):
        """缺少 product_id 返回 400（无前置依赖）"""
        resp = logged_in_http.post("/api/orders", json={
            "quantity": 1
        })
        assert resp.status_code == 400
```

testcases/test_project_task.py（完全解耦版）

```
# testcases/test_project_task.py

import pytest
import allure


@allure.epic("项目管理")
@allure.feature("项目与任务")
class TestProjectTask:

    def test_create_project(self, logged_in_http, db):
        """创建项目 + DB校验"""
        with allure.step("创建项目"):
            resp = logged_in_http.post("/api/projects", json={"name": "独立项目A"})
            assert resp.status_code == 201
            project_id = resp.json()["data"]["id"]

        with allure.step("DB校验"):
            db.assert_field_value("projects", "id = %s", (project_id,),
                                  field="name", expected="独立项目A")

        # 清理
        logged_in_http.delete(f"/api/projects/{project_id}")

    def test_create_task_in_project(self, fresh_project, logged_in_http, db):
        """在项目中创建任务（独立项目）"""
        with allure.step(f"在项目 {fresh_project} 中创建任务"):
            resp = logged_in_http.post(f"/api/projects/{fresh_project}/tasks", json={
                "title": "独立任务X",
                "priority": "low"
            })
            assert resp.status_code == 201
            task_id = resp.json()["data"]["id"]

        with allure.step("DB校验"):
            db.assert_field_value("tasks", "id = %s", (task_id,),
                                  field="title", expected="独立任务X")
            db.assert_field_value("tasks", "id = %s", (task_id,),
                                  field="priority", expected="low")

    def test_query_task(self, fresh_task, logged_in_http):
        """查询任务（fixture 自动创建独立的项目+任务）"""
        project_id = fresh_task["project_id"]
        task_id = fresh_task["task_id"]

        resp = logged_in_http.get(f"/api/projects/{project_id}/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "隔离测试任务"
        assert resp.json()["data"]["priority"] == "high"
        assert resp.json()["data"]["status"] == "open"

    def test_update_task_status(self, fresh_task, logged_in_http, db):
        """更新任务状态（独立数据，不影响其他用例）"""
        project_id = fresh_task["project_id"]
        task_id = fresh_task["task_id"]

        with allure.step("更新状态为 done"):
            resp = logged_in_http.put(
                f"/api/projects/{project_id}/tasks/{task_id}",
                json={"status": "done"}
            )
            assert resp.status_code == 200

        with allure.step("DB校验"):
            db.assert_field_value("tasks", "id = %s", (task_id,),
                                  field="status", expected="done")

    def test_update_task_priority(self, fresh_task, logged_in_http):
        """更新任务优先级"""
        project_id = fresh_task["project_id"]
        task_id = fresh_task["task_id"]

        resp = logged_in_http.put(
            f"/api/projects/{project_id}/tasks/{task_id}",
            json={"priority": "critical"}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["priority"] == "critical"

    def test_delete_project_cascade_tasks(self, fresh_task, logged_in_http, db):
        """删除项目时级联删除任务"""
        project_id = fresh_task["project_id"]
        task_id = fresh_task["task_id"]

        with allure.step("删除项目"):
            resp = logged_in_http.delete(f"/api/projects/{project_id}")
            assert resp.status_code == 200

        with allure.step("DB校验：任务也被删除"):
            row = db.query_one("SELECT * FROM tasks WHERE id = %s", (task_id,))
            assert row is None, "任务应随项目级联删除"

        # 注意：fresh_task 的 teardown 会尝试删除 project，
        # 但已经被删了，Flask 返回 200，不会报错
```

testcases/test_profile.py（完全解耦版）

```
# testcases/test_profile.py

import allure


@allure.epic("用户中心")
@allure.feature("个人信息")
class TestProfile:

    def test_get_profile(self, logged_in_http):
        """获取个人信息（只需登录态）"""
        user_id = logged_in_http._user_id

        resp = logged_in_http.get(f"/api/users/{user_id}/profile")
        assert resp.status_code == 200
        assert resp.json()["data"]["username"] == "testuser"

    def test_get_profile_not_found(self, logged_in_http):
        """查询不存在的用户"""
        resp = logged_in_http.get("/api/users/99999/profile")
        assert resp.status_code == 404

    def test_update_avatar(self, logged_in_http, fresh_upload_token):
        """更新头像（用独立的上传凭证）"""
        resp = logged_in_http.put("/api/users/me/avatar", json={
            "file_key": fresh_upload_token
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["avatar"] == fresh_upload_token

    def test_update_avatar_invalid_key(self, logged_in_http):
        """无效的 file_key 返回 400"""
        resp = logged_in_http.put("/api/users/me/avatar", json={
            "file_key": "fk-invalid-key-123"
        })
        assert resp.status_code == 400
```

testcases/test_file_upload.py（完全解耦版）

```
# testcases/test_file_upload.py

import allure


@allure.epic("文件管理")
@allure.feature("文件上传")
class TestFileUpload:

    def test_get_upload_token(self, logged_in_http):
        """获取上传凭证"""
        resp = logged_in_http.post("/api/files/upload-token", json={
            "file_name": "test_doc.pdf",
            "file_type": "application/pdf"
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["file_key"] is not None

    def test_commit_file(self, logged_in_http, fresh_upload_token):
        """用凭证提交文件"""
        resp = logged_in_http.post("/api/files/commit", json={
            "file_key": fresh_upload_token
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "committed"

    def test_commit_invalid_key(self, logged_in_http):
        """无效凭证提交返回 400"""
        resp = logged_in_http.post("/api/files/commit", json={
            "file_key": "fk-nonexistent-key"
        })
        assert resp.status_code == 400

    def test_upload_token_missing_filename(self, logged_in_http):
        """缺少 file_name 返回 400"""
        resp = logged_in_http.post("/api/files/upload-token", json={
            "file_type": "image/png"
        })
        assert resp.status_code == 400
```

testcases/test_generic_isolated.py

```
# testcases/test_generic_isolated.py

import pytest
import allure
from utils.data_loader import load_test_data
from utils.jsonpath_util import extract_json


def _resolve_template(template: str, context: dict) -> str:
    """简易模板替换：${setup.order_id} → context['setup']['order_id']"""
    import re
    def _replace(m):
        keys = m.group(1).split(".")
        val = context
        for k in keys:
            val = val[k]
        return str(val)
    return re.sub(r'\$\{(.+?)\}', _replace, template)


def _execute_request(http, req_config, context):
    """执行单个请求配置"""
    url = _resolve_template(req_config["url"], context)
    method = req_config["method"]
    kwargs = {}
    if "json" in req_config:
        kwargs["json"] = req_config["json"]
    if "params" in req_config:
        kwargs["params"] = req_config["params"]

    resp = getattr(http, method)(url, **kwargs)
    return resp


ORDER_ISO_DATA = load_test_data("order.yaml", "test_order_isolated")


@allure.epic("订单中心")
@allure.feature("隔离数据驱动")
class TestOrderIsolated:

    @pytest.mark.parametrize("case_id, case_data", ORDER_ISO_DATA,
                             ids=[d[0] for d in ORDER_ISO_DATA])
    def test_order_flow(self, logged_in_http, case_id, case_data):
        """每条用例：setup → request → assert → teardown，完全自包含"""
        allure.dynamic.title(f"[{case_id}] {case_data['title']}")
        context = {}

        try:
            # Setup
            if "setup" in case_data:
                setup_resp = _execute_request(logged_in_http, case_data["setup"], context)
                assert setup_resp.status_code in (200, 201), \
                    f"Setup失败: {setup_resp.text}"
                context["setup"] = setup_resp.json().get("data", {})

            # Request
            req = case_data["request"]
            url = _resolve_template(req["url"], context)
            method = req["method"]
            kwargs = {k: v for k, v in req.items() if k in ("json", "params", "data", "headers")}
            resp = getattr(logged_in_http, method)(url, **kwargs)

            # Assert
            expect = case_data["expect"]
            assert resp.status_code == expect["status_code"]
            for path, expected_value in expect.get("json_path", []):
                actual = extract_json(resp.json(), path)
                if expected_value == "not_null":
                    assert actual is not None
                else:
                    assert actual == expected_value

        finally:
            # Teardown（无论成功失败都清理）
            if "teardown" in case_data and context:
                try:
                    _execute_request(logged_in_http, case_data["teardown"], context)
                except Exception:
                    pass  # 清理失败不影响用例结果
```

config/testdata/order.yaml（解耦版）

```
# ✅ 解耦版：每条用例自带 setup/teardown
test_order_isolated:
  - case_id: ORDER_ISO_001
    title: "创建订单后查询"
    setup:                              # ← 自己创建
      method: post
      url: /api/orders
      json:
        product_id: "SKU_ISO_001"
        quantity: 1
    request:
      method: get
      url: "/api/orders/${setup.order_id}"
    expect:
      status_code: 200
      db_check:
        - table: orders
          where: "order_id = %s"
          params: [ "${setup.order_id}" ]
          field: status
          expected: "pending"
      json_path:
        - ["$.data.status", "pending"]
    teardown:                           # ← 自己清理
      method: delete
      url: "/api/orders/${setup.order_id}"

  - case_id: ORDER_ISO_002
    title: "取消订单并验证DB"
    setup:
      method: post
      url: /api/orders
      json:
        product_id: "SKU_ISO_002"
        quantity: 1
    request:
      method: put
      url: "/api/orders/${setup.order_id}/cancel"
    expect:
      status_code: 200
      db_check:
        - table: orders
          where: "order_id = %s"
          params: ["${setup.order_id}"]
          field: status
          expected: "cancelled"
    teardown:
      method: delete
      url: "/api/orders/${setup.order_id}"
```

删除的文件

common/context.py → 不再需要

utils/context_resolver.py → 不再需要（改用 fixture 传参）

## 🎯 落地路线图建议

第1天：搭目录 + 装环境 + 跑通第一个 requests 请求第2-3天：完成 HTTP 封装 + 日志 + YAML 配置第4-5天：写 3-5 个核心接口的数据驱动用例第6天：接入 Allure，本地报告跑通第7天：上 Jenkins Pipeline，配置定时任务之后：按业务模块逐步扩充用例，每周review框架痛点

```
第1天：搭目录 + 装环境 + 跑通第一个 requests 请求
第2-3天：完成 HTTP 封装 + 日志 + YAML 配置
第4-5天：写 3-5 个核心接口的数据驱动用例
第6天：接入 Allure，本地报告跑通
第7天：上 Jenkins Pipeline，配置定时任务
之后：按业务模块逐步扩充用例，每周review框架痛点
```

## 📋 阶段十一：项目演进 V2 工程化升级（按真实项目演进补全）

前面阶段一到阶段十教的是"从零搭起一个能跑的接口自动化框架"。但实战中框架要上线 Jenkins、要扛住多 worker 并发、要在被中断后能恢复、要避免敏感信息泄露到 Allure 报告里——这些都不在最初的教学范围内。

这一章把项目实际演进过程中补的所有工程化能力整理出来，对应到当前仓库的代码文件。读完前十章再看这一章，就能理解"教程版"和"生产版"的差距在哪里。

★ 与前面章节的关系：阶段一到阶段十的代码片段保留作为"V1 教学版"，本章不替换它们，只补充 V2 实际采用的写法。读者可以两边对比着看。

### 11.1 共享 MySQL 连接池（common/db_pool.py）

V1 的 mock_flask.py 把数据库连接配置硬编码在文件里（host=localhost、password=Root@123456），改密码要改两个地方。V2 抽出 common/db_pool.py，按 (env, database, autocommit) 三元组缓存连接池，mock_flask 和测试 DBClient 共用同一份配置。

```
"""共享 MySQL 连接池，供 mock_flask 与测试 DB 客户端使用。"""
import pymysql
from dbutils.pooled_db import PooledDB
from common.yaml_handler import get_config

_pools = {}

def get_pool(env="dev", database="api_test", autocommit=True):
    """按 (env, database, autocommit) 缓存连接池。"""
    key = (env, database, autocommit)
    if key not in _pools:
        cfg = get_config(env)
        _pools[key] = PooledDB(
            creator=pymysql,
            maxconnections=20,
            mincached=2,
            maxcached=5,
            blocking=True,
            host=cfg.get("db_host", "localhost"),
            port=cfg.get("db_port", 3306),
            user=cfg.get("db_user", "root"),
            password=cfg.get("db_password", ""),
            database=database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=autocommit,
        )
    return _pools[key]
```

★ 关键设计：

• maxconnections=20 够 4 个 xdist worker 共用，每个 worker 独立连接池

• blocking=True 连接耗尽时等待而非报错，避免偶发"too many connections"

• autocommit 区分：mock_flask 用 False（要事务），DBClient 用 True（查询只读）

• cursorclass=DictCursor 返回 dict 而非 tuple，断言时直接 row["field"] 取值

### 11.2 敏感字段脱敏（common/sanitize.py）

V1 的 HttpClient 把 kwargs 和 resp.json() 原样写到日志和 Allure 附件里，password / token / Authorization 全部明文出现在 Jenkins 报告里，有权限看报告的人都能看到测试账号密码。V2 加了 sanitize_for_report 递归脱敏。

```
"""敏感字段脱敏，用于日志 / Allure 附件。"""

SENSITIVE_KEYS = frozenset({
    "password", "token", "authorization", "secret",
    "access_token", "db_password", "refresh_token",
})
MASK = "***"

def sanitize_for_report(data):
    """递归脱敏 dict / list 中的敏感字段。"""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            if key.lower() in SENSITIVE_KEYS:
                sanitized[key] = MASK
            elif key.lower() == "headers" and isinstance(value, dict):
                sanitized[key] = _sanitize_headers(value)
            else:
                sanitized[key] = sanitize_for_report(value)
        return sanitized
    if isinstance(data, list):
        return [sanitize_for_report(item) for item in data]
    return data

def _sanitize_headers(headers):
    result = {}
    for key, value in headers.items():
        if key.lower() == "authorization":
            result[key] = f"Bearer {MASK}"
        elif key.lower() in SENSITIVE_KEYS:
            result[key] = MASK
        else:
            result[key] = value
    return result
```

★ HttpClient.request 里两处使用：

• log.info(f"   参数: {sanitize_for_report(kwargs)}") —— 请求参数日志脱敏

• log.info(f"   响应体: {sanitize_for_report(resp.json())}") —— 响应体日志脱敏

★ key.lower() 比较保证 Password / TOKEN / Authorization 大小写都能匹配到。

### 11.3 测试账号统一管理（utils/accounts.py + config/test_accounts.yaml）

V1 的 conftest.py 把账号密码硬编码在 fixture 里（"testuser" / "Test@123"），改密码要改 Python 代码。V2 抽到 config/test_accounts.yaml，conftest fixture 和 YAML 数据驱动用例共用同一份账号，散落维护问题根治。

```
# config/test_accounts.yaml
accounts:
  default:                # ← 主测试用户（session 级 logged_in_http 用）
    username: testuser
    password: Test@123
  user_b:                  # ← 备用账号（new_user fixture 用，注册时附随机后缀）
    username: user_b
    password: pass_b_123
# utils/accounts.py
import os
from functools import lru_cache
from common.yaml_handler import read_yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@lru_cache
def load_accounts():
    path = os.path.join(BASE_DIR, "config", "test_accounts.yaml")
    return read_yaml(path)["accounts"]

def get_account(name="default"):
    return load_accounts()[name]

def get_accounts_context():
    """供 case_runner 模板变量 ${accounts.default.username} 使用。"""
    return load_accounts()
```

★ conftest.py 用 get_account("default")；YAML 用例用 ${accounts.default.username}，两边引用同一份配置，改密码只改 yaml 一处。

### 11.4 YAML 用例执行引擎（utils/case_runner.py + 模板变量递归解析）

V1 的 test_generic_isolated.py 把 _resolve_template / _execute_request 写在用例文件里，每个 YAML 用例都要自己复制一份解析逻辑。V2 抽到 utils/case_runner.py，支持 setup → request → json_path 断言 → db_check 数据库断言 → teardown 完整流程，模板变量 ${setup.xxx} / ${accounts.xxx} 在 str / list / dict 任意层级递归解析。

```
# utils/case_runner.py 核心函数
def resolve_template(template: str, context: dict) -> str:
    """${setup.order_id} / ${accounts.default.username} → 实际值。"""
    def _replace(match):
        keys = match.group(1).split(".")
        value = context
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                raise KeyError(
                    f"模板变量 ${{{match.group(1)}}} 解析失败: "
                    f"路径 '{key}' 不存在。"
                    f"当前 context keys: {list(context.keys())}"
                )
        return str(value)
    return re.sub(r"\$\{(.+?)\}", _replace, template)

def resolve_value(value, context: dict):
    """递归解析 str / list / dict 中的模板变量。"""
    if isinstance(value, str) and "${" in value:
        return resolve_template(value, context)
    if isinstance(value, list):
        return [resolve_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: resolve_value(item, context) for key, item in value.items()}
    return value

def run_flow_case(http, case_data, db=None, case_id=None):
    """setup → request → assert → teardown 完整流程。"""
    context = build_context()
    try:
        if "setup" in case_data:
            setup_resp = execute_request(http, case_data["setup"], context)
            assert setup_resp.status_code in (200, 201)
            context["setup"] = setup_resp.json().get("data", {})
        resp = execute_request(http, case_data["request"], context)
        assert_response(resp, case_data["expect"], db=db, context=context)
        return resp
    finally:
        if "teardown" in case_data and context:
            try:
                execute_request(http, case_data["teardown"], context)
            except Exception as exc:
                log.warning("[%s] Teardown 失败（已忽略）: %s", case_id, exc, exc_info=True)
```

★ 用例侧只一行：

```
ORDER_ISO_DATA = load_parametrize_data("order.yaml", "test_order_isolated")

@pytest.mark.parametrize("case_id, case_data", ORDER_ISO_DATA)
def test_order_flow(self, logged_in_http, db, case_id, case_data):
    allure.dynamic.title(f"[{case_id}] {case_data['title']}")
    run_flow_case(logged_in_http, case_data, db=db, case_id=case_id)
```

### 11.5 JSONPath 升级到 jsonpath-ng（utils/jsonpath_util.py）

V1 自己写了一个简易 JSONPath 解析器，只支持 $.a.b.c 和 $.list[0].name，遇到 $.list[*].name / $..key / $[?(@.status=='ok')] 这种语法就废了。V2 直接引入 jsonpath-ng 库，支持完整 JSONPath 语法，再封一层薄壳保持原 API。

```
"""JSONPath 提取工具，基于 jsonpath-ng。
支持完整 JSONPath 语法：$.a.b.c / $.list[0].name / $.list[*].name / $..key / $[?(@.status=='ok')]
"""
from jsonpath_ng import parse as _parse

def _normalize(path):
    if not path:
        return None
    if not path.startswith("$"):
        path = "$." + path
    return path

def extract_json(data, path):
    """从 data 中按 JSONPath 提取**第一个**匹配值，无匹配返回 None。"""
    norm = _normalize(path)
    if norm is None:
        return None
    try:
        expr = _parse(norm)
        matches = [m.value for m in expr.find(data)]
    except Exception:
        return None
    return matches[0] if matches else None

def extract_json_all(data, path):
    """从 data 中按 JSONPath 提取**所有**匹配值列表，无匹配返回 []。"""
    norm = _normalize(path)
    if norm is None:
        return []
    try:
        expr = _parse(norm)
        return [m.value for m in expr.find(data)]
    except Exception:
        return []
```

★ requirements.txt 加一行 jsonpath-ng==1.6.1。

### 11.6 SQL 注入防护（utils/db.py 的 _validate_identifier）

V1 的 db.py 直接 f"SELECT {field} FROM {table} WHERE {where}" 拼接 SQL，field / table / where 全外部传入。虽然 case_runner 的 YAML 受信任，但代码层面没有任何校验，新人写用例可能拼出意外字符串。V2 在 DBClient 入口加正则白名单。

```
import re

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

def _validate_identifier(name, kind):
    """校验表名/字段名是否为合法标识符（防 SQL 注入）。"""
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"非法 {kind} 标识符: {name!r}（仅允许字母数字下划线）")
    return name

class DBClient:
    ...
    def count(self, table, where=None, params=None):
        _validate_identifier(table, "表名")
        sql = f"SELECT COUNT(*) AS cnt FROM {table}"
        if where:
            sql += f" WHERE {where}"
        row = self.query_one(sql, params)
        return row["cnt"] if row else 0

    def assert_field_value(self, table, where, params, field, expected):
        _validate_identifier(table, "表名")
        _validate_identifier(field, "字段名")
        row = self.query_one(
            f"SELECT {field} FROM {table} WHERE {where}", params
        )
        assert row is not None, ...
        actual = row[field]
        assert actual == expected, ...
```

★ 同时 query / execute / query_one 中的 cursor.execute 包了 try-except + log.error，异常会经 logger 落盘到 logs/{当天}.log 后再向上抛，Jenkins 失败归档日志完整。

### 11.7 用户身份隔离模式（authed_user_http / new_user）

V1 用 session 级 logged_in_http 跑所有用例，token 在所有用例间共享。测多用户权限隔离场景（"新用户不能看 default 用户的订单"）时，要在用例里手动改 header，跑完再改回去，并发模式下极易 token 污染。V2 设计了 fixture 组合：

• user_http (function scope)：每条用例独立 HttpClient 实例，与 session 级 http 完全隔离

• new_user (function scope)：注册一个随机用户名（uuid 后缀），返回 {token, user_id, username, auth_header}

• authed_user_http = user_http + new_user：在独立实例上设置新用户 token，调用方拿到的 client 已带 Authorization

```
# testcases/conftest.py
@pytest.fixture
def user_http(env_name):
    """用例级独立 HttpClient 实例。"""
    cfg = get_config(env_name)
    client = HttpClient(base_url=cfg["base_url"], env=env_name, timeout=cfg.get("timeout", 10))
    yield client
    client.session.close()

@pytest.fixture
def new_user(user_http, db):
    """注册随机用户，teardown 从 DB 按外键依赖逐表清理。"""
    account = get_account("user_b")
    unique_username = f"{account['username']}_{uuid.uuid4().hex[:8]}"
    resp = user_http.post("/api/auth/register", json={...})
    user_info = {"token": ..., "user_id": ..., "username": unique_username, ...}
    yield user_info
    # teardown：按 tasks → orders → projects → file_uploads → users 顺序删
    for table, where in [...]:
        db.execute(f"DELETE FROM {table} WHERE {where}", (user_id,))
    db.execute("DELETE FROM users WHERE user_id = %s", (user_id,))

@pytest.fixture
def authed_user_http(user_http, new_user):
    """组合体：独立实例 + 新用户 token。"""
    user_http.session.headers["Authorization"] = new_user["auth_header"]["Authorization"]
    user_http._user_id = new_user["user_id"]
    return user_http
```

★ 用例侧天然干净：

```
@allure.story("跨用户权限隔离")
def test_user_http_cannot_see_others_order(self, authed_user_http, fresh_order):
    """新用户访问 default 用户的订单，应返回 404。"""
    resp = authed_user_http.get(f"/api/orders/{fresh_order}")
    assert resp.status_code == 404
```

★ 并发安全：每条用例独立 HttpClient + 随机用户名，多 worker 互不冲突；session 级 logged_in_http 不被污染。

### 11.8 Mock 服务日志化（mock_flask.py 接入 common.logger）

V1 的 mock_flask.py 用 print 调试，Flask 默认不写日志。Jenkins 归档的 logs/*.log 是 pytest 的，mock 服务的运行轨迹完全丢失。V2 让 mock_flask 复用 common.logger（与 pytest 同一 logger 实例），关键事件落盘：

• 故障注入触发 → log.warning("⚡ [FAULT] 用户 xxx 触发故障注入，剩余 N 次")

• 登录失败（用户名或密码错误）→ log.info("🔑 登录失败: username=xxx")

• /api/ping DB 健康检查异常 → log.error("/api/ping DB 健康检查失败: ...")

```
# mock_flask.py
from common.logger import log

# 故障注入处
if injected:
    log.warning(f"⚡ [FAULT] 用户 {username} 触发故障注入，剩余 {remaining} 次")
    return jsonify({"code": 500, "message": "临时故障", "data": None}), 500

log.info(f"🔑 登录失败（用户名或密码错误）: username={username}")
return jsonify({"code": 401, "message": "用户名或密码错误", "data": None}), 401
```

★ 日志路径：项目根目录/logs/{YYYY-MM-DD}.log（按天 + 10MB 滚动，保留 5 个备份）。Jenkins post.always 自动归档到 Artifacts。

### 11.9 Mock 生命周期管理（scripts/ensure_mock.py）

V1 直接 python mock_flask.py 前台启动，Jenkins 构建结束时 Windows JobObject 自动 kill 子进程，没有 PID 管理、没有健康检查、没有数据重置兜底。V2 写了 scripts/ensure_mock.py 托管完整生命周期：

• start —— 已在跑就跳过；没在跑就后台启动 + 写 PID 文件 + 探测就绪（最多 30 秒）

• status —— 健康检查（探测 / 端点 + 检查 PID 进程是否存活），exit 0=正常 exit 1=未响应

• stop —— 按 PID 文件 kill；PID 失效则按端口占用兜底清理

• reset-db —— 清空 orders/projects/tasks/file_uploads 四张业务表，保留 users 种子数据；失败即终止流水线

• db-status —— 打印各表数据量快照（不清空，用于 Jenkins 失败时诊断现场）

```
# scripts/ensure_mock.py 核心子命令
def cmd_start(env_name):
    if is_mock_up(base_url):
        return 0  # 已在跑
    proc = start_mock()
    _write_pid(proc.pid)
    if wait_until_ready(base_url):
        return 0
    _clear_pid()
    return 1

def cmd_reset_db(env_name):
    """直连 MySQL，不依赖 Mock 服务是否启动。"""
    tables = ["tasks", "file_uploads", "orders", "projects"]
    conn = pool.connection()
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in tables:
            cur.execute(f"TRUNCATE TABLE {table}")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    return 0
```

★ prod 环境自动跳过所有 Mock 操作：env != "dev" 时五个子命令都直接退出 0，便于同一套 Jenkinsfile 在 prod 环境只跑接口测试不启 Mock。

### 11.10 Jenkins Pipeline 工程化（Jenkinsfile 重构）

V1 的 Jenkinsfile 是单阶段 bat 块，每个步骤都写一遍 chcp 65001 + PYTHON_PATH，没有失败重试、没有诊断归档、钉钉 webhook 硬编码。V2 重构为 4 个主阶段 + 子阶段结构：

• 阶段 1：信息采集 & 准备（清理工作区 / 获取构建用户 / 拉代码 retry 3 / 装依赖 retry 3 + 10min 超时）

• 阶段 2：Mock 与数据重置（仅 dev）—— start + status 健康检查 + reset-db 失败即终止流水线

• 阶段 3：执行测试 & 写环境信息（catchError 包裹保证报告阶段继续 + 写 environment.properties / executor.json）

• 阶段 4：生成 Allure 报告（reportBuildPolicy: ALWAYS 总是生成）

• post.always：停止 Mock + 归档 logs/*.log + 构建耗时盘点

• post.failure：收集 diagnostics/（db-status 快照 + 日志）+ 归档 + 发送失败通知

★ 关键工程化封装：

```
// 统一 Python 命令封装：自动 chcp 65001（中文不乱码）+ PYTHON_PATH 拼接
def pythonCmd(String pyArgs, String extraArgs = '') {
    return """
        @echo off
        chcp 65001 >nul
        "${env.PYTHON_PATH}" ${pyArgs} ${extraArgs}
    """.stripIndent().trim()
}

// 钉钉 webhook 走 Jenkins Credentials（ID: dingtalk_webhook），不硬编码
environment {
    DINGTALK_WEBHOOK = credentials('dingtalk_webhook')
    DINGTALK_KEYWORD = '测试'
}
```

★ catchError 包裹测试阶段：pytest 用例失败返回非 0，但报告阶段继续执行，最后按测试结果标记构建。

### 11.11 失败诊断机制（diagnostics 归档）

V1 测试失败时只有 pytest 控制台日志，定位"是数据残留还是用例本身的问题"要重新跑一次。V2 加了失败诊断归档：构建失败时自动收集现场快照到 Jenkins Artifacts。

```
// Jenkinsfile post.failure
failure {
    script {
        catchError(buildResult: null, stageResult: null, message: "诊断信息收集失败") {
            bat 'if not exist "diagnostics" mkdir diagnostics'
            // 1) 抓 DB 当前数据量快照
            if (params.ENV == 'dev') {
                bat script: pythonCmd('scripts/ensure_mock.py', "db-status --env ${params.ENV} > diagnostics\\db_status.txt 2>&1")
            }
            // 2) 复制 mock + pytest 日志
            bat 'copy /Y logs\\*.log diagnostics\\ >nul'
            // 3) 归档到 Jenkins Artifacts
            archiveArtifacts artifacts: 'diagnostics/**/*', allowEmptyArchive: true
        }
        notifyAll('FAILURE', 'red', '❌')
    }
}
```

★ 打开该次构建的 Artifacts → diagnostics/ 目录：

• db_status.txt — 各业务表数据量快照（失败现场）

• *.log — pytest 和 mock 的日志副本

★ 如果 orders/projects/tasks/file_uploads 任一表数据量异常大，多半是上一次构建中断导致的数据残留；下次构建的 stage 2.2 会自动清空。

### 11.12 注册接口测试用例（testcases/test_register.py）

V1 的 conftest.py 用 new_user fixture 间接调 register，但没有专门测试 register 接口本身。V2 新增 testcases/test_register.py，用 user_http + 随机用户名 + db.execute 直连清理的方式自包含测试：

• test_register_success —— 注册全新用户，返回 user_id 和 token，并 DB 校验落库

• test_register_idempotent —— 重复注册同一用户名，应返回相同 user_id（幂等）

• test_register_empty_body —— 空 body 返回 400

```
# testcases/test_register.py
@pytest.mark.smoke
def test_register_success(self, user_http, db):
    """正向：注册全新用户，返回 user_id 和 token，并落库。"""
    account = get_account("user_b")
    username = f"reg_ok_{uuid.uuid4().hex[:8]}"
    user_id = None
    try:
        resp = user_http.post("/api/auth/register", json={
            "username": username,
            "password": account["password"],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["username"] == username
        # DB 校验：用户已落库
        row = db.query_one(
            "SELECT username FROM users WHERE user_id = %s",
            (data["user_id"],),
        )
        assert row is not None and row["username"] == username
        user_id = data["user_id"]
    finally:
        if user_id:
            db.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
```

★ 为什么不用 new_user fixture？因为 new_user 是已注册完成的状态，不能用于测试 register 接口本身的行为（重复注册、缺参数、空 body 等）。

### 11.13 小结：V1 → V2 的关键演进

把上面 12 个小节归纳一下，V2 比 V1 多出来的核心能力：

• 配置统一：连接池 / 账号 / Mock 服务都从 config.yaml 读，改一处全生效

• 安全：敏感字段脱敏 / 钉钉 webhook 走 Credentials / SQL 注入防护

• 隔离：每条用例独立 HttpClient + 随机用户名 + function 级 fixture，并发无冲突

• 韧性：Mock 服务生命周期托管 / reset-db 兜底 / 失败诊断归档 / retry + timeout

• 工程化：Jenkinsfile 4 阶段子结构 + pythonCmd 封装 + 钉钉+邮件统一通知入口

• 可读性：JSONPath 升级 jsonpath-ng / case_runner 抽公共引擎 / accounts 统一管理

★ 这些演进都不是"一开始就想到"，而是真实跑 Jenkins、被中断、被并发搞坏、看到敏感信息泄露到报告里之后逐步补的。建议读者按 V1 教程搭起来后，遇到具体痛点再回头看 V2 对应章节。
