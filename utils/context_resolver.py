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