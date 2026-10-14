import cv2
import numpy as np

from app import design, plot
from app.printer import MAX_MESSAGE_BYTES
from app.settings import Point, Settings


def test_text_wraps_to_width():
    strokes = design.text_strokes("hello " * 40, font="futural", size=5, max_width=80)
    _x0, _y0, x1, y1 = plot.bounds(strokes)
    assert x1 <= 80.5
    assert y1 > 20  # wrapped onto several lines


def test_svg_units_are_mm():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="50mm" height="20mm" viewBox="0 0 50 20"><rect x="0" y="0" width="50" height="20"/></svg>'
    x0, y0, x1, y1 = plot.bounds(design.svg_strokes(svg))
    assert abs((x1 - x0) - 50) < 0.5
    assert abs((y1 - y0) - 20) < 0.5


def test_image_is_traced_to_fit():
    img = np.full((400, 400), 255, np.uint8)
    cv2.circle(img, (200, 200), 120, 0, -1)
    data = cv2.imencode(".png", img)[1].tobytes()
    for mode in ("outline", "fill", "edges"):
        strokes = design.image_strokes(data, width_mm=50, height_mm=80, mode=mode)
        assert strokes
        _x0, _y0, x1, y1 = plot.bounds(strokes)
        assert x1 <= 50.5 and y1 <= 80.5


def test_place_fits_inside_margins():
    strokes = [[(0, 0), (300, 100)]]
    placed = plot.place(strokes, paper_w=100, paper_h=150, margin=10, fit=True)
    x0, _y0, x1, _y1 = plot.bounds(placed)
    assert x0 >= 10 - 1e-6 and x1 <= 90 + 1e-6


def test_paper_top_facing_back_of_printer():
    # Top-left at the back-left of the bed: paper y goes towards the front, i.e. down in machine Y.
    to_bed = plot.paper_to_machine(Point(x=20, y=160), Point(x=125, y=12))
    assert to_bed(0, 0) == (20, 160)
    assert to_bed(10, 10) == (30, 150)


def test_chunks_fit_in_a_message_and_stay_on_paper():
    s = Settings(paper_top_left=Point(x=20, y=160), paper_bottom_right=Point(x=125, y=12))
    # Lots of short strokes and one very long one, which has to be split.
    strokes = [[(i / 2, 0.0), (i / 2, 10.0)] for i in range(200)]
    strokes.append([(50 + 40 * np.cos(t / 50), 70 + 40 * np.sin(t / 50)) for t in range(400)])
    chunks = plot.gcode_chunks(plot.order(strokes), s)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len("\n".join(chunk.lines)) + plot.MARKER_BYTES <= MAX_MESSAGE_BYTES
    lines = [line for chunk in chunks for line in chunk.lines]
    assert lines[-1] == f"G1 Z{s.pen_up:.2f} F900"
    for line in lines:
        if " X" in line:
            x = float(line.split(" X")[1].split()[0])
            y = float(line.split(" Y")[1].split()[0])
            assert 20 <= x <= 125 and 12 <= y <= 160


def test_clip_drops_what_is_off_the_paper():
    clipped = plot.clip([[(-5, 5), (5, 5), (10, 5), (200, 5)], [(500, 500), (501, 501)]], 100, 100)
    assert clipped == [[(5, 5), (10, 5)]]
