import os
from pathlib import Path


def read_last_lines(path: Path, n: int, block_size: int = 8192) -> list[str]:
    """Return the last ``n`` lines of a file without loading the whole file into memory.

    The file is read backwards in ``block_size`` chunks. Missing or unreadable
    files yield an empty list.
    """
    if n <= 0:
        return []
    try:
        with Path(path).open("rb") as f:
            f.seek(0, os.SEEK_END)
            position = f.tell()
            newlines = 0
            blocks: list[bytes] = []
            while position > 0 and newlines <= n:
                read_size = min(block_size, position)
                position -= read_size
                f.seek(position)
                block = f.read(read_size)
                newlines += block.count(b"\n")
                blocks.append(block)
    except OSError:
        return []
    data = b"".join(reversed(blocks))
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[-n:]


class LogTailer:
    """Incrementally read a log file that may grow, shrink, or be replaced."""

    CHUNK_SIZE = 64 * 1024
    MAX_BYTES_PER_POLL = 256 * 1024
    MAX_LINE_CHARS = 64 * 1024

    def __init__(self, path: Path):
        self.path = Path(path)
        self.offset = 0
        self.inode = None
        self.partial = ""

    def initial_lines(self, n: int = 100) -> list[str]:
        """Return the last ``n`` lines and position the tailer at the current EOF."""
        try:
            stat = self.path.stat()
        except OSError:
            self.inode = None
            self.offset = 0
            self.partial = ""
            return []
        self.inode = stat.st_ino
        self.offset = stat.st_size
        self.partial = ""
        return read_last_lines(self.path, n)

    def poll(self) -> list[str]:
        """Return only the complete lines appended since the previous call."""
        try:
            stat = self.path.stat()
        except OSError:
            return []
        if stat.st_ino != self.inode or stat.st_size < self.offset:
            # File was replaced or truncated/cleared: start over.
            self.offset = 0
            self.partial = ""
            self.inode = stat.st_ino
        lines: list[str] = []
        remaining = self.MAX_BYTES_PER_POLL
        try:
            with self.path.open("rb") as f:
                f.seek(self.offset)
                while remaining > 0:
                    chunk = f.read(min(self.CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    self.offset += len(chunk)
                    text = self.partial + chunk.decode("utf-8", errors="replace")
                    parts = text.split("\n")
                    self.partial = parts.pop()
                    if len(self.partial) > self.MAX_LINE_CHARS:
                        # Pathological newline-free output: flush a bounded line instead of growing forever.
                        lines.append(self.partial[: self.MAX_LINE_CHARS] + " ...[truncated]")
                        self.partial = ""
                    lines.extend(part.rstrip("\r") for part in parts)
        except OSError:
            return []
        return lines
