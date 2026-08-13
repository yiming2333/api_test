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