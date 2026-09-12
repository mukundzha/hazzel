import os
import threading
import time


def caching_enabled():
    return "PYTEST_CURRENT_TEST" not in os.environ


class TTLCache:
    def __init__(self, maxsize=128, ttl=600.0):
        self._maxsize = max(1, maxsize)
        self._ttl = max(1.0, ttl)
        self._lock = threading.Lock()
        self._data = {}

    def get(self, key):
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires, value = entry
            if now >= expires:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key, value):
        with self._lock:
            while len(self._data) >= self._maxsize:
                oldest = min(self._data, key=lambda k: self._data[k][0])
                del self._data[oldest]
            self._data[key] = (time.monotonic() + self._ttl, value)

    def clear(self):
        with self._lock:
            self._data.clear()


WEB = TTLCache(maxsize=128, ttl=600.0)
FETCH = TTLCache(maxsize=128, ttl=600.0)
LIST = TTLCache(maxsize=256, ttl=10.0)
SEARCH = TTLCache(maxsize=128, ttl=20.0)
NAME_INDEX = TTLCache(maxsize=4, ttl=30.0)
REPO = TTLCache(maxsize=4, ttl=10.0)


def invalidate_fs():
    LIST.clear()
    SEARCH.clear()
    NAME_INDEX.clear()
