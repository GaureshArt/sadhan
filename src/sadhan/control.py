import threading


_cancel = threading.Event()
cancelled = _cancel


class CancelRequested(Exception):
    pass


def new_run():
    global cancelled
    cancelled = threading.Event()
    return cancelled


def is_cancelled():
    return cancelled.is_set()