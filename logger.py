"""Daily application log (log/pipitrek_YYYY-MM-DD.log).

setup_logging() routes the `logging` module, stdout/stderr (so existing print() calls)
and uncaught exceptions (main and worker threads) into the dated file, keeps a copy on
the original console streams (journalctl) and deletes files older than the retention limit.
get_log() reads a day's file incrementally by line number, like the task log.
"""
import datetime
import glob
import logging
import os
import sys
import threading
import traceback

LOG_DIR = "log"
LOG_PREFIX = "pipitrek_"
RETENTION_DAYS = 30

logger = logging.getLogger("pipitrek")

_log_index: dict[str, list[int]] = {}
_index_lock = threading.RLock()


def _log_path(day: str) -> str:
    return os.path.join(LOG_DIR, f"{LOG_PREFIX}{day}.log")


def log():
    return logger

def delete_old_logs(prefix: str = LOG_PREFIX, retention_days: int = RETENTION_DAYS):
    cutoff = (datetime.date.today() - datetime.timedelta(days=retention_days)).isoformat()
    for path in glob.glob(os.path.join(LOG_DIR, f"{prefix}*.log")):
        day = os.path.basename(path)[len(prefix):-len(".log")]
        if day < cutoff:  # ISO dates sort lexicographically
            try:
                os.remove(path)
            except OSError:
                continue
            if prefix == LOG_PREFIX:
                with _index_lock:
                    _log_index.pop(day, None)


class DailyFileHandler(logging.Handler):
    """Writes to log/<prefix><today>.log, switching file (and pruning old ones) at midnight."""

    def __init__(self, prefix: str = LOG_PREFIX):
        super().__init__()
        self._prefix = prefix
        self._day = None
        self._file = None

    def emit(self, record):
        try:
            day = datetime.date.today().isoformat()
            if day != self._day:
                self._rollover(day)
            self._file.write(self.format(record) + "\n")
            self._file.flush()
        except Exception:
            # Never log from here (would recurse through the redirected stderr).
            try:
                sys.__stderr__.write("logger: failed to write log record\n")
            except Exception:
                pass

    def _rollover(self, day):
        if self._file:
            self._file.close()
        os.makedirs(LOG_DIR, exist_ok=True)
        self._file = open(os.path.join(LOG_DIR, f"{self._prefix}{day}.log"), "a", encoding="utf-8")
        self._day = day
        delete_old_logs(self._prefix)


_task_logger = None
_task_logger_lock = threading.Lock()


def get_task_logger() -> logging.Logger:
    """Logger for log/task_YYYY-MM-DD.log, lines formatted as "timestamp, task name, message".
    Independent of the root logger (no propagation), so task entries stay out of the app log."""
    global _task_logger
    with _task_logger_lock:
        if _task_logger is None:
            task_logger = logging.getLogger("pipitrek.tasks")
            task_logger.setLevel(logging.INFO)
            task_logger.propagate = False
            handler = DailyFileHandler("task_")
            handler.setFormatter(logging.Formatter("%(asctime)s, %(task)s, %(message)s", "%Y-%m-%d %H:%M:%S"))
            task_logger.addHandler(handler)
            _task_logger = task_logger
    return _task_logger


class _StreamToLogger:
    """File-like object that logs complete lines written to it (replacement for sys.stdout/stderr)."""

    def __init__(self, level):
        self._level = level
        self._buffer = ""
        self._lock = threading.Lock()
        self._local = threading.local()

    def write(self, text):
        if not text:
            return 0
        if getattr(self._local, "busy", False):
            return len(text)  # re-entrant write from inside logging
        self._local.busy = True
        try:
            with self._lock:
                self._buffer += text
                *lines, self._buffer = self._buffer.split("\n")
            for line in lines:
                logger.log(self._level, line.rstrip("\r"))
        finally:
            self._local.busy = False
        return len(text)

    def flush(self):
        pass  # partial lines stay buffered until their newline arrives

    def isatty(self):
        return False

    def writable(self):
        return True


def setup_logging(console: bool = True, level=logging.INFO):
    """Call once at startup, before other modules start printing."""
    logging.raiseExceptions = False
    fmt = logging.Formatter("%(asctime)s, %(levelname)s, %(message)s", "%Y-%m-%d %H:%M:%S")

    handlers = [DailyFileHandler()]
    if console and sys.__stdout__ is not None:
        handlers.append(logging.StreamHandler(sys.__stdout__))
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    for handler in handlers:
        handler.setFormatter(fmt)
        root.addHandler(handler)

    sys.stdout = _StreamToLogger(logging.INFO)
    sys.stderr = _StreamToLogger(logging.ERROR)

    def log_uncaught(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logger.critical("Uncaught exception:\n" + "".join(traceback.format_exception(exc_type, exc, tb)).rstrip())

    def log_uncaught_thread(args):
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread else "?"
        logger.critical(f"Uncaught exception in thread {name}:\n"
                        + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)).rstrip())

    sys.excepthook = log_uncaught
    threading.excepthook = log_uncaught_thread
    delete_old_logs()


def read_log_lines(path: str, lineindex: list[int], from_line: int = 0) -> list[str]:
    """Return complete lines from `from_line` on. `lineindex[i]` caches the byte offset of line i.
    The caller must serialize access to `lineindex`."""
    from_line = max(0, from_line)
    lines = []
    try:
        log_file = open(path, "rb")
    except FileNotFoundError:
        return lines
    with log_file:
        # Extend the index until it covers from_line (or the file ends).
        if lineindex:
            log_file.seek(lineindex[-1])
            log_file.readline()
        pos = log_file.tell()
        while len(lineindex) <= from_line:
            line = log_file.readline()
            # No trailing "\n" only happens at EOF: b"" or a last line still being written.
            # Leave it unindexed so a later call returns it complete.
            if not line.endswith(b"\n"):
                break
            lineindex.append(pos)
            pos = log_file.tell()
        if from_line >= len(lineindex):
            return lines
        log_file.seek(lineindex[from_line])
        while True:
            line = log_file.readline()
            if not line.endswith(b"\n"):  # EOF / incomplete last line, as above
                break
            if len(lineindex) <= from_line + len(lines):
                lineindex.append(log_file.tell() - len(line))
            lines.append(line.decode("utf-8", errors="replace"))
    return lines


def get_log(day: str | None = None, from_line: int = 0) -> list[str]:
    if day is None:
        day = datetime.date.today().isoformat()
    datetime.datetime.strptime(day, "%Y-%m-%d")  # also rejects path tricks
    with _index_lock:
        return read_log_lines(_log_path(day), _log_index.setdefault(day, []), from_line)
