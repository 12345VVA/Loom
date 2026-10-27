"""文件日志队列化测试（评审 F3）。

日志此前全同步写盘且跑在事件循环线程上，磁盘抖动直接表现为全站延迟尖刺。
修复后文件 handler 挂 QueueListener 后台线程：有界队列（5000）满时丢弃计数、
stop() 加固（哨兵腾位重试 + 关闭 handler）。控制台保持同步。
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core import logging as app_logging  # noqa: E402
from app.core.logging import _stop_file_log_listener, configure_logging  # noqa: E402

# listener 统一经 app_logging 模块属性访问：from-import 会绑死导入时的 None，
# configure_logging 重新赋值模块全局后看不到新 listener



def _make_record(msg: str) -> logging.LogRecord:
    return logging.LogRecord("test.queue", logging.INFO, __file__, 1, msg, None, None)


class DropCountingQueueHandlerTests(unittest.TestCase):
    def test_full_queue_drops_and_counts(self):
        handler = app_logging._DropCountingQueueHandler(maxsize=1)
        handler.emit(_make_record("first"))
        handler.emit(_make_record("second"))  # 队列已满：丢弃且不抛
        self.assertEqual(handler.dropped, 1)
        self.assertEqual(handler.queue.qsize(), 1)

    def test_queue_not_full_passes_through(self):
        handler = app_logging._DropCountingQueueHandler(maxsize=8)
        handler.emit(_make_record("ok"))
        self.assertEqual(handler.dropped, 0)
        self.assertEqual(handler.queue.qsize(), 1)


class FileQueueListenerTests(unittest.TestCase):
    """端到端：configure 后日志经队列由后台线程落盘（stop 含 flush）。"""

    def setUp(self) -> None:
        root = logging.getLogger()
        self._root = root
        self._saved_handlers = root.handlers[:]
        self._saved_level = root.level
        uv_names = ("uvicorn", "uvicorn.error", "uvicorn.access")
        self._uv_loggers = [logging.getLogger(n) for n in uv_names]
        self._uv_saved = [(lg.handlers[:], lg.propagate, lg.level) for lg in self._uv_loggers]

    def tearDown(self) -> None:
        # configure_logging 换掉过 root handlers，且文件句柄由 listener 持有
        # （Windows 下不关会挂死 TemporaryDirectory 清理）
        _stop_file_log_listener()
        self._root.handlers[:] = self._saved_handlers
        self._root.setLevel(self._saved_level)
        for lg, (handlers, propagate, level) in zip(self._uv_loggers, self._uv_saved):
            lg.handlers[:] = handlers
            lg.propagate = propagate
            lg.setLevel(level)

    def test_records_reach_file_via_queue_listener(self):
        with tempfile.TemporaryDirectory() as log_dir:
            configure_logging(log_level="INFO", log_dir=log_dir)
            self.assertIsNotNone(app_logging._file_log_listener)
            logging.getLogger("test.queue.file").info("hello-queue-listener")
            app_logging._file_log_listener.stop()
            content = (Path(log_dir) / "app.log").read_text(encoding="utf-8")
            self.assertIn("hello-queue-listener", content)

    def test_error_file_receives_only_error_level(self):
        with tempfile.TemporaryDirectory() as log_dir:
            configure_logging(log_level="INFO", log_dir=log_dir)
            logger = logging.getLogger("test.queue.file")
            logger.info("plain-info")
            logger.error("boom-error")
            app_logging._file_log_listener.stop()
            error_log = (Path(log_dir) / "error.log").read_text(encoding="utf-8")
            self.assertIn("boom-error", error_log)
            self.assertNotIn("plain-info", error_log)

    def test_stop_is_idempotent(self):
        with tempfile.TemporaryDirectory() as log_dir:
            configure_logging(log_level="INFO", log_dir=log_dir)
            _stop_file_log_listener()
            _stop_file_log_listener()  # 二次调用不炸（atexit 与 tearDown 可能都触发）
            self.assertIsNone(app_logging._file_log_listener)


if __name__ == "__main__":
    unittest.main()
