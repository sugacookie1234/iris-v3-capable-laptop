"""Bounded pipe reads on both Windows and POSIX test hosts."""
import queue
import threading


def read_line(stream, timeout=5):
    result = queue.Queue()
    threading.Thread(target=lambda: result.put(stream.readline()), daemon=True).start()
    return result.get(timeout=timeout)
