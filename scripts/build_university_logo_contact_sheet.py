"""Build contact sheets for visually auditing university logo assets."""

from __future__ import annotations

import argparse
import csv
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "data" / "master" / "university_logos.csv"


def build_contact_sheets(output_dir: Path, page_size: int = 60) -> list[Path]:
    with METADATA.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    output_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default()
    outputs: list[Path] = []
    columns = 10
    cell_width, cell_height = 120, 150

    for page in range(math.ceil(len(rows) / page_size)):
        subset = rows[page * page_size : (page + 1) * page_size]
        sheet = Image.new(
            "RGB",
            (columns * cell_width, math.ceil(len(subset) / columns) * cell_height),
            "white",
        )
        draw = ImageDraw.Draw(sheet)

        for index, row in enumerate(subset):
            x = (index % columns) * cell_width
            y = (index // columns) * cell_height
            asset = ROOT / row["logo_path"].lstrip("/").replace("/", os.sep)
            try:
                logo = Image.open(asset)
                logo.seek(0)
                logo.thumbnail((100, 100))
                if logo.mode in {"RGBA", "LA", "P"}:
                    background = Image.new("RGBA", logo.size, "white")
                    background.alpha_composite(logo.convert("RGBA"))
                    logo = background.convert("RGB")
                else:
                    logo = logo.convert("RGB")
                sheet.paste(
                    logo,
                    (x + 10 + (100 - logo.width) // 2, y + 5 + (100 - logo.height) // 2),
                )
            except Exception:
                draw.rectangle((x + 10, y + 5, x + 110, y + 105), outline="red")
                draw.text((x + 45, y + 45), "SVG", fill="red", font=font)

            draw.text((x + 8, y + 108), row["school_code"], fill="black", font=font)
            draw.text((x + 8, y + 122), row["status"][:18], fill=(90, 90, 90), font=font)

        output = output_dir / f"university-logos-{page + 1}.jpg"
        sheet.save(output, quality=90)
        outputs.append(output)

    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--page-size", type=int, default=60)
    args = parser.parse_args()
    for output in build_contact_sheets(args.output_dir, args.page_size):
        print(output)


if __name__ == "__main__":
    main()
