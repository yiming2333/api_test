import logging
import os
from logging.handlers import RotatingFileHandler  # 按文件大小滚动的日志处理器
from datetime import datetime

# ============================================================
# 路径配置
# ============================================================

# 获取项目根目录（与 yaml_handler.py 同理，两次 dirname 回到根目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 日志存放目录：项目根目录/logs/
LOG_DIR = os.path.join(BASE_DIR, "logs")

# 自动创建 logs 目录（如果不存在的话）
# exist_ok=True 表示目录已存在时不报错，避免重复创建异常
os.makedirs(LOG_DIR, exist_ok=True)


# ============================================================
# 核心函数：获取 logger 实例
# ============================================================

def get_logger(name="api_test"):
    """
    获取一个配置好的 logger 实例

    设计要点：
    1. 同名 logger 是单例的 —— logging.getLogger("api_test") 多次调用返回同一个对象
    2. 通过 if logger.handlers 判断防止重复添加 handler（否则每调用一次就多一对输出）
    3. 同时输出到控制台 + 文件，方便本地调试和 Jenkins 归档

    Args:
        name: logger 名称，默认 "api_test"。不同模块可以用不同名字区分日志来源

    Returns:
        logging.Logger: 配置好的 logger 实例

    Usage:
        from common.logger import log
        log.info("测试开始")
        log.error(f"请求失败: {resp.status_code}")
    """

    # ---------- 第 1 步：获取或创建 logger ----------
    # Python logging 模块内部维护了一个字典 {name: Logger}
    # 相同 name 多次调用返回的是同一个 Logger 对象（单例模式）
    logger = logging.getLogger(name)

    # 设置最低日志级别为 DEBUG（所有级别都会处理，由 handler 各自决定输出哪些）
    logger.setLevel(logging.DEBUG)

    # ---------- 第 2 步：防止重复添加 handler ----------
    # 因为 getLogger 是单例，如果这个函数被调用多次，
    # 不加这个判断的话每次都会 addHandler，导致同一条日志打印 N 遍
    if logger.handlers:
        return logger  # 已经配置过了，直接返回

    # ---------- 第 3 步：定义日志格式 ----------
    # 最终效果示例：[2026-08-18 15:30:01] [INFO] 用户登录成功
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",  # 格式模板
        "%Y-%m-%d %H:%M:%S"  # 时间格式
    )
    # 常用格式占位符说明：
    # %(asctime)s   → 时间戳
    # %(levelname)s → 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
    # %(message)s   → 日志正文
    # %(name)s      → logger 名称
    # %(filename)s  → 产生日志的文件名
    # %(lineno)d    → 产生日志的行号

    # ---------- 第 4 步：添加控制台输出 ----------
    # StreamHandler 默认输出到 sys.stderr（终端/控制台）
    # 用途：本地开发时实时看到日志；Jenkins 构建时日志会出现在 Console Output 里
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)  # 控制台只显示 INFO 及以上（DEBUG 太琐碎，不在终端刷屏）
    logger.addHandler(sh)

    # ---------- 第 5 步：添加文件输出 ----------
    # 文件名按当天日期命名，例如：2026-08-18.log
    # 好处：每天一个文件，方便按天查找问题
    log_file = os.path.join(LOG_DIR, f"{datetime.now():%Y-%m-%d}.log")

    # RotatingFileHandler：按文件大小滚动
    # - maxBytes=10MB：单个日志文件最大 10MB
    # - backupCount=5：最多保留 5 个备份（xxx.log.1, xxx.log.2, ...）
    # - 超过 10MB 后自动重命名当前文件为 .1，新建空文件继续写
    # - encoding="utf-8"：确保中文日志不乱码
    fh = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,  # 保留 5 个历史文件
        encoding="utf-8"
    )
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)  # 文件记录所有级别（包括 DEBUG），方便排查问题
    logger.addHandler(fh)

    # ---------- 第 6 步：返回配置好的 logger ----------
    return logger


# ============================================================
# 模块级默认 logger 实例
# ============================================================
# 其他模块直接 from common.logger import log 就能用
# 不需要每次都调用 get_logger()
log = get_logger()