import os
import signal

_ANSI_OK = None


def is_windows():
    return os.name == "nt"


def enable_ansi():
    global _ANSI_OK
    if _ANSI_OK is not None:
        return _ANSI_OK
    _ANSI_OK = True
    if not is_windows():
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        _ANSI_OK = False
    return _ANSI_OK


def popen_kwargs():
    if is_windows():
        return {}
    return {"start_new_session": True}


def kill_proc(proc):
    if not is_windows():
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            return
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass
