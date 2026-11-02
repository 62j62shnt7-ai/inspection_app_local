"""Emulate Windows' writable-handle requirement for file-buffer flushing."""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
from unittest.mock import patch


@contextmanager
def windows_flush_requirement():
    original_open = Path.open
    original_fsync = os.fsync
    handles = {}

    def tracked_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        handles[stream.fileno()] = stream
        return stream

    def windows_fsync(fd):
        stream = handles.get(fd)
        if stream is not None and not stream.closed and not stream.writable():
            raise OSError(errno.EBADF, 'Windows flush requires a writable file handle')
        return original_fsync(fd)

    with patch.object(Path, 'open', tracked_open), patch('os.fsync', windows_fsync):
        yield
