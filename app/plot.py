"""From strokes on paper to G-code on the bed."""

import itertools
import math

import numpy as np

from .design import Stroke
from .printer import MAX_MESSAGE_BYTES, Z_SPEED, Chunk
from .settings import Point, Settings

# Room left in each message for the progress marker the runner appends.
MARKER_BYTES = 64


def bounds(strokes: list[Stroke]) -> tuple[float, float, float, float]:
    xs = [x for s in strokes for x, _ in s]
    ys = [y for s in strokes for _, y in s]
    return min(xs), min(ys), max(xs), max(ys)


def place(
    strokes: list[Stroke],
    *,
    paper_w: float,
    paper_h: float,
    margin: float,
    fit: bool,
    align: str = "center",
) -> list[Stroke]:
    """Position strokes on the paper, inside the margins.

    With fit, the drawing is scaled to fill the space; otherwise it keeps its
    size and is only scaled down if it doesn't fit.
    """
    if not strokes:
        return []
    x0, y0, x1, y1 = bounds(strokes)
    w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    room_w, room_h = paper_w - 2 * margin, paper_h - 2 * margin
    scale = min(room_w / w, room_h / h)
    if not fit:
        scale = min(scale, 1.0)
    dx = margin + (room_w - w * scale) / 2
    dy = margin + (room_h - h * scale) / 2
    if align == "top":
        dy = margin
    return [[((x - x0) * scale + dx, (y - y0) * scale + dy) for x, y in s] for s in strokes]


def clip(strokes: list[Stroke], paper_w: float, paper_h: float) -> list[Stroke]:
    """Drop anything off the paper, so the pen never draws on the bed."""
    result: list[Stroke] = []
    for stroke in strokes:
        current: Stroke = []
        for x, y in stroke:
            if 0 <= x <= paper_w and 0 <= y <= paper_h:
                current.append((x, y))
            else:
                if len(current) > 1:
                    result.append(current)
                current = []
        if len(current) > 1:
            result.append(current)
    return result


def order(strokes: list[Stroke]) -> list[Stroke]:
    """Greedy nearest-neighbour ordering, so the pen doesn't zig-zag across the page.

    Strokes can be drawn backwards when that end is closer.
    """
    if len(strokes) < 2:
        return strokes
    starts = np.array([s[0] for s in strokes])
    ends = np.array([s[-1] for s in strokes])
    remaining = np.ones(len(strokes), bool)
    result: list[Stroke] = []
    pos = np.array([0.0, 0.0])
    for _ in range(len(strokes)):
        d_start = np.where(remaining, np.hypot(*(starts - pos).T), np.inf)
        d_end = np.where(remaining, np.hypot(*(ends - pos).T), np.inf)
        i, j = int(d_start.argmin()), int(d_end.argmin())
        if d_start[i] <= d_end[j]:
            stroke = strokes[i]
            remaining[i] = False
        else:
            stroke = strokes[j][::-1]
            remaining[j] = False
        result.append(stroke)
        pos = np.array(stroke[-1])
    return result


def length(strokes: list[Stroke]) -> tuple[float, float]:
    """(drawing, travel) distance in mm, for the strokes in order."""
    draw = travel = 0.0
    pos = (0.0, 0.0)
    for s in strokes:
        travel += math.dist(pos, s[0])
        draw += sum(math.dist(a, b) for a, b in itertools.pairwise(s))
        pos = s[-1]
    return draw, travel


def estimate_seconds(strokes: list[Stroke], settings: Settings) -> float:
    draw, travel = length(strokes)
    lifts = len(strokes) * 2 * (settings.pen_up + settings.pen_pressure) / Z_SPEED * 60
    # Acceleration means real moves are slower than the feed rate suggests,
    # especially lots of short ones; 1.3 is a rough correction.
    return 1.3 * (draw / settings.draw_speed * 60 + travel / settings.travel_speed * 60) + lifts


def paper_to_machine(top_left: Point, bottom_right: Point):
    """Map paper coordinates (mm, y down from the top edge) to bed coordinates."""
    sx = 1 if bottom_right.x >= top_left.x else -1
    sy = 1 if bottom_right.y >= top_left.y else -1

    def convert(x: float, y: float) -> tuple[float, float]:
        return top_left.x + sx * x, top_left.y + sy * y

    return convert


def gcode_chunks(strokes: list[Stroke], settings: Settings) -> list[Chunk]:
    """G-code for the strokes, split into messages small enough for the printer.

    A long stroke can be split across messages: the printer runs them back
    to back, so the pen just keeps drawing.
    """
    assert settings.paper_top_left and settings.paper_bottom_right
    to_bed = paper_to_machine(settings.paper_top_left, settings.paper_bottom_right)
    up, down = settings.pen_up, -settings.pen_pressure

    # Each line with where the pen is once it has run.
    lines: list[tuple[str, tuple[float, float]]] = []
    pos = (0.0, 0.0)
    lines += [("G90", pos), (f"G1 Z{up:.2f} F{Z_SPEED:.0f}", pos)]
    for stroke in strokes:
        points = [to_bed(x, y) for x, y in stroke]
        pos = points[0]
        # G1 rather than G0 for travel, like Bambu Studio's own G-code.
        lines.append((f"G1 X{pos[0]:.2f} Y{pos[1]:.2f} F{settings.travel_speed:.0f}", pos))
        lines.append((f"G1 Z{down:.2f} F{Z_SPEED:.0f}", pos))
        for i, pos in enumerate(points[1:]):
            # Feed rate is sticky, so only the first drawing move needs it.
            feed = f" F{settings.draw_speed:.0f}" if i == 0 else ""
            lines.append((f"G1 X{pos[0]:.2f} Y{pos[1]:.2f}{feed}", pos))
        lines.append((f"G1 Z{up:.2f} F{Z_SPEED:.0f}", pos))

    budget = MAX_MESSAGE_BYTES - MARKER_BYTES
    chunks: list[Chunk] = []
    current: list[str] = []
    size = 0
    end = pos
    for line, after in lines:
        if current and size + len(line) + 1 > budget:
            chunks.append(Chunk(current, end))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
        end = after
    if current:
        chunks.append(Chunk(current, end))
    return chunks


def preview_path(strokes: list[Stroke]) -> str:
    """An SVG path `d` for the strokes, for the preview on the page."""
    return " ".join("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in s) for s in strokes)
