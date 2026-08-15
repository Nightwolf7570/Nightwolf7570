#!/usr/bin/env python3
"""Turn the green cells in the 2027 graph into a rotating 3D artifact."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "graph-2027-light.svg"
STL_OUTPUT = ROOT / "assets" / "commit-hearts.stl"
SVG_OUTPUT = ROOT / "assets" / "commit-hearts-3d.svg"

BACKGROUND = "#ebedf0"
DEPTHS = {
    "#40c463": 0.72,
    "#30a14e": 1.02,
    "#216e39": 1.34,
}
CELL_PITCH = 1.24
CELL_SIZE = 0.96


@dataclass(frozen=True)
class Cell:
    col: int
    row: int
    color: str
    depth: float


def read_cells() -> list[Cell]:
    source = SOURCE.read_text(encoding="utf-8")
    matches = re.findall(
        r'<rect x="(\d+)" y="(\d+)"[^>]*fill="(#[0-9a-fA-F]{6})"', source
    )
    colored = [(int(x), int(y), color.lower()) for x, y, color in matches if color.lower() != BACKGROUND]
    xs = sorted({int(x) for x, _, _ in matches})
    ys = sorted({y for _, y, _ in colored})
    x_step = min(b - a for a, b in zip(xs, xs[1:]))
    x_origin = min(x for x, _, _ in colored)
    y_index = {y: index for index, y in enumerate(ys)}
    return [
        Cell((x - x_origin) // x_step, y_index[y], color, DEPTHS[color])
        for x, y, color in colored
    ]


def cuboid_vertices(cell: Cell) -> list[tuple[float, float, float]]:
    x0 = cell.col * CELL_PITCH
    z0 = (5 - cell.row) * CELL_PITCH
    x1 = x0 + CELL_SIZE
    z1 = z0 + CELL_SIZE
    y0 = -cell.depth / 2
    y1 = cell.depth / 2
    return [
        (x0, y0, z0),
        (x1, y0, z0),
        (x1, y1, z0),
        (x0, y1, z0),
        (x0, y0, z1),
        (x1, y0, z1),
        (x1, y1, z1),
        (x0, y1, z1),
    ]


FACES = [
    ((0, 3, 2, 1), (0, 0, -1)),
    ((4, 5, 6, 7), (0, 0, 1)),
    ((0, 1, 5, 4), (0, -1, 0)),
    ((3, 7, 6, 2), (0, 1, 0)),
    ((0, 4, 7, 3), (-1, 0, 0)),
    ((1, 2, 6, 5), (1, 0, 0)),
]


def fmt(value: float) -> str:
    rounded = round(value, 5)
    if rounded == 0:
        rounded = 0
    return f"{rounded:g}"


def write_stl(cells: list[Cell]) -> None:
    lines = ["solid github_commit_hearts"]
    for cell in cells:
        vertices = cuboid_vertices(cell)
        for indices, normal in FACES:
            a, b, c, d = (vertices[index] for index in indices)
            for triangle in ((a, b, c), (a, c, d)):
                lines.append(f"facet normal {fmt(normal[0])} {fmt(normal[1])} {fmt(normal[2])}")
                lines.append(" outer loop")
                for x, y, z in triangle:
                    lines.append(f"  vertex {fmt(x)} {fmt(y)} {fmt(z)}")
                lines.append(" endloop")
                lines.append("endfacet")
    lines.append("endsolid github_commit_hearts")
    STL_OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))


def shade(color: str, factor: float) -> str:
    values = [max(0, min(255, round(channel * factor))) for channel in hex_to_rgb(color)]
    return "#" + "".join(f"{value:02x}" for value in values)


def rotate(vertex: tuple[float, float, float], angle: float, center_x: float) -> tuple[float, float, float]:
    x, y, z = vertex
    x -= center_x
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return (cosine * x - sine * y, sine * x + cosine * y, z)


def project(vertex: tuple[float, float, float], scale: float, center_x: float, baseline: float) -> tuple[float, float]:
    x, depth, z = vertex
    return (center_x + x * scale, baseline - z * scale + depth * scale * 0.10)


def svg_frame(cells: list[Cell], angle: float) -> str:
    model_center = (max(cell.col for cell in cells) * CELL_PITCH + CELL_SIZE) / 2
    faces: list[tuple[float, str]] = []
    for cell in cells:
        vertices = [rotate(vertex, angle, model_center) for vertex in cuboid_vertices(cell)]
        for indices, normal in FACES:
            normal_x, normal_y, normal_z = rotate(normal, angle, 0)
            visibility = -normal_y - 0.10 * normal_z
            if visibility <= 0.001:
                continue
            face_vertices = [vertices[index] for index in indices]
            average_depth = sum(vertex[1] for vertex in face_vertices) / 4
            points = " ".join(
                f"{fmt(x)},{fmt(y)}"
                for x, y in (project(vertex, 10.7, 380, 174) for vertex in face_vertices)
            )
            light = 0.72 + 0.16 * max(0, -normal_y) + 0.12 * max(0, -normal_z)
            color = shade(cell.color, light)
            faces.append((average_depth, f'<polygon points="{points}" fill="{color}" stroke="#0d4429" stroke-width="0.45"/>'))
    faces.sort(key=lambda item: item[0], reverse=True)
    return "".join(face for _, face in faces)


def write_svg(cells: list[Cell]) -> None:
    frame_count = 28
    duration = 9.8
    groups = []
    for frame in range(frame_count):
        angle = math.radians(30) * math.sin(2 * math.pi * frame / frame_count)
        values = ["0"] * (frame_count + 1)
        values[frame] = "1"
        values[-1] = values[0]
        key_times = ";".join(fmt(index / frame_count) for index in range(frame_count + 1))
        groups.append(
            '<g opacity="0">'
            f'<animate attributeName="opacity" values="{";".join(values)}" keyTimes="{key_times}" '
            f'calcMode="discrete" dur="{duration}s" repeatCount="indefinite"/>'
            f"{svg_frame(cells, angle)}</g>"
        )

    title = escape("Five hearts · 135 commits · one rotatable object")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="232" viewBox="0 0 760 232" role="img" '
        f'aria-label="{title}">'
        '<style>'
        'text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}'
        '.label{fill:#57606a}.title{fill:#1f2328}'
        '@media(prefers-color-scheme:dark){.label{fill:#8c959f}.title{fill:#f0f6fc}}'
        '</style>'
        f'<title>{title}</title>'
        '<text class="title" x="380" y="20" text-anchor="middle" font-size="13" font-weight="600">'
        'THE 2027 CONTRIBUTION FIELD / EXTRUDED</text>'
        '<text class="label" x="380" y="218" text-anchor="middle" font-size="11">'
        'click the artifact, then drag to rotate it yourself</text>'
        + "".join(groups)
        + "</svg>\n"
    )
    SVG_OUTPUT.write_text(svg, encoding="utf-8")


def main() -> None:
    cells = read_cells()
    if len(cells) != 135:
        raise SystemExit(f"expected 135 contribution cells, found {len(cells)}")
    write_stl(cells)
    write_svg(cells)
    print(f"generated {STL_OUTPUT.relative_to(ROOT)} ({len(cells)} cubes)")
    print(f"generated {SVG_OUTPUT.relative_to(ROOT)} ({len(cells)} cubes, 28 frames)")


if __name__ == "__main__":
    main()
