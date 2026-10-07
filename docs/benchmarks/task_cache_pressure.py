"""Bounded task-cache pressure probe; run as module from project root.

Completed tasks have no external-history obligation, isolating cache retention.
Each hit is generated, cached and released before generating the next hit.
This measures traced Python allocations, not OS RSS or SQLite page-cache memory.
"""
import argparse
import gc
import json
import tempfile
import time
import tracemalloc
from pathlib import Path
from unittest.mock import patch
from api.task_manager import TaskStatus, task_manager


def run(tasks=20, hits=200, bars=1440):
    samples = []
    with tempfile.TemporaryDirectory(prefix='task-pressure-') as root, \
         patch('api.task_results.ROOT', root), patch.object(task_manager, '_tasks', {}):
        gc.collect()
        tracemalloc.start()
        started = time.monotonic()
        for number in range(tasks):
            ident = task_manager.create_task()
            for hit in range(hits):
                rows = [{'date': f'2026-09-{1 + i // 24:02d} {i % 24:02d}:00:00',
                         'open': 100., 'high': 101., 'low': 99., 'close': 100. + (i % 10) * .01,
                         'volume': 1000.} for i in range(bars)]
                task_manager.append_streamed(ident, [{'code': str(hit), 'kline_data': rows}])
                del rows
            task_manager.finish_results(ident, [{'code': str(hit)} for hit in range(hits)])
            task_manager.update_task(ident, status=TaskStatus.COMPLETED)
            task_manager.clean_old_tasks(max_completed=8)
            task = task_manager.get_task(ident)
            compact = task.result_page(0, 100)
            page_bytes = len(json.dumps(compact).encode())
            del compact
            gc.collect()
            current, peak = tracemalloc.get_traced_memory()
            sample = {'task': number + 1, 'retained_python_bytes': current, 'peak_python_bytes': peak,
                      'live_tasks': len(task_manager._tasks),
                      'cache_directories': len(list(Path(root).glob('task-*'))),
                      'cache_bytes': sum(path.stat().st_size for path in Path(root).glob('task-*/*.db')),
                      'compact_page_bytes': page_bytes, 'elapsed_seconds': round(time.monotonic() - started, 2)}
            samples.append(sample)
            print(json.dumps(sample), flush=True)
        # Compare the same 100-hit page only once; it is intentionally expensive.
        tracemalloc.reset_peak()
        full_page = task.result.page(0, min(hits, 100))
        full_bytes = len(json.dumps(full_page).encode())
        full_peak = tracemalloc.get_traced_memory()[1]
        del full_page
        tracemalloc.stop()
        return {'tasks': tasks, 'hits_per_task': hits, 'bars_per_hit': bars, 'samples': samples,
                'full_page_bytes': full_bytes, 'full_page_peak_python_bytes': full_peak,
                'note': 'Isolated task cache; Python tracemalloc excludes native allocations/RSS; completed tasks are eligible for eviction.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tasks', type=int, default=20)
    parser.add_argument('--hits', type=int, default=200)
    parser.add_argument('--bars', type=int, default=1440)
    parser.add_argument('--output', default='/tmp/task-cache-pressure.json')
    args = parser.parse_args()
    result = run(args.tasks, args.hits, args.bars)
    Path(args.output).write_text(json.dumps(result, indent=2))
