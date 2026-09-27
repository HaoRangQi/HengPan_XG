import unittest

from api.task_manager import TaskManager, TaskStatus


class CancellationContractTests(unittest.TestCase):
    def setUp(self):
        self.manager = TaskManager()
        self.task_id = self.manager.create_task()
        self.manager.update_task(self.task_id, status=TaskStatus.RUNNING)

    def test_status_exposes_cancel_request_and_cancel_is_idempotent(self):
        task = self.manager.get_task(self.task_id)
        self.assertFalse(task.to_dict()["cancel_requested"])

        self.assertTrue(self.manager.request_cancel(self.task_id))
        self.assertTrue(self.manager.request_cancel(self.task_id))
        self.assertTrue(task.to_dict()["cancel_requested"])
        self.assertEqual(task.status, TaskStatus.RUNNING)

    def test_terminal_task_cannot_be_cancelled(self):
        self.manager.update_task(self.task_id, status=TaskStatus.CANCELLED)
        self.assertFalse(self.manager.request_cancel(self.task_id))

    def test_streamed_results_stop_at_cancel_boundary(self):
        self.manager.append_streamed(self.task_id, [{"code": "before"}])
        self.assertEqual(self.manager.get_task(self.task_id).to_dict()["cursor"], 1)
        self.manager.request_cancel(self.task_id)
        self.manager.append_streamed(self.task_id, [{"code": "after"}])
        task = self.manager.get_task(self.task_id)
        self.assertEqual([item["code"] for item in task.streamed], ["before"])


if __name__ == "__main__":
    unittest.main()
