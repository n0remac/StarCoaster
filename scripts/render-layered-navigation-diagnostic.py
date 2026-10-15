#!/usr/bin/env python3
"""Render the bridge's traced native mask and its blocking causes as SVG."""

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape


REGIONS = (("Coaster: high rail, low rail, station, loop", 14, 29, 38, 33),
           ("Footpaths: low overhead and layered bridge", 44, 55, 51, 59))
COLORS = {"track": "#db5550", "path": "#e6a13b", "wall": "#9068b2",
          "cliff": "#5277bd", "legacy": "#777b83", "terrain": "#495970"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagnostic", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.diagnostic.read_text())
    bits = bytes.fromhex(data["mask_hex"])
    width = data["native_width"] * 4
    offset_x = (data["native_width"] - data["park_width"]) // 2
    offset_y = (data["native_height"] - data["park_height"]) // 2
    causes = data.get("causes") or {}
    output = args.output or args.diagnostic.with_suffix(".svg")
    scale = 9
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" width="980" height="480" viewBox="0 0 980 480">',
             '<rect width="980" height="480" fill="#f5f3ee"/>',
             f'<text x="22" y="29" font-size="18" font-family="sans-serif">Ground mask revision {data["revision"]} · {data["hash"]}</text>',
             '<text x="22" y="49" font-size="11" font-family="sans-serif">Each square is one native 8-pixel walk cell. Hover for blocking causes.</text>']
    y_origin = 80
    for title, x0, y0, x1, y1 in REGIONS:
        lines.append(f'<text x="22" y="{y_origin-10}" font-size="13" font-family="sans-serif">{escape(title)}</text>')
        for ty in range(y0, y1):
            for tx in range(x0, x1):
                for sy in range(4):
                    for sx in range(4):
                        wx, wy = (tx + offset_x) * 4 + sx, (ty + offset_y) * 4 + sy
                        index = wy * width + wx
                        blocked = bool(bits[index // 8] & (1 << (index % 8)))
                        reasons = causes.get(str(index), [])
                        reason = ", ".join(reasons) if reasons else "terrain or map boundary" if blocked else "clear"
                        if not blocked:
                            color = "#f9fff7"
                        elif any("track:" in item for item in reasons):
                            color = COLORS["track"]
                        elif any(item.startswith("path:") for item in reasons):
                            color = COLORS["path"]
                        elif any("wall:" in item for item in reasons):
                            color = COLORS["wall"]
                        elif "cliff" in reasons:
                            color = COLORS["cliff"]
                        elif reasons:
                            color = COLORS["legacy"]
                        else:
                            color = COLORS["terrain"]
                        px = 22 + ((tx-x0)*4+sx)*scale
                        py = y_origin + ((ty-y0)*4+sy)*scale
                        lines.append(f'<rect x="{px}" y="{py}" width="{scale-1}" height="{scale-1}" fill="{color}"><title>{escape(str(tx)+","+str(ty)+" / "+reason)}</title></rect>')
        y_origin += (y1-y0)*4*scale + 50
    lines.append('<text x="22" y="460" font-size="11" font-family="sans-serif">Red track · amber raised path · purple wall · blue cliff · gray other or terrain · white clear</text>')
    lines.append('</svg>')
    output.write_text("\n".join(lines) + "\n")
    print(output)


if __name__ == "__main__":
    main()
