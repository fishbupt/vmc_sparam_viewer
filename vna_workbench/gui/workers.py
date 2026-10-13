"""Shared QThread workers preserving existing signal contracts."""

import traceback
from PyQt6.QtCore import QThread, pyqtSignal

class Task(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str, str)
    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args
    def run(self):
        try:
            self.done.emit(self.fn(*self.args))
        except Exception as e:
            self.failed.emit(str(e), traceback.format_exc())

class Worker(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str, str)
    def __init__(self, fn, args, parent=None):
        super().__init__(parent); self.fn, self.args = fn, args
    def run(self):
        try: self.done.emit(self.fn(*self.args))
        except Exception as e: self.failed.emit(str(e), traceback.format_exc())

class Work(QThread):
    done=pyqtSignal(object)
    failed=pyqtSignal(str)
    def __init__(self,fn,*args):
        super().__init__(); self.fn=fn; self.args=args
    def run(self):
        try: self.done.emit(self.fn(*self.args))
        except Exception: self.failed.emit(traceback.format_exc())
