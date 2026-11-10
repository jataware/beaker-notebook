import logging

from tornado.log import LogFormatter

from beaker_notebook.app.base import BaseBeakerApp


def test_app_log_format_with_tornado_formatter():
    app = BaseBeakerApp()
    formatter = LogFormatter(fmt=app.log_format, datefmt=app.log_datefmt, color=False)
    record = logging.LogRecord("beaker", logging.INFO, __file__, 1, "Kernel shutdown: %s", ("id",), None)

    formatted = formatter.format(record)

    assert "[beaker] INFO" in formatted
    assert f".{record.msecs:03.0f} Kernel shutdown: id" in formatted
