"""Export the retained run's recorded scenes for the README; no simulation or model calls.

Requires Pillow (the exported artifacts record the version used). Example:
  .venv/bin/python scripts/render_percolation_highlight.py RUN_DIRECTORY
"""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PIL import __version__ as pillow_version

WIDTH, HEIGHT = 1200, 940
INK, MUTED = "#142a3b", "#536779"
COLORS = {
    "control": "#087f99",
    "proposed": "#8251bc",
    "field": "#b4c4ce",
    "muted": "#d1dbe2",
    "truth": "#b56a08",
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def font(size, bold=False):
    names = [
        f"/System/Library/Fonts/Supplemental/Arial{' Bold' if bold else ''}.ttf",
        f"DejaVuSans{'-Bold' if bold else ''}.ttf",
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def render(process, index):
    image = Image.new("RGB", (WIDTH, HEIGHT), "#f4f7fa")
    draw = ImageDraw.Draw(image)

    def text(x, y, value, size=18, color=INK, bold=False):
        draw.text((x, y), value, font=font(size, bold), fill=color)

    text(40, 28, "OMNILAB  /  FROM PAPER TO EXECUTED EXPLORATION", 15, COLORS["control"], True)
    text(40, 62, "Does street direction change connectivity?", 36, bold=True)
    text(
        40,
        111,
        "Agent-written simulation  ·  Final follow-up  ·  First recorded paired seed",
        21,
        MUTED,
    )
    probability = process["times"][index]
    text(40, 157, f"Bond occupation probability  p = {probability:.2f}", 23, bold=True)
    text(763, 163, "21 computed states  ·  p = 0 to 1", 18, MUTED)
    draw.line((40, 210, 1160, 210), fill="#d6e0e7", width=5)
    for p in process["times"]:
        x = 40 + 1120 * p
        draw.ellipse((x - 3, 207, x + 3, 213), fill="#8ea7b7")
    x = 40 + 1120 * probability
    draw.ellipse((x - 8, 202, x + 8, 218), fill=COLORS["control"])

    for arm, left, label, subtitle, color in [
        (
            "original",
            40,
            "Alternating streets",
            "Neighboring rows and columns alternate",
            "control",
        ),
        (
            "proposed",
            612,
            "Random whole streets",
            "Positive-direction probability = 0.75",
            "proposed",
        ),
    ]:
        world = process[arm]
        frame = world["frames"][index]
        draw.rounded_rectangle((left, 242, left + 548, 742), radius=16, fill="white")
        text(left + 24, 262, label, 25, COLORS[color], True)
        text(left + 24, 299, subtitle, 18, MUTED)
        x0, x1, y0, y1 = process["bounds"]
        scale = 320 / (x1 - x0)

        def point(x, y, left=left, x0=x0, y0=y0, scale=scale):
            return left + 114 + (x - x0) * scale, 665 - (y - y0) * scale

        draw.rectangle((*point(x0, y1), *point(x1, y0)), outline="#dce5eb", width=1)
        for glyph in world["geometry"] + frame["glyphs"]:
            if glyph["start"] > index:
                continue
            fill = COLORS["truth" if index in glyph["highlight"] else glyph["color"]]
            ax, ay = point(glyph["x"], glyph["y"])
            if glyph["kind"] == "circle":
                radius = max(1, glyph["radius"] * scale)
                box = (ax - radius, ay - radius, ax + radius, ay + radius)
                draw.ellipse(box, fill=fill if glyph["filled"] else None, outline=fill)
            else:
                bx, by = point(glyph["x2"], glyph["y2"])
                draw.line((ax, ay, bx, by), fill=fill, width=1)
                if glyph["kind"] == "arrow":
                    angle = math.atan2(by - ay, bx - ax)
                    length = min(4, math.hypot(bx - ax, by - ay) * 0.35)
                    draw.polygon(
                        [(bx, by)]
                        + [
                            (bx - length * math.cos(angle + a), by - length * math.sin(angle + a))
                            for a in (-0.5, 0.5)
                        ],
                        fill=fill,
                    )
        count = re.search(r"largest SCC=(\d+)/256", frame["caption"])
        if count is None:
            raise ValueError("Expected the recorded 16 by 16 percolation scene")
        text(left + 24, 688, f"Largest connected component: {count[1]} / 256 sites", 20, bold=True)

    text(
        40,
        761,
        "Colored sites are mutually reachable along directed bonds. "
        "Same occupied bonds in both arms.",
        18,
        MUTED,
    )
    text(
        40,
        790,
        "Recorded 16 × 16 scene; the experiment also measures 32 × 32. "
        "Probability is not physical time.",
        18,
        MUTED,
    )
    draw.rounded_rectangle((40, 834, 1160, 912), radius=12, fill="#e5edf4")
    text(60, 848, "MEASUREMENTS CHANGED THE NEXT ACTION", 13, COLORS["control"], True)
    text(
        60,
        877,
        "4 pairs: screen     →     8 fresh pairs: precision     →     "
        "8 pairs: bias test     →     stop",
        22,
        bold=True,
    )
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, default=Path("docs/assets"))
    args = parser.parse_args()
    run, destination = args.run, args.output
    artifact = json.loads((run / "comparison/process.json").read_text())
    report = json.loads((run / "report.json").read_text())
    process = artifact["process"]
    if artifact["status"] != "ready" or process["times"] != [i / 20 for i in range(21)]:
        raise ValueError("Expected all 21 recorded probability samples")
    if (
        report["final_experiment"] != 3
        or report["rounds"][-1]["treatment"].get("positive_direction_probability") != 0.75
    ):
        raise ValueError(
            "This highlight describes the retained run's third, biased-street comparison"
        )
    destination.mkdir(parents=True, exist_ok=True)
    frames = [render(process, index) for index in range(len(process["times"]))]
    png, gif = [destination / f"percolation-exploration.{suffix}" for suffix in ("png", "gif")]
    frames[15].save(png)
    frames[0].save(
        gif,
        save_all=True,
        append_images=frames[1:],
        duration=[900] + [450] * 19 + [1600],
        loop=0,
        disposal=2,
    )
    provenance = {
        "run_id": run.name,
        "source_run": str(run),
        "renderer": str(Path(__file__).relative_to(Path.cwd())),
        "renderer_sha256": digest(Path(__file__)),
        "pillow_version": pillow_version,
        "selection": process["selection"],
        "scene_inputs": process["inputs"],
        "frame_values": process["times"],
        "poster_frame_value": process["times"][15],
        "limitations": "Recorded simulation states, not physical motion or independent validation. "
        "The poster is p=0.75 for the first paired seed; it is not an aggregate result. "
        "The GIF displays every recorded frame without interpolation. "
        "The initial direction is recorded as user_suggestion; agents implement and extend it.",
        "input_sha256": {
            name: digest(run / name)
            for name in [
                "manifest.json",
                "comparison/process.json",
                "report.json",
                "code/experiment.py",
                "rounds/03/trials.json",
            ]
        },
        "figure_sha256": {p.name: digest(p) for p in [gif, png]},
        "rounds": [
            {
                "round": r["round"],
                "summary": r["summary"],
                "action": r["next_decision"]["action"],
                "next_experiment": r["next_decision"]["next_experiment"],
            }
            for r in report["rounds"]
        ],
    }
    (destination / "percolation-exploration.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )
    print(f"Exported {len(frames)} recorded frames and a static poster to {destination}")


if __name__ == "__main__":
    main()
