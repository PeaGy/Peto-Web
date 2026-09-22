"""Sinh peto_agent/mascot.py từ ảnh mascot: ký tự khối có màu, chủ web chọn từ ảnh xem trước ngày 2026-09-22.

Chỉ dùng lúc phát triển (cần Pillow); CLI khi chạy chỉ đọc dữ liệu đã sinh nên vẫn thuần thư viện chuẩn, và thư mục
tools/ không nằm trong wheel. Đổi ảnh hay cỡ trong SIZES rồi chạy lại:

    .venv/Scripts/python.exe agent-cli/tools/make_mascot.py

Mỗi ô chọn một ký tự khối (nửa ô, góc tư, khối 1/8) cùng hai màu sao cho gần ảnh nhất. Windows Terminal và VS Code
tự vẽ nhóm ký tự U+2580–U+259F thành hình chữ nhật lấp kín ô thay vì lấy từ font, nên máy nào cũng ra như ảnh xem
trước. Chữ Braille thì ngược lại: chấm lấy từ font, nhỏ và thưa, nên bản Braille trước đó trông vỡ hạt trên terminal
thật. Phần trong suốt để trống cho màu nền của terminal hiện ra. Nét viền tối của ảnh vẽ tay được làm dày trước khi
thu nhỏ, để còn thấy mắt và miệng.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageFilter

HERE = Path(__file__).resolve().parent
TARGET = HERE.parent / "peto_agent" / "mascot.py"
# Các cỡ từ lớn đến nhỏ: (ảnh trong tools/, số cột, có làm dày nét viền không). Hai cỡ đầu là ảnh vẽ tay; quả lê là
# pixel art sẵn nét viền một điểm ảnh nên giữ nguyên, cỡ 6 cột chủ web chọn cho terminal thấp như bảng của VS Code.
SIZES = (("mascot.png", 24, True), ("mascot.png", 18, True), ("pear.png", 6, False))
# Ô terminal cao gấp đôi bề ngang (Windows Terminal đúng 1:2, VS Code hơi cao hơn).
CELL_ASPECT = 2.0
# Mỗi ô lấy 8×16 mẫu, đủ mịn cho khối 1/8 theo cả hai chiều.
SAMPLES_X, SAMPLES_Y = 8, 16
# Nền terminal giả định khi tính sai số cho phần trong suốt (terminal nền tối).
TERMINAL_BG = (18, 18, 18)
# Độ sáng dưới ngần này là nét viền (áo xám tối của mascot sáng hơn, không bị tính là viền).
OUTLINE_DARK = 40
SATURATION, CONTRAST = 1.2, 1.08

E = 1 / 8
# Hình của từng ký tự khối: các hình chữ nhật (x0, y0, x1, y1) theo tỉ lệ ô. Không dùng ░▒▓ vì chúng là hoa văn chấm.
SHAPES: dict[str, tuple[tuple[float, float, float, float], ...]] = {
    "▀": ((0, 0, 1, .5),), "▄": ((0, .5, 1, 1),), "▌": ((0, 0, .5, 1),), "▐": ((.5, 0, 1, 1),),
    "▔": ((0, 0, 1, E),), "▕": ((1 - E, 0, 1, 1),),
    "▖": ((0, .5, .5, 1),), "▗": ((.5, .5, 1, 1),), "▘": ((0, 0, .5, .5),), "▝": ((.5, 0, 1, .5),),
    "▙": ((0, 0, .5, 1), (.5, .5, 1, 1)), "▛": ((0, 0, 1, .5), (0, .5, .5, 1)),
    "▜": ((0, 0, 1, .5), (.5, .5, 1, 1)), "▟": ((.5, 0, 1, 1), (0, .5, .5, 1)),
    "▚": ((0, 0, .5, .5), (.5, .5, 1, 1)), "▞": ((.5, 0, 1, .5), (0, .5, .5, 1)),
    **{char: ((0, 1 - k * E, 1, 1),) for k, char in enumerate("▁▂▃", start=1)},
    **{char: ((0, 1 - k * E, 1, 1),) for k, char in enumerate("▅▆▇", start=5)},
    **{char: ((0, 0, k * E, 1),) for k, char in enumerate("▏▎▍", start=1)},
    **{char: ((0, 0, k * E, 1),) for k, char in enumerate("▋▊▉", start=5)},
}
# Hai ký tự chéo trông lấm tấm hơn, chỉ chọn khi rõ ràng khớp hơn hẳn.
PENALTY = {"▚": 1.25, "▞": 1.25}

Sample = tuple[tuple[int, int, int], float, tuple[float, float, float]]
Cell = tuple[str, int | None, int | None]


def luminance(red: int, green: int, blue: int) -> float:
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def prepare(path: Path, columns: int, outline: bool) -> Image.Image:
    """Cắt sát hình, làm dày nét viền theo tỉ lệ thu nhỏ, rồi tăng màu một chút cho khỏi đục khi gộp điểm ảnh."""
    image = Image.open(path).convert("RGBA")
    image = image.crop(image.getbbox())
    thicken = round(image.width / columns / 8) if outline else 0
    if thicken:
        pixels = image.load()
        outline = Image.new("L", image.size, 0)
        marks = outline.load()
        total, count = [0, 0, 0], 0
        for y in range(image.height):
            for x in range(image.width):
                red, green, blue, alpha = pixels[x, y]
                if alpha >= 128 and luminance(red, green, blue) < OUTLINE_DARK:
                    marks[x, y] = 255
                    total = [total[0] + red, total[1] + green, total[2] + blue]
                    count += 1
        if count:
            ink = (*(round(channel / count) for channel in total), 255)
            grown = outline.filter(ImageFilter.MaxFilter(thicken * 2 + 1))
            # Chỉ dày vào trong hình, không lấn ra phần trong suốt.
            inside = image.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
            image.paste(Image.new("RGBA", image.size, ink), (0, 0), ImageChops.multiply(grown, inside))
    alpha = image.getchannel("A")
    colored = ImageEnhance.Contrast(ImageEnhance.Color(image.convert("RGB")).enhance(SATURATION)).enhance(CONTRAST)
    colored = colored.convert("RGBA")
    colored.putalpha(alpha)
    return colored


def masks() -> dict[str, list[bool]]:
    result = {}
    for char, rects in SHAPES.items():
        result[char] = [any(x0 <= (i + .5) / SAMPLES_X < x1 and y0 <= (j + .5) / SAMPLES_Y < y1
                            for x0, y0, x1, y1 in rects)
                        for j in range(SAMPLES_Y) for i in range(SAMPLES_X)]
    return result


def mean(region: list[Sample]) -> tuple[float, float, float] | None:
    """Màu trung bình theo độ đục, để phần gần trong suốt không kéo màu về phía nền."""
    weight = sum(alpha for _, alpha, _ in region)
    if weight <= 0:
        return None
    return tuple(sum(color[index] * alpha for color, alpha, _ in region) / weight for index in range(3))


def error(region: list[Sample], color: tuple[float, float, float] | None) -> float:
    """Sai số khi tô vùng bằng một màu; None nghĩa là để trống cho nền terminal hiện ra."""
    shown = TERMINAL_BG if color is None else color
    return sum((seen[0] - shown[0]) ** 2 + (seen[1] - shown[1]) ** 2 + (seen[2] - shown[2]) ** 2
               for _, _, seen in region)


def pack(color: tuple[float, float, float] | None) -> int | None:
    if color is None:
        return None
    red, green, blue = (min(255, max(0, round(channel))) for channel in color)
    return red << 16 | green << 8 | blue


def fit(samples: list[Sample], shapes: dict[str, list[bool]]) -> Cell:
    """Chọn ký tự và hai màu cho một ô, gồm cả để trống và tô kín cả ô."""
    whole = mean(samples)
    best = (error(samples, None), " ", None, None)
    if whole is not None and error(samples, whole) < best[0]:
        # Cả ô một màu: dùng màu nền của dấu cách, cách chắc chắn nhất để lấp kín ô.
        best = (error(samples, whole), " ", None, whole)
    for char, shape in shapes.items():
        inside = [sample for sample, on in zip(samples, shape) if on]
        outside = [sample for sample, on in zip(samples, shape) if not on]
        fg = mean(inside)
        if fg is None:
            continue
        cost = error(inside, fg)
        factor = PENALTY.get(char, 1.0)
        bg = mean(outside)
        if bg is not None:
            total = (cost + error(outside, bg)) * factor
            if total < best[0]:
                best = (total, char, fg, bg)
        total = (cost + error(outside, None)) * factor
        if total < best[0]:
            best = (total, char, fg, None)
    _, char, fg, bg = best
    return char, pack(fg), pack(bg)


def convert(path: Path, columns: int, outline: bool = True) -> list[list[Cell]]:
    image = prepare(path, columns, outline)
    rows = max(1, round(image.height / image.width * columns / CELL_ASPECT))
    small = image.convert("RGBa").resize((columns * SAMPLES_X, rows * SAMPLES_Y), Image.BOX).convert("RGBA")
    pixels = small.load()
    shapes = masks()
    art = []
    for row in range(rows):
        line = []
        for column in range(columns):
            samples: list[Sample] = []
            for j in range(SAMPLES_Y):
                for i in range(SAMPLES_X):
                    red, green, blue, alpha = pixels[column * SAMPLES_X + i, row * SAMPLES_Y + j]
                    share = alpha / 255
                    seen = tuple(channel * share + back * (1 - share)
                                 for channel, back in zip((red, green, blue), TERMINAL_BG))
                    samples.append(((red, green, blue), share, seen))
            if all(share < 0.15 for _, share, _ in samples):
                line.append((" ", None, None))
            else:
                line.append(fit(samples, shapes))
        art.append(line)
    return art


def render(arts: list[tuple[str, list[list[Cell]]]]) -> str:
    def value(item: int | None) -> str:
        return "None" if item is None else f"0x{item:06X}"

    sources = ", ".join(dict.fromkeys(source for source, _ in arts))
    lines = [
        '"""Mascot của Peto ở đầu phiên: ký tự khối có màu, mỗi ô là (ký tự, màu chữ, màu nền), màu dạng 0xRRGGBB.',
        "",
        f"Sinh bằng agent-cli/tools/make_mascot.py từ {sources}; đừng sửa tay, chạy lại công cụ đó khi đổi ảnh.",
        "Các cỡ xếp từ lớn đến nhỏ; đầu phiên dùng cỡ lớn nhất vừa cửa sổ.",
        '"""',
        "",
        "ARTS = (",
    ]
    for source, art in arts:
        lines.append(f"    (  # {source}, {len(art[0])} cột × {len(art)} dòng")
        for line in art:
            cells = ", ".join(f'("{char}", {value(fg)}, {value(bg)})' for char, fg, bg in line)
            lines.append(f"        ({cells}),")
        lines.append("    ),")
    lines += [")", ""]
    return "\n".join(lines)


def main() -> None:
    arts = [(name, convert(HERE / name, columns, outline)) for name, columns, outline in SIZES]
    TARGET.write_text(render(arts), encoding="utf-8")
    sizes = ", ".join(f"{name} {len(art[0])} cột × {len(art)} dòng" for name, art in arts)
    print(f"Đã ghi {TARGET.name}: {sizes}")


if __name__ == "__main__":
    main()
