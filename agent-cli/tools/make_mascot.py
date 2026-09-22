"""Sinh peto_agent/mascot.py từ ảnh mascot: chữ Braille có màu, kiểu chủ web chọn ngày 2026-09-22.

Chỉ dùng lúc phát triển (cần Pillow); CLI khi chạy chỉ đọc dữ liệu đã sinh nên vẫn thuần thư viện chuẩn, và thư mục
tools/ không nằm trong wheel. Chạy lại khi đổi ảnh hay đổi cỡ:

    .venv/Scripts/python.exe agent-cli/tools/make_mascot.py [ảnh.png] [số cột]

Kiểu "viền chấm + tô nền": trong mỗi ô 2×4 chấm, chấm là nét viền tối, còn phần tô (tóc, mặt, áo) thành màu nền của
ô. Ô ở mép hình không tô nền, vì phần trong suốt phải giữ màu nền của terminal; ở đó chấm vẽ theo dáng hình bằng màu
phần tô, để trên terminal nền tối hình không mất viền.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
DEFAULT_IMAGE = HERE / "mascot.png"
TARGET = HERE.parent / "peto_agent" / "mascot.py"
DEFAULT_COLUMNS = 18
# Độ sáng dưới ngần này là nét viền; tỉ lệ điểm tối trong một chấm từ ngần này trở lên thì bật chấm.
DARK = 70
DARK_SHARE = 0.22
# Tỉ lệ điểm đục để coi là có hình (chấm ở mép), và để coi cả ô nằm trong hình (được tô nền).
OPAQUE_SHARE = 0.35
INSIDE_SHARE = 0.9
# Thứ tự bit của chữ Braille: (cột, hàng, bit).
BRAILLE_BITS = ((0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08), (1, 1, 0x10), (1, 2, 0x20),
                (0, 3, 0x40), (1, 3, 0x80))


def luminance(red: int, green: int, blue: int) -> float:
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def convert(path: Path, columns: int) -> list[list[tuple[str, int | None, int | None]]]:
    image = Image.open(path).convert("RGBA")
    image = image.crop(image.getbbox())
    width, height = image.size
    pixels = image.load()
    rows = math.ceil(height * columns * 2 / width / 4)
    step_x, step_y = width / (columns * 2), height / (rows * 4)

    def dot(x0: float, y0: float) -> tuple[int, int, int, list[int], int, list[int]]:
        total = opaque = dark = fill = 0
        dark_sum, fill_sum = [0, 0, 0], [0, 0, 0]
        for y in range(int(y0), max(int(y0) + 1, int(y0 + step_y))):
            for x in range(int(x0), max(int(x0) + 1, int(x0 + step_x))):
                if x >= width or y >= height:
                    continue
                total += 1
                red, green, blue, alpha = pixels[x, y]
                if alpha < 128:
                    continue
                opaque += 1
                is_dark = luminance(red, green, blue) < DARK
                sums = dark_sum if is_dark else fill_sum
                sums[0] += red
                sums[1] += green
                sums[2] += blue
                if is_dark:
                    dark += 1
                else:
                    fill += 1
        return total, opaque, dark, dark_sum, fill, fill_sum

    def color(sums: list[int], count: int) -> int | None:
        if not count:
            return None
        red, green, blue = (round(channel / count) for channel in sums)
        return red << 16 | green << 8 | blue

    art = []
    for row in range(rows):
        line = []
        for column in range(columns):
            cell_total = cell_opaque = dark_count = fill_count = 0
            dark_sum, fill_sum = [0, 0, 0], [0, 0, 0]
            dots = []
            for dx, dy, bit in BRAILLE_BITS:
                total, opaque, dark, dsum, fill, fsum = dot((column * 2 + dx) * step_x, (row * 4 + dy) * step_y)
                dots.append((bit, total, opaque, dark))
                cell_total += total
                cell_opaque += opaque
                dark_count += dark
                fill_count += fill
                for index in range(3):
                    dark_sum[index] += dsum[index]
                    fill_sum[index] += fsum[index]
            if not cell_opaque:
                line.append((" ", None, None))
                continue
            fill_color = color(fill_sum, fill_count)
            if cell_opaque >= INSIDE_SHARE * cell_total and fill_color is not None:
                code = sum(bit for bit, total, _, dark in dots if total and dark / total >= DARK_SHARE)
                line.append((chr(0x2800 + code) if code else " ", color(dark_sum, dark_count) or 0x141414, fill_color))
            else:
                code = sum(bit for bit, total, opaque, _ in dots if total and opaque / total >= OPAQUE_SHARE)
                line.append((chr(0x2800 + code) if code else " ", fill_color or 0x5A5A5A, None))
        art.append(line)
    return art


def render(art: list[list[tuple[str, int | None, int | None]]], source: str) -> str:
    def value(item: int | None) -> str:
        return "None" if item is None else f"0x{item:06X}"

    rows = []
    for line in art:
        cells = ", ".join(f'("{char}", {value(fg)}, {value(bg)})' for char, fg, bg in line)
        rows.append(f"    ({cells}),")
    return "\n".join([
        '"""Mascot của Peto ở đầu phiên: chữ Braille có màu, mỗi ô là (ký tự, màu chữ, màu nền), màu dạng 0xRRGGBB.',
        "",
        f"Sinh bằng agent-cli/tools/make_mascot.py từ {source}; đừng sửa tay, chạy lại công cụ đó khi đổi ảnh.",
        '"""',
        "",
        "ART = (",
        *rows,
        ")",
        "",
    ])


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMAGE
    columns = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_COLUMNS
    art = convert(path, columns)
    TARGET.write_text(render(art, path.name), encoding="utf-8")
    print(f"Đã ghi {TARGET.name}: {columns} cột × {len(art)} dòng")


if __name__ == "__main__":
    main()
