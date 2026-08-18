# testcases/test_task_flow.py

import allure


@allure.epic("项目管理")
@allure.feature("任务流程")
class TestTaskFlow:

    def test_create_task_verify_db(self, http, context, task, db):
        """创建任务后验证数据库"""
        task_id = context.get_or_fail("task_id")
        project_id = context.get_or_fail("project_id")

        with allure.step("DB校验：任务记录存在"):
            db.assert_record_exists(
                "tasks", "id = %s AND project_id = %s",
                (task_id, project_id),
                msg=f"任务 {task_id} "
            )

        with allure.step("DB校验：优先级为 high"):
            db.assert_field_value(
                "tasks", "id = %s", (task_id,),
                field="priority", expected="high"
            )

        with allure.step("DB校验：初始状态为 open"):
            db.assert_field_value(
                "tasks", "id = %s", (task_id,),
                field="status", expected="open"
            )

    def test_update_task_status_verify_db(self, http, context, task, db):
        """更新任务状态后验证数据库"""
        project_id = context.get_or_fail("project_id")
        task_id = context.get_or_fail("task_id")

        with allure.step("更新任务状态为 done"):
            resp = http.put(
                f"/api/projects/{project_id}/tasks/{task_id}",
                json={"status": "done"}
            )
            assert resp.status_code == 200

        with allure.step("DB校验：状态已更新为 done"):
            db.assert_field_value(
                "tasks", "id = %s", (task_id,),
                field="status", expected="done"
            )

    def test_query_task(self, http, context, task):
        project_id = context.get_or_fail("project_id")
        task_id = context.get_or_fail("task_id")
        resp = http.get(f"/api/projects/{project_id}/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "测试任务"
        assert resp.json()["data"]["priority"] == "high"