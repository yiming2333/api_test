class TestTaskFlow:

    def test_query_task(self, http, context, task):
        """查询任务（task fixture 已保证 登录→项目→任务 全部就绪）"""
        project_id = context.get_or_fail("project_id")
        task_id    = context.get_or_fail("task_id")

        resp = http.get(f"/api/projects/{project_id}/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "测试任务"
        assert resp.json()["data"]["priority"] == "high"

    def test_update_task_status(self, http, context, task):
        """更新任务状态"""
        project_id = context.get_or_fail("project_id")
        task_id    = context.get_or_fail("task_id")

        resp = http.put(
            f"/api/projects/{project_id}/tasks/{task_id}",
            json={"status": "done"}
        )
        assert resp.status_code == 200