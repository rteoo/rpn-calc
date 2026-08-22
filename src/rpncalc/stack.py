"""The HP 50g data stack: level 1 is the top, unbounded like the real machine.

Backed by a plain list with index 0 as level 1 - the opposite order from a
typical Python stack idiom (`list.append`/`pop` at the end), because level
numbering is user-visible (via PICK, ROLL, the stack display) and matching it
directly avoids an off-by-one translation at every call site.
"""

from __future__ import annotations


class StackError(Exception):
    """Raised on stack underflow. The 50g never consumes arguments on error,
    so every method here validates depth *before* mutating anything.
    """


class RpnStack:
    def __init__(self) -> None:
        self._levels: list[float] = []

    @property
    def depth(self) -> int:
        return len(self._levels)

    def _require(self, n: int) -> None:
        if self.depth < n:
            raise StackError("Too Few Arguments")

    def push(self, v: float) -> None:
        self._levels.insert(0, v)

    def pop(self) -> float:
        self._require(1)
        return self._levels.pop(0)

    def peek(self, level: int = 1) -> float:
        self._require(level)
        return self._levels[level - 1]

    def drop(self) -> None:
        self._require(1)
        del self._levels[0]

    def dropn(self, n: int) -> None:
        self._require(n)
        del self._levels[:n]

    def swap(self) -> None:
        self._require(2)
        self._levels[0], self._levels[1] = self._levels[1], self._levels[0]

    def dup(self) -> None:
        self._require(1)
        self._levels.insert(0, self._levels[0])

    def dupn(self, n: int) -> None:
        """Duplicate the top n levels as a group, preserving their order."""
        self._require(n)
        block = list(self._levels[:n])
        self._levels[:0] = block

    def over(self) -> None:
        """Copy level 2 to level 1."""
        self._require(2)
        self._levels.insert(0, self._levels[1])

    def rot(self) -> None:
        """Level 3 -> level 1, level 1 -> level 2, level 2 -> level 3."""
        self._require(3)
        a, b, c = self._levels[0], self._levels[1], self._levels[2]
        self._levels[0], self._levels[1], self._levels[2] = c, a, b

    def unrot(self) -> None:
        """Inverse of rot: level 1 -> level 3, level 2 -> level 1, level 3 -> level 2."""
        self._require(3)
        a, b, c = self._levels[0], self._levels[1], self._levels[2]
        self._levels[0], self._levels[1], self._levels[2] = b, c, a

    def roll(self, n: int) -> None:
        """Move level n to level 1, shifting levels 1..n-1 up by one."""
        self._require(n)
        item = self._levels.pop(n - 1)
        self._levels.insert(0, item)

    def rolld(self, n: int) -> None:
        """Inverse of roll: move level 1 down to level n."""
        self._require(n)
        item = self._levels.pop(0)
        self._levels.insert(n - 1, item)

    def pick(self, n: int) -> None:
        """Copy level n to level 1."""
        self._require(n)
        self._levels.insert(0, self._levels[n - 1])

    def clear(self) -> None:
        self._levels.clear()

    def to_list(self) -> list[float]:
        """Level 1 first."""
        return list(self._levels)

    def depth_command(self) -> None:
        """The 50g's DEPTH: pushes the current depth as a new level 1."""
        self._levels.insert(0, float(len(self._levels)))
