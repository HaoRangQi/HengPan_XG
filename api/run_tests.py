"""Run backend tests with an isolated task-cache root, never production journals."""
import os
import tempfile
import unittest

def main():
    with tempfile.TemporaryDirectory(prefix='hengpan-tests-') as directory:
        os.environ['HENGPAN_TASK_CACHE_ROOT'] = directory
        suite = unittest.defaultTestLoader.discover('api', pattern='test_*.py')
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
