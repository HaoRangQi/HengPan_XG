"""Small, deterministic shutdown helper for ProcessPoolExecutor users."""
import time


def close_process_pool(executor, pending=(), force=False, timeout=2.0):
    """Close a process pool and prevent cancelled workers from becoming orphans."""
    futures = list(pending)
    for future in futures:
        future.cancel()

    if not force:
        executor.shutdown(wait=True, cancel_futures=True)
        return

    processes = list((getattr(executor, "_processes", None) or {}).values())
    for process in processes:
        if process.is_alive():
            process.terminate()

    deadline = time.monotonic() + timeout
    for process in processes:
        remaining = max(0.0, deadline - time.monotonic())
        process.join(remaining)
    for process in processes:
        if process.is_alive():
            process.kill()
            process.join()

    executor.shutdown(wait=False, cancel_futures=True)
