import yaml
import os

# 获取项目根目录的绝对路径
# __file__ 是当前文件（yaml_handler.py）的路径
# 第一次 dirname → common/ 目录
# 第二次 dirname → 项目根目录（api_test/）
# 这样无论在哪里调用这个模块，BASE_DIR 始终指向项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_yaml(file_path):
    """
    读取 YAML 文件，返回解析后的字典

    Args:
        file_path: YAML 文件的完整路径

    Returns:
        dict: YAML 内容解析后的 Python 字典

    Raises:
        FileNotFoundError: 文件不存在时抛出
        yaml.YAMLError: YAML 格式错误时抛出
    """
    with open(file_path, "r", encoding="utf-8") as f:
        # safe_load 比 load 更安全，不会执行 YAML 中的自定义标签/代码
        # 防止恶意 YAML 文件执行任意 Python 代码
        return yaml.safe_load(f)


def get_config(env="dev"):
    """
    获取指定环境的配置信息

    从 config/config.yaml 中读取对应环境的配置块，
    供 HttpClient、DBClient 等组件初始化时使用。

    Args:
        env: 环境名称，默认 "dev"，可选 "prod" 等
             对应 config.yaml 中 env.dev / env.prod 下的配置

    Returns:
        dict: 该环境下的配置字典，例如：
              {
                  "base_url": "http://127.0.0.1:5000",
                  "timeout": 10,
                  "db": {
                      "host": "127.0.0.1",
                      "port": 3306,
                      ...
                  }
              }

    Raises:
        KeyError: config.yaml 中不存在指定环境时抛出
        FileNotFoundError: config.yaml 文件不存在时抛出

    Usage:
        cfg = get_config("dev")
        client = HttpClient(base_url=cfg["base_url"])
    """
    # 拼接配置文件完整路径：项目根目录/config/config.yaml
    config_path = os.path.join(BASE_DIR, "config", "config.yaml")

    # 读取整个 YAML 文件，得到顶层字典
    # 结构示例：{"env": {"dev": {...}, "prod": {...}}}
    config = read_yaml(config_path)

    # 按环境名取出对应的配置块并返回
    return config["env"][env]