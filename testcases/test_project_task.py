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