"""Console progress display for the command line (stdlib only).

On a terminal it draws one bar that overwrites itself with ``\\r`` (no ANSI codes, so it
works in every Windows console). When stderr is redirected to a file or another program it
writes a plain line at the start of each stage, at every 10 % and at the end, so logs stay
readable.
"""

from __future__ import annotations

import shutil
import sys
import time
from collections.abc import Callable
from typing import TextIO

LABELS = {
    "scan": "Scanning folders",
    "exif": "Reading GPS",
    "plan": "Checking captures",
    "copy": "Writing files",
    "filter": "Filtering",
}
# Shown after the count when the total is not known in advance.
UNITS = {"scan": " files"}

BAR_WIDTH = 24
REDRAW_SECONDS = 0.1  # at most ~10 redraws per second on a terminal
LOG_STEP_PERCENT = 10  # one log line per 10 % when not on a terminal
LOG_UNKNOWN_SECONDS = 10.0  # one log line per 10 s when the total is unknown
ETA_AFTER_SECONDS = 2.0  # the first seconds say little about the rate


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds + 0.5))
    hours, rest = divmod(seconds, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}"


class ConsoleProgress:
    """A ``progress(stage, done, total)`` callback that shows progress on stderr."""

    def __init__(
        self,
        stream: TextIO | None = None,
        clock: Callable[[], float] = time.monotonic,
        is_terminal: bool | None = None,
    ) -> None:
        self.stream = sys.stderr if stream is None else stream
        self.clock = clock
        if is_terminal is None:
            try:
                is_terminal = self.stream.isatty()
            except (AttributeError, ValueError):
                is_terminal = False
        self.is_terminal = is_terminal
        self.stage: str | None = None
        self.started = 0.0
        self.last_draw = float("-inf")
        self.last_step = -1
        self.line_open = False
        self.last: tuple[int, int | None] = (0, None)

    def __call__(self, stage: str, done: int, total: int | None) -> None:
        now = self.clock()
        if stage != self.stage:
            self._end_stage()
            self.stage, self.started = stage, now
            self.last_draw, self.last_step = float("-inf"), -1
            if not self.is_terminal:
                self._log_line(f"{self._label()}: started")
        self.last = (done, total)
        finished = total is not None and done >= total
        if self.is_terminal:
            if finished or now - self.last_draw >= REDRAW_SECONDS:
                self._draw(done, total, now)
                self.last_draw = now
        elif total is not None:
            step = min(100, done * 100 // total if total else 100) // LOG_STEP_PERCENT
            if step > self.last_step and done > 0:
                self.last_step = step
                self._log_line(self._log_text(done, total, now))
        elif done > 0 and now - self.last_draw >= LOG_UNKNOWN_SECONDS:
            self.last_draw = now
            self._log_line(self._log_text(done, total, now))

    def finish(self) -> None:
        """End the current line; call before printing anything else."""
        self._end_stage()
        self.stage = None

    # --- internals -------------------------------------------------------------------

    def _label(self) -> str:
        assert self.stage is not None
        return LABELS.get(self.stage, self.stage)

    def _unit(self) -> str:
        return UNITS.get(self.stage or "", "")

    def _end_stage(self) -> None:
        if self.stage is None:
            return
        done, total = self.last
        if self.is_terminal:
            if self.line_open:
                self._draw(done, total, self.clock())
                self.stream.write("\n")
                self.stream.flush()
                self.line_open = False
        elif total is None:  # the 10 % lines already covered a known total
            self._log_line(self._log_text(done, total, self.clock()))

    def _log_text(self, done: int, total: int | None, now: float) -> str:
        elapsed = format_duration(now - self.started)
        if total is None:
            return f"{self._label()}: {done:,}{self._unit()}, {elapsed} elapsed"
        percent = done * 100 // total if total else 100
        return f"{self._label()}: {percent}% ({done:,}/{total:,}), {elapsed} elapsed"

    def _log_line(self, text: str) -> None:
        self.stream.write(text + "\n")
        self.stream.flush()

    def _draw(self, done: int, total: int | None, now: float) -> None:
        elapsed = now - self.started
        if total is None:
            text = f"{self._label()}: {done:,}{self._unit()}  {format_duration(elapsed)}"
        else:
            fraction = min(1.0, done / total) if total else 1.0
            filled = int(BAR_WIDTH * fraction)
            bar = "#" * filled + "-" * (BAR_WIDTH - filled)
            if done >= total:
                tail = format_duration(elapsed)
            elif elapsed >= ETA_AFTER_SECONDS and fraction >= 0.01:
                tail = "ETA " + format_duration(elapsed / fraction - elapsed)
            else:
                tail = "ETA --:--"
            text = f"{self._label()}  [{bar}] {int(fraction * 100):3d}%  {done:,}/{total:,}  {tail}"
        # Writing into the last column makes some consoles (Windows) wrap the line.
        width = max(20, shutil.get_terminal_size((80, 24)).columns - 1)
        self.stream.write("\r" + text[:width].ljust(width))
        self.stream.flush()
        self.line_open = True
