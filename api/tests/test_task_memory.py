import gc
import tempfile
import unittest
from unittest.mock import patch
from api.task_manager import Task, TaskManager, TaskStatus

class TaskMemoryTests(unittest.TestCase):
    def test_completed_filter_does_not_restore_rejected_candidates(self):
        task=Task('filter')
        task.append_streamed([{'code':'A'},{'code':'B'}])
        task.update(status=TaskStatus.COMPLETED,result=[{'code':'A'}])
        self.assertEqual([x['code'] for x in task.result],['A'])

    def test_compact_status_pages_without_kline(self):
        task=Task('pages')
        rows=[{'code':str(i),'kline_data':[{'close':i}]*1000} for i in range(230)]
        task.append_streamed(rows)
        payload=task.to_dict(compact=True)
        self.assertEqual(len(payload['new_results']),100)
        self.assertEqual(payload['cursor'],100)
        self.assertTrue(payload['has_more'])
        self.assertEqual(payload['new_results'][0]['kline_data'],[])
        self.assertIn('kline_url',payload['new_results'][0])
        self.assertEqual(len(task.kline('0')),1000)
        self.assertFalse(isinstance(task.streamed,list))
        task.close()

    def test_thin_change_uses_fraction_for_percent_formatter(self):
        task=Task('ratio')
        self.addCleanup(task.close)
        task.append_streamed([{'code':'A','kline_data':[{'close':100},{'close':101}]}])
        self.assertAlmostEqual(task.to_dict(compact=True)['new_results'][0]['last_change_ratio'],0.01)

    def test_terminal_pages_are_authoritative(self):
        task=Task('terminal')
        task.append_streamed([{'code':'Z'},{'code':'A'}])
        task.update(status=TaskStatus.COMPLETED,result=[{'code':'A'}])
        self.assertEqual(task.result_page()['results'][0]['code'],'A')
        self.assertEqual(task.result_page()['total'],1)
        task.close()

    def test_manager_does_not_evict_unsaved_history(self):
        m=TaskManager(); ident=m.create_task(); task=m.get_task(ident)
        task.history_required=True
        task.update(status=TaskStatus.COMPLETED,result=[{'code':'A'}])
        task.completed_at=1
        m.clean_old_tasks(max_age_seconds=1)
        self.assertIs(m.get_task(ident),task)
        m.mark_persisted(ident)
        m.clean_old_tasks(max_age_seconds=1)
        self.assertIsNone(m.get_task(ident))
