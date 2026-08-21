"""敏感字段脱敏，用于日志 / Allure 附件。"""

SENSITIVE_KEYS = frozenset({
    "password",
    "token",
    "authorization",
    "secret",
    "access_token",
    "db_password",
    "refresh_token",
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
