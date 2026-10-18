import logging

# systemd and journald read a "<N>" syslog priority at the start of a line
_PRIORITIES = {
    logging.CRITICAL: 2,
    logging.ERROR: 3,
    logging.WARNING: 4,
    logging.INFO: 6,
    logging.DEBUG: 7,
}


class PriorityFormatter(logging.Formatter):
    """Prefixes every output line with its systemd priority when enabled.

    Prefixing each line keeps the lines of a traceback at the level of the
    record, instead of falling back to the default priority.
    """

    def __init__(self, *args, prefix=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.prefix = prefix

    def format(self, record):
        text = super().format(record)
        if not self.prefix:
            return text
        floor = max((lv for lv in _PRIORITIES if lv <= record.levelno), default=logging.DEBUG)
        priority = _PRIORITIES[floor]
        return "\n".join(f"<{priority}>{line}" for line in text.splitlines())
