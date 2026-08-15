#!/usr/bin/env python3
"""Generate a GitHub-safe SVG where the five contribution hearts become stats."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "graph-2027-light.svg"
OUTPUT = ROOT / "assets" / "commit-hearts-stats.svg"

BACKGROUND = "#ebedf0"
WIDTH = 780
DURATION = 20
FRAME_COUNT = 48
BASELINE = 138


@dataclass(frozen=True)
class Cell:
    x: int
    y: int
    color: str


@dataclass(frozen=True)
class Stat:
    value: str
    label: str


STATS = (
    Stat("7,518", "CONTRIBUTIONS"),
    Stat("43", "REPOS"),
    Stat("11", "HACKATHON WINS"),
    Stat("5", "LANGUAGES"),
    Stat("135", "CELLS"),
)


def read_hearts() -> list[list[Cell]]:
    source = SOURCE.read_text(encoding="utf-8")
    cells = [
        Cell(int(x), int(y), color.lower())
        for x, y, color in re.findall(
            r'<rect x="(\d+)" y="(\d+)"[^>]*fill="(#[0-9a-fA-F]{6})"', source
        )
        if color.lower() != BACKGROUND
    ]
    if len(cells) != 135:
        raise SystemExit(f"expected 135 colored cells, found {len(cells)}")

    xs = sorted({cell.x for cell in cells})
    starts = [xs[0]] + [right for left, right in zip(xs, xs[1:]) if right - left > 20]
    hearts: list[list[Cell]] = []
    for start in starts:
        heart = sorted(
            (cell for cell in cells if start <= cell.x <= start + 84),
            key=lambda cell: (cell.x, cell.y),
        )
        if len(heart) != 27:
            raise SystemExit(f"expected 27 cells in heart at x={start}, found {len(heart)}")
        hearts.append(heart)
    if len(hearts) != 5:
        raise SystemExit(f"expected 5 hearts, found {len(hearts)}")
    return hearts


def fmt(value: float) -> str:
    rounded = round(value, 4)
    if rounded == 0:
        rounded = 0
    return f"{rounded:g}"


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def smoothstep(value: float) -> float:
    value = clamp(value)
    return value * value * (3 - 2 * value)


def lerp(start: float, end: float, amount: float) -> float:
    return start + (end - start) * amount


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))


def shade(color: str, factor: float) -> str:
    channels = [max(0, min(255, round(channel * factor))) for channel in hex_to_rgb(color)]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


FACES = (
    ((0, 3, 2, 1), (0, 0, -1)),
    ((4, 5, 6, 7), (0, 0, 1)),
    ((0, 1, 5, 4), (0, -1, 0)),
    ((3, 7, 6, 2), (0, 1, 0)),
    ((0, 4, 7, 3), (-1, 0, 0)),
    ((1, 2, 6, 5), (1, 0, 0)),
)

DEPTHS = {"#40c463": 7.7, "#30a14e": 10.9, "#216e39": 14.3}
HEART_CENTERS = (114, 254, 394, 534, 674)


def cuboid_vertices(
    center: tuple[float, float, float], size: tuple[float, float, float]
) -> list[tuple[float, float, float]]:
    cx, cy, cz = center
    sx, sy, sz = (dimension / 2 for dimension in size)
    return [
        (cx - sx, cy - sy, cz - sz),
        (cx + sx, cy - sy, cz - sz),
        (cx + sx, cy + sy, cz - sz),
        (cx - sx, cy + sy, cz - sz),
        (cx - sx, cy - sy, cz + sz),
        (cx + sx, cy - sy, cz + sz),
        (cx + sx, cy + sy, cz + sz),
        (cx - sx, cy + sy, cz + sz),
    ]


def rotate_yaw(
    vector: tuple[float, float, float], angle: float, center_x: float = WIDTH / 2
) -> tuple[float, float, float]:
    x, y, z = vector
    x -= center_x
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return (center_x + cosine * x - sine * y, sine * x + cosine * y, z)


def project(vertex: tuple[float, float, float]) -> tuple[float, float]:
    x, depth, z = vertex
    return (x, BASELINE - z + depth * 0.10)


def animation_state(progress: float) -> tuple[str, float, float]:
    """Return phase, transition progress, and whole-field yaw."""
    if progress < 0.28:
        yaw = math.radians(30) * math.sin(2 * math.pi * progress / 0.28)
        return ("heart", 0.0, yaw)
    if progress < 0.48:
        return ("into", (progress - 0.28) / 0.20, 0.0)
    if progress < 0.72:
        return ("stats", 1.0, 0.0)
    if progress < 0.90:
        return ("out", (progress - 0.72) / 0.18, 0.0)
    return ("heart", 0.0, 0.0)


def cell_morph(phase: str, transition: float, heart_index: int, cell_index: int) -> float:
    if phase == "stats":
        return 1.0
    if phase == "heart":
        return 0.0
    column = cell_index % 9
    row = cell_index // 9
    delay = heart_index * 0.018 + column * 0.010 + row * 0.008
    local = smoothstep(clamp((transition - delay) / (1 - 0.15)))
    return local if phase == "into" else 1 - local


def transformed_cell(
    cell: Cell,
    heart_index: int,
    cell_index: int,
    morph: float,
    yaw: float,
    progress: float,
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    source_center = (cell.x + 5.5, 0.0, BASELINE - (cell.y + 5.5))
    target_column = cell_index % 9
    target_row = cell_index // 9
    target_center = (
        HEART_CENTERS[heart_index] - 48 + target_column * 12,
        0.55 * math.sin(progress * 2 * math.pi + cell_index * 0.37),
        BASELINE - (99.5 + target_row * 11),
    )
    center = tuple(lerp(source, target, morph) for source, target in zip(source_center, target_center))
    size = (
        lerp(11, 7, morph),
        lerp(DEPTHS[cell.color], 1.8, morph),
        lerp(11, 7, morph),
    )
    vertices = [rotate_yaw(vertex, yaw * (1 - morph)) for vertex in cuboid_vertices(center, size)]
    normals = [rotate_yaw(normal, yaw * (1 - morph), 0) for _, normal in FACES]
    return vertices, normals


def render_frame(
    hearts: list[list[Cell]], frame: int
) -> tuple[str, float, float]:
    progress = frame / FRAME_COUNT
    phase, transition, yaw = animation_state(progress)
    faces: list[tuple[float, str]] = []
    y_values: list[float] = []

    for heart_index, heart in enumerate(hearts):
        for cell_index, cell in enumerate(heart):
            morph = cell_morph(phase, transition, heart_index, cell_index)
            vertices, normals = transformed_cell(cell, heart_index, cell_index, morph, yaw, progress)
            for (indices, _), (normal_x, normal_y, normal_z) in zip(FACES, normals):
                visibility = -normal_y - 0.10 * normal_z
                if visibility <= 0.001:
                    continue
                face_vertices = [vertices[index] for index in indices]
                projected = [project(vertex) for vertex in face_vertices]
                y_values.extend(y for _, y in projected)
                points = " ".join(f"{fmt(x)},{fmt(y)}" for x, y in projected)
                average_depth = sum(vertex[1] for vertex in face_vertices) / 4
                light = 0.72 + 0.16 * max(0, -normal_y) + 0.12 * max(0, -normal_z)
                color = shade(cell.color, light)
                faces.append(
                    (average_depth, f'<polygon points="{points}" fill="{color}" stroke="#0d4429" stroke-width="0.45"/>')
                )

    faces.sort(key=lambda item: item[0], reverse=True)
    return "".join(face for _, face in faces), min(y_values), max(y_values)


def opacity_animation(values: str, key_times: str) -> str:
    return (
        f'<animate attributeName="opacity" values="{values}" keyTimes="{key_times}" '
        f'dur="{DURATION}s" repeatCount="indefinite"/>'
    )


def stat_copy() -> str:
    chunks: list[str] = []
    for center, stat in zip(HEART_CENTERS, STATS):
        chunks.append(
            f'<g transform="translate({center} 0)">'
            f'<text class="value" x="0" y="55" text-anchor="middle">{escape(stat.value)}</text>'
            f'<text class="label" x="0" y="78" text-anchor="middle">{escape(stat.label)}</text>'
            "</g>"
        )
    return "".join(chunks)


def write_svg(hearts: list[list[Cell]]) -> None:
    groups: list[str] = []
    min_y = math.inf
    max_y = -math.inf
    key_times = ";".join(fmt(index / FRAME_COUNT) for index in range(FRAME_COUNT + 1))

    for frame in range(FRAME_COUNT):
        frame_svg, frame_min_y, frame_max_y = render_frame(hearts, frame)
        min_y = min(min_y, frame_min_y)
        max_y = max(max_y, frame_max_y)
        values = ["0"] * (FRAME_COUNT + 1)
        values[frame] = "1"
        values[-1] = values[0]
        base_opacity = "1" if frame == 0 else "0"
        groups.append(
            f'<g opacity="{base_opacity}">'
            f'<animate attributeName="opacity" values="{";".join(values)}" keyTimes="{key_times}" '
            f'calcMode="discrete" dur="{DURATION}s" repeatCount="indefinite"/>'
            f'{frame_svg}</g>'
        )

    view_top = math.floor(min(min_y, 27))
    view_bottom = math.ceil(max(max_y, 128))
    view_height = view_bottom - view_top
    title = "Five rotating contribution hearts drift into GitHub stats"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{view_height}" viewBox="0 {view_top} {WIDTH} {view_height}" role="img" aria-label="{escape(title)}">
  <title>{escape(title)}</title>
  <style>
    text {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }}
    .value {{ fill: #1f2328; font-size: 27px; font-weight: 700; letter-spacing: -1px; }}
    .label {{ fill: #57606a; font-size: 9px; font-weight: 700; letter-spacing: .65px; }}
    @media (prefers-color-scheme: dark) {{
      .value {{ fill: #f0f6fc; }}
      .label {{ fill: #8c959f; }}
    }}
  </style>
  <g class="stats-copy" opacity="0">
    {opacity_animation("0;0;1;1;0;0", "0;.36;.48;.72;.84;1")}
    {stat_copy()}
  </g>
  {''.join(groups)}
</svg>
'''
    OUTPUT.write_text(svg, encoding="utf-8")


# ---------------------------------------------------------------------------
# Heartbeat-skyline banner: EKG sweep first, then the city recedes and the
# same stats drift into the sky. One loop = SKY_DUR seconds.
# ---------------------------------------------------------------------------

SKY_W, SKY_H = 1200, 260
SKY_BASE = 232          # baseline y (EKG flatline / street level)
SKY_PERIOD = 1400       # dash period in normalized pathLength units
SKY_DASH = 80           # visible sweep segment length
SKY_DUR = 26            # sweep runs 0-50%, stats hold 60-84%


@dataclass(frozen=True)
class Skyline:
    path_d: str
    fill_d: str
    spike_d: str
    windows: str
    tip_fraction: float  # where along the path the spire tip sits (0..1)


def build_skyline() -> Skyline:
    import math

    pts: list[tuple[float, float]] = [(0.0, SKY_BASE)]
    buildings: list[tuple[float, float, float]] = []
    x = 0.0

    def flat(w: float) -> None:
        nonlocal x
        x += w
        pts.append((x, SKY_BASE))

    def bldg(w: float, roof: float, antenna: tuple[float, float, float] | None = None) -> None:
        nonlocal x
        x0 = x
        pts.append((x, roof))
        if antenna:
            frac, tip, aw = antenna
            ax = x0 + w * frac
            pts.extend([(ax, roof), (ax, tip), (ax + aw, tip), (ax + aw, roof)])
        x = x0 + w
        pts.append((x, roof))
        buildings.append((x0, x, roof))

    def down_to(y: float) -> None:
        pts.append((x, y))

    def slope(w_up: float, top_w: float, w_down: float, roof: float) -> None:
        nonlocal x
        x += w_up; pts.append((x, roof))
        x += top_w; pts.append((x, roof))
        x += w_down; pts.append((x, SKY_BASE))

    flat(28)
    bldg(70, 150); down_to(SKY_BASE)
    flat(18)
    bldg(48, 118)
    down_to(160); bldg(64, 160); down_to(SKY_BASE)
    flat(20)
    bldg(90, 96, antenna=(0.62, 68, 5)); down_to(SKY_BASE)
    flat(26)
    slope(16, 26, 16, 196)                  # P wave
    flat(14)
    x += 6; pts.append((x, 242))            # q dip
    spike_x0 = x
    x += 16; pts.append((x, 26))            # R: the spire
    spike_tip = (x, 26)
    x += 16; pts.append((x, 252))           # S: under baseline
    x += 8; pts.append((x, SKY_BASE))
    flat(14)
    slope(20, 34, 20, 182)                  # T wave
    flat(24)
    bldg(56, 132); down_to(SKY_BASE)
    flat(14)
    bldg(72, 88, antenna=(0.3, 58, 5))
    down_to(142); bldg(44, 142); down_to(SKY_BASE)
    flat(16)
    bldg(60, 174); down_to(SKY_BASE)
    flat(20)
    bldg(78, 110); down_to(SKY_BASE)
    flat(18)
    bldg(52, 164); down_to(SKY_BASE)
    flat(12)
    bldg(66, 138); down_to(SKY_BASE)
    flat(SKY_W - x)
    pts[-1] = (SKY_W, SKY_BASE)

    def arclen(ps: list[tuple[float, float]]) -> float:
        return sum(math.dist(ps[i], ps[i + 1]) for i in range(len(ps) - 1))

    tip_fraction = arclen(pts[: pts.index(spike_tip) + 1]) / arclen(pts)

    win_rects: list[str] = []
    wi = 0
    for (x0, x1, roof) in buildings:
        w = x1 - x0
        cols = max(1, int((w - 18) // 15))
        rows = max(1, int((SKY_BASE - roof - 16) // 18))
        gx = (w - cols * 6 - (cols - 1) * 9) / 2
        for r in range(rows):
            for c in range(cols):
                wi += 1
                cls = f' class="tw tw{len(win_rects) % 5}"' if (wi * 7919) % 13 < 3 else ""
                win_rects.append(
                    f'<rect x="{x0 + gx + c * 15:g}" y="{roof + 10 + r * 18:g}" width="6" height="8"{cls}/>'
                )

    path_d = "M" + " L".join(f"{px:g} {py:g}" for px, py in pts)
    return Skyline(
        path_d=path_d,
        fill_d=path_d + f" L{SKY_W} {SKY_H} L0 {SKY_H} Z",
        spike_d=f"M{spike_x0:g} 242 L{spike_tip[0]:g} 26 L{spike_tip[0] + 16:g} 252",
        windows="\n    ".join(win_rects),
        tip_fraction=tip_fraction,
    )


def skyline_stats_copy() -> str:
    chunks: list[str] = []
    for index, stat in enumerate(STATS):
        center = 600 + (index - 2) * 220
        chunks.append(
            f'<g transform="translate({center} 0)">'
            f'<text class="sky-value" x="0" y="122" text-anchor="middle">{escape(stat.value)}</text>'
            f'<text class="sky-label" x="0" y="150" text-anchor="middle">{escape(stat.label)}</text>'
            "</g>"
        )
    return "".join(chunks)


def skyline_svg(sky: Skyline, ink: str) -> str:
    pc = lambda f: round(f * 100, 2)
    # sweep head reaches the spire tip at tip_fraction of the (half-loop) sweep
    peak = pc(sky.tip_fraction * (1200 / SKY_PERIOD) * 0.5)
    title = "A slow heartbeat traces a city skyline, then drifts into GitHub stats"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SKY_W} {SKY_H}" width="{SKY_W}" height="{SKY_H}" role="img" aria-label="{escape(title)}">
  <title>{escape(title)}</title>
  <style>
    text {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }}
    .sky-value {{ fill: {ink}; font-size: 40px; font-weight: 700; letter-spacing: -1px; }}
    .sky-label {{ fill: {ink}; fill-opacity: 0.55; font-size: 12px; font-weight: 700; letter-spacing: 2px; }}
    .fillArea {{ fill: {ink}; fill-opacity: 0.07; }}
    .win {{ fill: {ink}; opacity: 0.16; }}
    .trace {{ stroke: {ink}; stroke-opacity: 0.32; }}
    .sweep, .glow {{
      stroke: {ink};
      stroke-dasharray: {SKY_DASH} {SKY_PERIOD - SKY_DASH};
      animation: sweep {SKY_DUR}s linear infinite;
    }}
    .glow {{ stroke-opacity: 0.55; }}
    .flash {{ stroke: {ink}; opacity: 0; animation: flash {SKY_DUR}s linear infinite; }}
    .city {{ animation: recede {SKY_DUR}s ease-in-out infinite; }}
    .stats {{ opacity: 0; animation: drift {SKY_DUR}s ease-in-out infinite; }}
    .tw {{ animation: twinkle 9s ease-in-out infinite alternate; }}
    .tw1 {{ animation-delay: -2.2s; animation-duration: 11s; }}
    .tw2 {{ animation-delay: -4.7s; animation-duration: 8s; }}
    .tw3 {{ animation-delay: -6.1s; animation-duration: 10s; }}
    .tw4 {{ animation-delay: -7.9s; animation-duration: 12s; }}
    @keyframes sweep {{
      0% {{ stroke-dashoffset: {SKY_DASH + SKY_PERIOD}; }}
      50%, 100% {{ stroke-dashoffset: {SKY_DASH}; }}
    }}
    @keyframes flash {{
      0%, {peak - 1.75}% {{ opacity: 0; }}
      {peak}% {{ opacity: 0.9; }}
      {peak + 0.5}% {{ opacity: 0.9; }}
      {peak + 4.5}%, 100% {{ opacity: 0; }}
    }}
    @keyframes recede {{
      0%, 50% {{ opacity: 1; }}
      58%, 84% {{ opacity: 0.18; }}
      94%, 100% {{ opacity: 1; }}
    }}
    @keyframes drift {{
      0%, 52% {{ opacity: 0; transform: translateY(10px); }}
      60% {{ opacity: 1; transform: translateY(0); }}
      84% {{ opacity: 1; transform: translateY(0); }}
      93%, 100% {{ opacity: 0; transform: translateY(-8px); }}
    }}
    @keyframes twinkle {{
      from {{ opacity: 0.1; }}
      to {{ opacity: 0.38; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      .sweep, .glow, .flash, .tw, .city, .stats {{ animation: none; }}
      .sweep {{ stroke-dasharray: none; stroke-opacity: 0.8; }}
      .glow, .flash {{ display: none; }}
      .city {{ opacity: 0.25; }}
      .stats {{ opacity: 1; }}
    }}
  </style>
  <defs>
    <filter id="blur" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="3.5"/>
    </filter>
  </defs>

  <g class="city">
    <path class="fillArea" d="{sky.fill_d}"/>
    <g class="win">
    {sky.windows}
    </g>
    <path class="trace" d="{sky.path_d}" fill="none" stroke-width="1.6"/>
  </g>

  <path class="glow"  d="{sky.path_d}" fill="none" stroke-width="7" pathLength="1200" filter="url(#blur)" stroke-linecap="round"/>
  <path class="sweep" d="{sky.path_d}" fill="none" stroke-width="2.4" pathLength="1200" stroke-linecap="round"/>
  <path class="flash" d="{sky.spike_d}" fill="none" stroke-width="5" filter="url(#blur)" stroke-linecap="round"/>

  <g class="stats">{skyline_stats_copy()}</g>
</svg>
'''


def write_skyline_svgs() -> None:
    sky = build_skyline()
    for name, ink in (("dark", "#f0f6fc"), ("light", "#0d1117")):
        path = ROOT / "assets" / f"heartbeat-skyline-stats-{name}.svg"
        path.write_text(skyline_svg(sky, ink), encoding="utf-8")
        print(f"generated {path.relative_to(ROOT)}")


def main() -> None:
    hearts = read_hearts()
    write_svg(hearts)
    print(f"generated {OUTPUT.relative_to(ROOT)} ({sum(map(len, hearts))} animated cells)")
    write_skyline_svgs()


if __name__ == "__main__":
    main()
