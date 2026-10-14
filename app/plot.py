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


def transform(strokes: list[Stroke], *, rotation: float, scale: float, offset: tuple[float, float]) -> list[Stroke]:
    """Rotate (degrees, clockwise on the page) and scale around the drawing's centre, then move it."""
    if not rotation and scale == 1 and offset == (0, 0):
        return strokes
    x0, y0, x1, y1 = bounds(strokes)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    # y points down on paper, so a positive angle turns clockwise.
    a = math.radians(rotation)
    cos, sin = math.cos(a) * scale, math.sin(a) * scale
    dx, dy = cx + offset[0], cy + offset[1]
    return [
        [((x - cx) * cos - (y - cy) * sin + dx, (x - cx) * sin + (y - cy) * cos + dy) for x, y in s] for s in strokes
    ]


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


def center(strokes: list[Stroke], paper_w: float, paper_h: float) -> list[Stroke]:
    """Move strokes to the middle of the paper, keeping their size."""
    if not strokes:
        return []
    x0, y0, x1, y1 = bounds(strokes)
    dx, dy = (paper_w - (x0 + x1)) / 2, (paper_h - (y0 + y1)) / 2
    return [[(x + dx, y + dy) for x, y in s] for s in strokes]


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
    # Messages go one at a time, with a wait of about a second between them
    # for the printer to confirm. Each G-code line is ~20 bytes.
    points = sum(len(s) for s in strokes)
    messages = (points * 20 + len(strokes) * 60) / (MAX_MESSAGE_BYTES - MARKER_BYTES)
    # Acceleration means real moves are slower than the feed rate suggests,
    # especially lots of short ones; 1.3 is a rough correction.
    return 1.3 * (draw / settings.draw_speed * 60 + travel / settings.travel_speed * 60) + lifts + messages


def paper_to_machine(top_left: Point, bottom_right: Point):
    """Map paper coordinates (mm, y down from the top edge) to bed coordinates."""
    sx = 1 if bottom_right.x >= top_left.x else -1
    sy = 1 if bottom_right.y >= top_left.y else -1

    def convert(x: float, y: float) -> tuple[float, float]:
        return top_left.x + sx * x, top_left.y + sy * y

    return convert


def gcode_chunks(strokes: list[Stroke], settings: Settings) -> list[Chunk]:
    """G-code for the strokes, split into messages small enough for the printer.

    Messages break between strokes, so the pen is up while the printer waits
    for the next one. Only a stroke too long for one message is split, and
    then the pen just pauses for a moment mid-line.
    """
    assert settings.paper_top_left and settings.paper_bottom_right
    to_bed = paper_to_machine(settings.paper_top_left, settings.paper_bottom_right)
    up, down = settings.pen_up, -settings.pen_pressure

    # The G-code for each stroke, each line with where the pen is after it.
    groups: list[list[tuple[str, tuple[float, float]]]] = []
    for stroke in strokes:
        points = [to_bed(x, y) for x, y in stroke]
        pos = points[0]
        group = [
            # G1 rather than G0 for travel, like Bambu Studio's own G-code.
            (f"G1 X{pos[0]:.2f} Y{pos[1]:.2f} F{settings.travel_speed:.0f}", pos),
            (f"G1 Z{down:.2f} F{Z_SPEED:.0f}", pos),
        ]
        for i, pos in enumerate(points[1:]):
            # Feed rate is sticky, so only the first drawing move needs it.
            feed = f" F{settings.draw_speed:.0f}" if i == 0 else ""
            group.append((f"G1 X{pos[0]:.2f} Y{pos[1]:.2f}{feed}", pos))
        group.append((f"G1 Z{up:.2f} F{Z_SPEED:.0f}", pos))
        groups.append(group)

    # Every message starts by making sure we're in absolute mode.
    header = "G90"
    budget = MAX_MESSAGE_BYTES - MARKER_BYTES - len(header) - 1
    chunks: list[Chunk] = []
    current: list[tuple[str, tuple[float, float]]] = []
    size = 0

    def flush() -> None:
        nonlocal current, size
        if current:
            chunks.append(Chunk([header] + [line for line, _ in current], current[-1][1]))
        current, size = [], 0

    first = [(f"G1 Z{up:.2f} F{Z_SPEED:.0f}", (0.0, 0.0))]
    for group in [first, *groups]:
        group_size = sum(len(line) + 1 for line, _ in group)
        if size + group_size > budget:
            flush()
        if group_size <= budget:
            current += group
            size += group_size
            continue
        for line, pos in group:
            if size + len(line) + 1 > budget:
                flush()
            current.append((line, pos))
            size += len(line) + 1
    flush()
    return chunks


def preview_path(strokes: list[Stroke]) -> str:
    """An SVG path `d` for the strokes, for the preview on the page."""
    return " ".join("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in s) for s in strokes)
