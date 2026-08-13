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