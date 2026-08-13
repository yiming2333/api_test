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