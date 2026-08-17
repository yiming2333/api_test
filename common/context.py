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