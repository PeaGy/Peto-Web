"""Ảnh gửi kèm: thu nhỏ, đổi ảnh chụp màn hình trong clipboard thành PNG, xoay theo EXIF, và nhận ra tệp kéo thả."""

from __future__ import annotations

import os
import struct
import zlib

import pytest

from peto_agent import images
from peto_agent.images import Image, ImageError

windows_only = pytest.mark.skipif(os.name != "nt", reason="giải mã ảnh dùng GDI+ của Windows")


def make_png(width: int, height: int, row, alpha: bool = False) -> bytes:
    """PNG không lọc; ``row(y)`` trả các điểm ảnh của hàng y (RGB, hoặc RGBA khi ``alpha``)."""
    raw = b"".join(b"\x00" + row(y) for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 6 if alpha else 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b"")


def png_header(data: bytes) -> tuple[int, int, int]:
    """(rộng, cao, số kênh) đọc từ IHDR."""
    assert data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR"
    width, height, _, color = struct.unpack(">IIBB", data[16:26])
    return width, height, {2: 3, 6: 4}[color]


def read_png(data: bytes) -> list[bytes]:
    """Giải mã các hàng điểm ảnh của PNG 8 bit RGB/RGBA mà GDI+ ghi ra, gồm cả năm kiểu lọc. Chỉ dùng cho ảnh nhỏ."""
    width, height, channels = png_header(data)
    position, idat = 8, b""
    while position < len(data):
        length = struct.unpack(">I", data[position:position + 4])[0]
        if data[position + 4:position + 8] == b"IDAT":
            idat += data[position + 8:position + 8 + length]
        position += 12 + length
    raw, rows, stride = zlib.decompress(idat), [], width * channels
    previous = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            left = line[i - channels] if i >= channels else 0
            up, corner = previous[i], previous[i - channels] if i >= channels else 0
            if kind == 1:
                line[i] = (line[i] + left) & 255
            elif kind == 2:
                line[i] = (line[i] + up) & 255
            elif kind == 3:
                line[i] = (line[i] + (left + up) // 2) & 255
            elif kind == 4:
                guess = left + up - corner
                nearest = min((abs(guess - left), 0, left), (abs(guess - up), 1, up), (abs(guess - corner), 2, corner))
                line[i] = (line[i] + nearest[2]) & 255
        rows.append(bytes(line))
        previous = line
    return rows


def pixel(rows: list[bytes], channels: int, x: int, y: int) -> tuple[int, ...]:
    return tuple(rows[y][x * channels:(x + 1) * channels])


def close(actual: tuple[int, ...], expected: tuple[int, ...], tolerance: int = 6) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(actual, expected, strict=True))


def encode_jpeg(png: bytes) -> bytes:
    gdi = images._gdiplus()
    ctypes = gdi.ctypes
    stream = gdi.shlwapi.SHCreateMemStream(png, len(png))
    bitmap = ctypes.c_void_p()
    assert gdi.gdiplus.GdipCreateBitmapFromStream(stream, ctypes.byref(bitmap)) == 0
    try:
        return gdi._encode(bitmap, images.JPEG_ENCODER, 90)
    finally:
        gdi.gdiplus.GdipDisposeImage(bitmap)
        gdi._release(stream)


@windows_only
def test_small_images_are_sent_unchanged_and_large_ones_scaled_to_2000px():
    small = make_png(64, 32, lambda y: bytes(v for x in range(64) for v in (x * 3, y * 7, 90)))
    image = images.prepare(small)
    assert image == Image(small, "image/png", 64, 32)
    assert image.data_url().startswith("data:image/png;base64,iVBORw0KGgo")

    tall = images.prepare(make_png(1000, 3000, lambda y: bytes((90, 90, 90)) * 1000))
    assert (tall.mime, tall.width, tall.height) == ("image/png", 667, 2000)
    assert png_header(tall.data) == (667, 2000, 3)

    half = bytes((200, 30, 30)) * 1200 + bytes((30, 30, 200)) * 1200
    image = images.prepare(make_png(2400, 30, lambda y: half))
    assert (image.width, image.height) == (2000, 25)
    rows = read_png(image.data)
    assert close(pixel(rows, 3, 10, 12), (200, 30, 30)) and close(pixel(rows, 3, 1990, 12), (30, 30, 200))
    assert close(pixel(rows, 3, 0, 0), (200, 30, 30)), "mép ảnh thu nhỏ không bị viền tối"


@windows_only
def test_clipboard_screenshots_become_opaque_pngs_the_right_way_up():
    # Ảnh chụp màn hình trong clipboard: DIB 32 bit, hàng dưới cùng đứng trước, kênh alpha bằng 0.
    red_row, blue_row = bytes((0, 0, 255, 0)) * 5, bytes((255, 0, 0, 0)) * 5
    header = struct.pack("<IiiHHIIiiII", 40, 5, 2, 1, 32, 0, 0, 0, 0, 0, 0)
    image = images.prepare(images.dib_to_bmp(header + blue_row + red_row))
    assert image.mime == "image/png" and png_header(image.data) == (5, 2, 3), "không thành ảnh trong suốt"
    rows = read_png(image.data)
    assert close(pixel(rows, 3, 0, 0), (255, 0, 0)) and close(pixel(rows, 3, 4, 1), (0, 0, 255))

    # DIB 24 bit (mỗi hàng đệm cho tròn 4 byte) và DIB 32 bit có mặt nạ màu BI_BITFIELDS.
    header = struct.pack("<IiiHHIIiiII", 40, 3, 1, 1, 24, 0, 0, 0, 0, 0, 0)
    green = images.prepare(images.dib_to_bmp(header + bytes((0, 200, 0)) * 3 + bytes(3)))
    assert close(pixel(read_png(green.data), 3, 2, 0), (0, 200, 0))
    masks = struct.pack("<III", 0x00FF0000, 0x0000FF00, 0x000000FF)
    header = struct.pack("<IiiHHIIiiII", 40, 2, 1, 1, 32, 3, 0, 0, 0, 0, 0)
    bmp = images.dib_to_bmp(header + masks + bytes((10, 20, 30, 0)) * 2)
    assert int.from_bytes(bmp[10:14], "little") == 14 + 40 + 12
    assert close(pixel(read_png(images.prepare(bmp).data), 3, 1, 0), (30, 20, 10))


@windows_only
def test_transparency_survives_scaling():
    row = bytes((0, 0, 0, 0)) * 1200 + bytes((250, 180, 0, 255)) * 1200
    image = images.prepare(make_png(2400, 8, lambda y: row, alpha=True))
    assert png_header(image.data) == (2000, 7, 4)
    rows = read_png(image.data)
    assert pixel(rows, 4, 5, 3)[3] == 0 and close(pixel(rows, 4, 1990, 3), (250, 180, 0, 255))


@windows_only
def test_heavy_images_switch_to_jpeg_or_shrink_until_they_fit(monkeypatch):
    monkeypatch.setattr(images, "MAX_IMAGE_BYTES", 400 * 1024)
    monkeypatch.setattr(images, "PNG_PREFERRED_BYTES", 100 * 1024)
    noise = [os.urandom(900 * 3) for _ in range(700)]
    image = images.prepare(make_png(900, 700, lambda y: noise[y]))
    assert image.mime == "image/jpeg" and image.data.startswith(b"\xff\xd8\xff") and len(image.data) <= 400 * 1024
    assert image.width <= 900 and image.width / image.height == pytest.approx(900 / 700, rel=0.01)


@windows_only
def test_exif_orientation_is_applied():
    jpeg = encode_jpeg(make_png(40, 20, lambda y: bytes(v for x in range(40) for v in (x * 6, 0, 0))))
    ifd = struct.pack("<H", 1) + struct.pack("<HHIHH", 0x0112, 3, 1, 6, 0) + struct.pack("<I", 0)
    exif = b"Exif\x00\x00" + b"II*\x00" + struct.pack("<I", 8) + ifd
    rotated = jpeg[:2] + b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif + jpeg[2:]
    assert images.prepare(jpeg).width == 40
    image = images.prepare(rotated)
    assert (image.width, image.height) == (20, 40), "ảnh điện thoại chụp dọc không bị nằm ngang"


def test_webp_is_sent_as_is_and_other_data_is_refused(monkeypatch):
    webp = b"RIFF\x24\x00\x00\x00WEBPVP8 " + bytes(32)
    assert images.prepare(webp) == Image(webp, "image/webp", 0, 0)
    monkeypatch.setattr(images, "MAX_IMAGE_BYTES", 16)
    with pytest.raises(ImageError, match="WebP"):
        images.prepare(webp)
    with pytest.raises(ImageError, match="Không đọc được ảnh"):
        images.prepare(b"%PDF-1.7 khong phai anh")


def test_dropped_files_are_recognized_only_when_the_paste_is_just_image_paths(tmp_path):
    spaced, plain = tmp_path / "ảnh chụp.png", tmp_path / "loi.JPG"
    spaced.write_bytes(b"x")
    plain.write_bytes(b"x")
    assert images.dropped_paths(f'"{spaced}" {plain}') == [spaced, plain]
    assert images.dropped_paths(f"'{spaced}'") == [spaced]
    for text in (f"sửa {plain}", "loi.JPG", str(tmp_path / "chua-co.png"), str(tmp_path), f"{plain}\n{plain}",
                 str(tmp_path / "ghi-chu.txt")):
        assert images.dropped_paths(text) == []

    broken = tmp_path / "hong.png"
    broken.write_bytes(b"khong phai anh")
    with pytest.raises(ImageError, match="^hong.png: "):
        images.from_files([broken])
