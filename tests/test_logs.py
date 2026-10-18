import logging

from audiobook_notifier.logs import PriorityFormatter


def _record(level, msg="hello", exc_info=None):
    return logging.LogRecord("x", level, __file__, 1, msg, None, exc_info)


def test_disabled_leaves_output_untouched():
    fmt = PriorityFormatter("%(message)s", prefix=False)
    assert fmt.format(_record(logging.ERROR)) == "hello"


def test_levels_map_to_syslog_priorities():
    fmt = PriorityFormatter("%(message)s", prefix=True)
    assert fmt.format(_record(logging.INFO)) == "<6>hello"
    assert fmt.format(_record(logging.WARNING)) == "<4>hello"
    assert fmt.format(_record(logging.ERROR)) == "<3>hello"
    assert fmt.format(_record(logging.CRITICAL)) == "<2>hello"
    assert fmt.format(_record(logging.DEBUG)) == "<7>hello"


def test_every_traceback_line_is_prefixed():
    fmt = PriorityFormatter("%(message)s", prefix=True)
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        out = fmt.format(_record(logging.ERROR, exc_info=sys.exc_info()))
    assert len(out.splitlines()) > 1
    assert all(line.startswith("<3>") for line in out.splitlines())
