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
) -> list[Stroke]:
    """Trace an image so it fits in width_mm x height_mm.

    - outline: draw the edges of the dark areas
    - fill: outlines plus hatching inside the dark areas, `spacing` mm apart
    - edges: detect edges, which works better for photos
    """
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError("Couldn't read that image")
    if image.ndim == 3 and image.shape[2] == 4:
        # Transparent areas count as paper.
        alpha = image[:, :, 3:4].astype(np.float32) / 255
        image = (image[:, :, :3] * alpha + 255 * (1 - alpha)).astype(np.uint8)
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

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
