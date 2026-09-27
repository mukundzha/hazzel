import os
import threading
import time
from collections import OrderedDict


def caching_enabled():
    return "PYTEST_CURRENT_TEST" not in os.environ


class TTLCache:
    def __init__(self, maxsize=128, ttl=600.0):
        self._maxsize = max(1, maxsize)
        self._ttl = max(1.0, ttl)
        self._lock = threading.Lock()
        self._data = OrderedDict()

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
            self._data.move_to_end(key)
            return value

    def set(self, key, value):
        with self._lock:
            self._data.pop(key, None)
            if len(self._data) >= self._maxsize:
                self._data.popitem(last=False)
            self._data[key] = (time.monotonic() + self._ttl, value)

    def clear(self):
        with self._lock:
            self._data.clear()


WEB = TTLCache(maxsize=128, ttl=600.0)
FETCH = TTLCache(maxsize=128, ttl=600.0)
LIST = TTLCache(maxsize=256, ttl=10.0)
SEARCH = TTLCache(maxsize=128, ttl=20.0)
GLOB = TTLCache(maxsize=128, ttl=20.0)
NAME_INDEX = TTLCache(maxsize=4, ttl=30.0)
REPO = TTLCache(maxsize=4, ttl=10.0)


def invalidate_fs():
    LIST.clear()
    SEARCH.clear()
    GLOB.clear()
    NAME_INDEX.clear()
