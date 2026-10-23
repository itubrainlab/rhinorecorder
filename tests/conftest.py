import os
import socket

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def settings(tmp_path):
    """Default settings recording into tmp_path, trigger on a free port."""
    from rhino_recorder.settings import Settings

    s = Settings()
    for logger in s.recording.loggers().values():
        logger.folder = str(tmp_path)
    s.network.trigger_in.port = free_udp_port()
    # OSCAR cleans the EEG the tests measure; tests that want it say so.
    s.display.oscar = False
    return s
