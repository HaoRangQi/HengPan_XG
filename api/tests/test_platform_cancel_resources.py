import threading
import time
import unittest
from concurrent.futures import Future
from unittest.mock import Mock,patch
from api.platform_scanner import _iter_bounded_futures,_ScanExecutorContext

class PoolResourcesTests(unittest.TestCase):
    def test_cancel_does_not_wait_for_pending_io(self):
        future=Future(); timer=threading.Timer(.8,lambda:future.set_result(None) if not future.cancelled() else None)
        timer.start(); start=time.monotonic()
        try:
            list(_iter_bounded_futures(Mock(),[{}],lambda stock:future,lambda:time.monotonic()-start>.02,1))
            self.assertLess(time.monotonic()-start,.5)
        finally:timer.cancel();timer.join()
    def test_cancelled_process_pool_forcibly_reclaims_workers(self):
        pool=Mock(); pool._scan_cancelled=True
        with patch('api.process_pool.close_process_pool') as close:
            context=_ScanExecutorContext(Mock(),1);context.executor=pool
            context.__exit__(None,None,None)
            close.assert_called_once_with(pool,force=True)
