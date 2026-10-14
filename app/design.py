"""Turning text, SVGs and images into pen strokes.

Everything here returns strokes: lists of (x, y) points in millimetres, with
the origin at the top-left and y pointing down, like on paper.
"""

import io
import random

import cv2
import numpy as np
import svgelements
from HersheyFonts import HersheyFonts

type Stroke = list[tuple[float, float]]

# Single-stroke fonts: each letter is drawn with one pass of the pen, the way
# you'd write it. Outline fonts would draw every letter as a hollow shape.
FONTS = {
    "scripts": "Handwriting",
    "cursive": "Cursive",
    "futural": "Simple",
    "rowmans": "Roman",
    "timesr": "Times",
    "timesi": "Times italic",
    "gothiceng": "Gothic",
}

POEMS = [
    "Fire and Ice\n\nSome say the world will end in fire,\nSome say in ice.\nFrom what I've tasted of desire\nI hold with those who favor fire.\nBut if it had to perish twice,\nI think I know enough of hate\nTo say that for destruction ice\nIs also great\nAnd would suffice.\n\n- Robert Frost",
    "Hope is the thing with feathers\nThat perches in the soul,\nAnd sings the tune without the words,\nAnd never stops at all.\n\n- Emily Dickinson",
    "The Red Wheelbarrow\n\nso much depends\nupon\n\na red wheel\nbarrow\n\nglazed with rain\nwater\n\nbeside the white\nchickens.\n\n- William Carlos Williams",
    "Dust of Snow\n\nThe way a crow\nShook down on me\nThe dust of snow\nFrom a hemlock tree\n\nHas given my heart\nA change of mood\nAnd saved some part\nOf a day I had rued.\n\n- Robert Frost",
    "I wandered lonely as a cloud\nThat floats on high o'er vales and hills,\nWhen all at once I saw a crowd,\nA host, of golden daffodils;\nBeside the lake, beneath the trees,\nFluttering and dancing in the breeze.\n\n- William Wordsworth",
    "Nothing Gold Can Stay\n\nNature's first green is gold,\nHer hardest hue to hold.\nHer early leaf's a flower;\nBut only so an hour.\nThen leaf subsides to leaf.\nSo Eden sank to grief,\nSo dawn goes down to day.\nNothing gold can stay.\n\n- Robert Frost",
]


def random_poem() -> str:
    return random.choice(POEMS)


def text_strokes(
    text: str,
    *,
    font: str,
    size: float,
    max_width: float,
    line_spacing: float = 1.6,
    align: str = "left",
) -> list[Stroke]:
    """Lay out text with `size` mm tall letters, wrapping at `max_width` mm."""
    f = HersheyFonts()
    f.load_default_font(font if font in FONTS else "scripts")
    f.normalize_rendering(size)

    def width(s: str) -> float:
        xs = [x for stroke in f.strokes_for_text(s) for x, _ in stroke]
        return max(xs) if xs else 0.0

    lines: list[str] = []
    for paragraph in text.splitlines():
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            if current and width(candidate) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)

    strokes: list[Stroke] = []
    line_height = size * line_spacing
    for i, line in enumerate(lines):
        baseline = size + i * line_height
        offset = 0.0
        if align == "center":
            offset = (max_width - width(line)) / 2
        elif align == "right":
            offset = max_width - width(line)
        for stroke in f.strokes_for_text(line):
            # Hershey glyphs have y pointing up.
            strokes.append([(offset + x, baseline - y) for x, y in stroke])
    return strokes


def svg_strokes(data: bytes) -> list[Stroke]:
    """Every visible shape in the SVG as strokes, in mm."""
    svg = svgelements.SVG.parse(io.BytesIO(data), reify=True)
    px_to_mm = 25.4 / 96
    strokes: list[Stroke] = []
    for element in svg.elements():
        if isinstance(element, svgelements.Text):
            continue
        if not isinstance(element, svgelements.Shape):
            continue
        path = svgelements.Path(element)
        if len(path) == 0:
            continue
        for sub in path.as_subpaths():
            sub = svgelements.Path(sub)
            length = sub.length(error=1e-3)
            if not length:
                continue
            # A point every ~0.25 mm follows curves closely enough for a pen.
            n = max(2, int(length * px_to_mm / 0.25))
            points = [sub.point(t / (n - 1)) for t in range(n)]
            strokes.append([(p.x * px_to_mm, p.y * px_to_mm) for p in points if p is not None])
    return [s for s in strokes if len(s) > 1]


def svg_has_text(data: bytes) -> bool:
    return b"<text" in data


def image_strokes(
    data: bytes,
    *,
    width_mm: float,
    height_mm: float,
    mode: str = "outline",
    threshold: int = 128,
    invert: bool = False,
    spacing: float = 0.8,
    gamma: float = 1.0,
) -> list[Stroke]:
    """Turn an image into strokes that fit in width_mm x height_mm.

    Tracing, which only knows ink or no ink:
    - outline: draw the edges of the dark areas
    - fill: outlines plus hatching inside the dark areas, `spacing` mm apart
    - edges: detect edges, which works better for photos

    Shading, where darker areas get more ink, see `TONAL_MODES`.
    """
    gray = _load_gray(data)
    if mode in TONAL_MODES:
        return _tonal(gray, width_mm, height_mm, mode=mode, spacing=spacing, invert=invert, gamma=gamma)

    # Work at a resolution that matches what a pen can draw (~0.1 mm per
    # pixel), which also keeps tracing fast for big photos.
    h, w = gray.shape
    mm_per_px = max(width_mm / w, height_mm / h, 0.1)
    scale = min(width_mm / w, height_mm / h) / mm_per_px
    gray = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    if mode == "edges":
        ink = cv2.Canny(gray, threshold / 2, threshold)
    else:
        ink = (gray < threshold).astype(np.uint8) * 255
    if invert:
        ink = 255 - ink

    contours, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    strokes: list[Stroke] = []
    for contour in contours:
        if cv2.arcLength(contour, True) * mm_per_px < 1.0:
            continue  # specks
        simplified = cv2.approxPolyDP(contour, 0.5, True)
        points = [(float(x) * mm_per_px, float(y) * mm_per_px) for [[x, y]] in simplified]
        if mode != "edges":
            points.append(points[0])
        strokes.append(points)

    if mode == "fill":
        strokes += _hatch(ink, spacing / mm_per_px, mm_per_px)
    return strokes


def _load_gray(data: bytes) -> np.ndarray:
    buffer = np.frombuffer(data, np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError("Couldn't read that image")
    if image.ndim == 3 and image.shape[2] == 4:
        # Transparent areas count as paper.
        alpha = image[:, :, 3:4].astype(np.float32) / 255
        image = (image[:, :, :3] * alpha + 255 * (1 - alpha)).astype(np.uint8)
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Decoding as grayscale applies the EXIF orientation, which phone photos
    # rely on to be the right way up (IMREAD_UNCHANGED ignores it).
    return cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)


def _hatch(ink: np.ndarray, spacing_px: float, mm_per_px: float) -> list[Stroke]:
    """Horizontal lines across the inked areas, alternating direction."""
    strokes: list[Stroke] = []
    row = spacing_px / 2
    flip = False
    while row < ink.shape[0]:
        y = int(row)
        line = ink[y] > 0
        changes = np.flatnonzero(np.diff(np.concatenate(([0], line.astype(np.int8), [0]))))
        segments = [(changes[i], changes[i + 1] - 1) for i in range(0, len(changes), 2)]
        if flip:
            segments = [(b, a) for a, b in reversed(segments)]
        for a, b in segments:
            if abs(b - a) * mm_per_px >= 0.5:
                strokes.append([(a * mm_per_px, y * mm_per_px), (b * mm_per_px, y * mm_per_px)])
        flip = not flip
        row += spacing_px
    return strokes


# Shading styles. Each draws long continuous lines that carry more ink where
# the image is darker, so photos keep their greys.
TONAL_MODES = ("spiral", "circles", "squiggle", "crosshatch")

# Below this darkness nothing is drawn, so white stays white.
WHITE = 0.06


class _Darkness:
    """How dark the image is at any point, in mm, from 0 (white) to 1 (black)."""

    def __init__(self, gray: np.ndarray, width_mm: float, height_mm: float, invert: bool, gamma: float = 1.0):
        h, w = gray.shape
        # Fit the image in the box, then work at ~0.25 mm per pixel: finer
        # than any line we draw, and quick to process.
        self.mm_per_px = min(width_mm / w, height_mm / h)
        self.width, self.height = w * self.mm_per_px, h * self.mm_per_px
        px = 0.25
        small = cv2.resize(
            gray, (max(2, int(self.width / px)), max(2, int(self.height / px))), interpolation=cv2.INTER_AREA
        )
        # Stretch the contrast locally so faces in flat photos still read.
        small = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(small)
        small = cv2.GaussianBlur(small, (5, 5), 0)
        dark = 1 - small.astype(np.float32) / 255
        dark = 1 - dark if invert else dark
        # Above 1 lightens the mid-tones while keeping blacks black.
        self.values = dark ** max(gamma, 0.1)
        self.px = px

    def __call__(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        h, w = self.values.shape
        cols = (xs / self.px).astype(int)
        rows = (ys / self.px).astype(int)
        inside = (cols >= 0) & (cols < w) & (rows >= 0) & (rows < h)
        out = np.zeros(xs.shape, np.float32)
        out[inside] = self.values[rows[inside], cols[inside]]
        return out


def _tonal(
    gray: np.ndarray, width_mm: float, height_mm: float, *, mode: str, spacing: float, invert: bool, gamma: float
) -> list[Stroke]:
    darkness = _Darkness(gray, width_mm, height_mm, invert, gamma)
    spacing = max(spacing, 0.3)
    if mode == "crosshatch":
        return _crosshatch(darkness, spacing)
    if mode == "squiggle":
        xs = np.arange(0, darkness.width, 0.1)
        paths = [np.column_stack([xs, np.full_like(xs, y)]) for y in np.arange(spacing / 2, darkness.height, spacing)]
    else:
        cx, cy = darkness.width / 2, darkness.height / 2
        radius = np.hypot(cx, cy)
        if mode == "spiral":
            # An Archimedean spiral, `spacing` apart, sampled every ~0.1 mm.
            turns = radius / spacing
            theta = _spiral_angles(turns, spacing)
            r = spacing * theta / (2 * np.pi)
            paths = [np.column_stack([cx + r * np.cos(theta), cy + r * np.sin(theta)])]
        else:
            paths = []
            for r in np.arange(spacing, radius, spacing):
                theta = np.linspace(0, 2 * np.pi, max(16, int(2 * np.pi * r / 0.1)))
                paths.append(np.column_stack([cx + r * np.cos(theta), cy + r * np.sin(theta)]))
    strokes: list[Stroke] = []
    for path in paths:
        strokes += _wiggle(path, darkness, amplitude=spacing * 0.48)
    return strokes


def _spiral_angles(turns: float, spacing: float) -> np.ndarray:
    """Angles along a spiral so consecutive points are ~0.1 mm apart."""
    angles = [0.0]
    theta = 0.0
    end = turns * 2 * np.pi
    while theta < end:
        r = max(spacing * theta / (2 * np.pi), 0.5)
        theta += 0.1 / r
        angles.append(theta)
    return np.array(angles)


def _wiggle(path: np.ndarray, darkness: _Darkness, amplitude: float, wavelength: float = 0.8) -> list[Stroke]:
    """Zig-zag across a path, wider where the image is darker.

    The zig-zag is what carries the shading: in black areas it fills the gap
    to the next line, in white areas the pen lifts.
    """
    # Resample so there's one point per half wavelength (each zig and zag).
    seg = np.hypot(*np.diff(path, axis=0).T)
    dist = np.concatenate([[0], np.cumsum(seg)])
    if dist[-1] < wavelength:
        return []
    at = np.arange(0, dist[-1], wavelength / 2)
    xs = np.interp(at, dist, path[:, 0])
    ys = np.interp(at, dist, path[:, 1])
    d = darkness(xs, ys)
    # Perpendicular to the path at each point.
    tx, ty = np.gradient(xs), np.gradient(ys)
    norm = np.hypot(tx, ty) + 1e-9
    nx, ny = -ty / norm, tx / norm
    sign = np.where(np.arange(len(xs)) % 2 == 0, 1.0, -1.0)
    offset = sign * amplitude * d
    px, py = xs + nx * offset, ys + ny * offset

    strokes: list[Stroke] = []
    current: Stroke = []
    for x, y, value in zip(px, py, d):
        if value > WHITE:
            current.append((float(x), float(y)))
        elif current:
            if len(current) > 1:
                strokes.append(current)
            current = []
    if len(current) > 1:
        strokes.append(current)
    return strokes


def _crosshatch(darkness: _Darkness, spacing: float) -> list[Stroke]:
    """Layers of parallel lines: each darker tone adds another direction."""
    levels = [(0.2, 45), (0.4, 135), (0.6, 0), (0.8, 90)]
    cx, cy = darkness.width / 2, darkness.height / 2
    half = np.hypot(cx, cy)
    strokes: list[Stroke] = []
    step = 0.2
    for threshold, angle in levels:
        a = np.radians(angle)
        dx, dy = np.cos(a), np.sin(a)
        for offset in np.arange(-half, half, spacing):
            t = np.arange(-half, half, step)
            xs = cx + dx * t - dy * offset
            ys = cy + dy * t + dx * offset
            ink = darkness(xs, ys) > threshold
            if not ink.any():
                continue
            # Runs of ink along this line become strokes.
            edges = np.flatnonzero(np.diff(np.concatenate([[0], ink.astype(np.int8), [0]])))
            for start, end in zip(edges[::2], edges[1::2]):
                if (end - start) * step >= 0.6:
                    strokes.append([(float(xs[start]), float(ys[start])), (float(xs[end - 1]), float(ys[end - 1]))])
    return strokes
