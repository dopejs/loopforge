from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from types import TracebackType
from typing import Self

from .errors import StateConflictError


class ProjectLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._descriptor: int | None = None

    def __enter__(self) -> Self:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            self._acquire(descriptor)
        except OSError as exc:
            os.close(descriptor)
            raise StateConflictError(
                "Another Loopforge mutation holds the project lock.",
                "PROJECT_LOCKED",
                {"lock_path": str(self.path)},
            ) from exc

        metadata = json.dumps(
            {
                "hostname": socket.gethostname(),
                "pid": os.getpid(),
            },
            sort_keys=True,
        ).encode("utf-8")
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.write(descriptor, metadata)
        os.fsync(descriptor)
        self._descriptor = descriptor
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._descriptor is None:
            return
        try:
            self._release(self._descriptor)
        finally:
            os.close(self._descriptor)
            self._descriptor = None

    @staticmethod
    def _acquire(descriptor: int) -> None:
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            return

        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _release(descriptor: int) -> None:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            return

        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)
