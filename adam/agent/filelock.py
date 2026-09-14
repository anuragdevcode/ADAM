"""Cross-platform advisory file locking for the heavy worker coordinator.

POSIX uses ``fcntl.flock``; Windows has no ``fcntl`` so ``msvcrt.locking`` is
used on the first byte of the file instead. Both raise ``OSError`` (a
``BlockingIOError`` on POSIX) when another process already holds the lock.
"""

import os
from typing import IO

if os.name == "nt":
    import msvcrt

    def try_lock_exclusive(fh: IO) -> None:
        """Take a non-blocking exclusive lock; raise ``OSError`` if held elsewhere."""
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def unlock(fh: IO) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def try_lock_exclusive(fh: IO) -> None:
        """Take a non-blocking exclusive lock; raise ``BlockingIOError`` if held elsewhere."""
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def unlock(fh: IO) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
