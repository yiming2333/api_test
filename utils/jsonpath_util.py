"""JSONPath 提取工具，基于 jsonpath-ng。

支持完整 JSONPath 语法，包括：
- ``$.a.b.c``         嵌套字段
- ``$.list[0].name``  数组索引
- ``$.list[*].name``  数组通配符
- ``$..key``          递归下降
- ``$[?(@.status=='ok')]`` 过滤器
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
