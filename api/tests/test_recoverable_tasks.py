import unittest
from api.tests import test_task_asgi_review as support
from api.task_manager import TaskExtras, TaskStatus, task_manager

class RecoverableTasksTest(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = support.TaskAsgiReviewTests.asyncSetUp
    async def test_unsaved_task_is_discoverable_after_restart(self):
        ident=task_manager.create_task()
        TaskExtras('platform_a')[ident]={'params': {'frequency':'60'}}
        task_manager.append_streamed(ident,[{'code':'sh.600000','kline_data':[{'close':10}]}])
        task_manager.update_task(ident,status=TaskStatus.FAILED,message='interrupted')
        response=await support.AsgiClient().get('/api/tasks/recoverable')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['tasks'][0]['task_id'],ident)
        self.assertEqual(response.json()['tasks'][0]['found'],1)
