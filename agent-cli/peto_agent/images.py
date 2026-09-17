"""Ảnh gửi kèm tin nhắn: lấy từ clipboard (Alt+V) hoặc tệp kéo thả vào terminal, thu nhỏ ảnh lớn rồi mã hóa lại.

Chỉ dùng thư viện chuẩn. Clipboard đọc qua user32 và shell32; giải mã, thu nhỏ và mã hóa PNG/JPEG nhờ GDI+ (gdiplus.dll)
có sẵn trong Windows, gọi qua ctypes. Chủ web chọn thu nhỏ ảnh có cạnh dài quá 2000px: máy chủ không lưu hội thoại nên
bước nào Peto cũng gửi lại ảnh, ảnh nhỏ gửi nhanh và tốn ít token hơn mà chữ trong ảnh chụp màn hình vẫn đọc được.
"""

from __future__ import annotations

import base64
import os
import re
import struct
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

MAX_SIDE = 2000
# Mỗi ảnh sau khi xử lý; máy chủ nhận tới 3 MB nên còn chỗ cho phần chữ của bước.
MAX_IMAGE_BYTES = 2 * 1024 * 1024
# PNG giữ nét chữ; ảnh không trong suốt mà PNG nặng hơn mức này thì thử JPEG xem có nhẹ hơn không.
PNG_PREFERRED_BYTES = 1024 * 1024
JPEG_QUALITY = 85
# Tệp hay dữ liệu clipboard lớn hơn mức này thì không đọc, và ảnh quá nhiều điểm ảnh thì không giải mã.
MAX_SOURCE_BYTES = 40 * 1024 * 1024
MAX_SOURCE_PIXELS = 60_000_000
MAX_IMAGES_AT_ONCE = 4
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

NO_IMAGE = "Clipboard chưa có ảnh. Chụp màn hình (Win+Shift+S) hoặc copy ảnh rồi bấm Alt+V."
UNREADABLE = "Không đọc được ảnh này. Peto nhận ảnh PNG, JPEG, GIF, WebP hoặc BMP."
TOO_LARGE = "Ảnh lớn quá, Peto chưa thu nhỏ được. Thử chụp vùng nhỏ hơn nhé."
CLIPBOARD_BUSY = "Clipboard đang bị ứng dụng khác giữ. Bấm Alt+V lại sau chút nhé."
WINDOWS_ONLY = "Gửi ảnh hiện chỉ có trên Windows."


class ImageError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class Image:
    data: bytes
    mime: str
    width: int
    height: int

    def data_url(self) -> str:
        return f"data:{self.mime};base64,{base64.b64encode(self.data).decode('ascii')}"


def sniff_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    return None


def format_size(count: int) -> str:
    return f"{count / 1024 / 1024:.1f} MB" if count >= 1024 * 1024 else f"{max(1, round(count / 1024))} KB"


_PATH_TOKEN = re.compile(r'"([^"]+)"|\'([^\']+)\'|(\S+)')


def dropped_paths(text: str) -> list[Path]:
    """Đường dẫn tệp ảnh mà terminal dán vào khi kéo thả tệp; danh sách rỗng nếu chữ dán vào không chỉ gồm tệp ảnh.

    Windows Terminal dán đường dẫn tuyệt đối, đặt trong ngoặc kép khi có dấu cách, các tệp cách nhau bằng dấu cách.
    """
    text = text.strip()
    if not text or "\n" in text:
        return []
    paths = []
    for match in _PATH_TOKEN.finditer(text):
        path = Path(next(group for group in match.groups() if group))
        if not path.is_absolute() or path.suffix.lower() not in IMAGE_SUFFIXES:
            return []
        paths.append(path)
    if len(paths) > MAX_IMAGES_AT_ONCE or not all(path.is_file() for path in paths):
        return []
    return paths


def from_files(paths: list[Path]) -> list[Image]:
    images = []
    for path in paths[:MAX_IMAGES_AT_ONCE]:
        try:
            if path.stat().st_size > MAX_SOURCE_BYTES:
                raise ImageError(f"{path.name}: {TOO_LARGE}")
            raw = path.read_bytes()
        except OSError:
            raise ImageError(f"Không mở được tệp {path.name}.") from None
        try:
            images.append(prepare(raw))
        except ImageError as err:
            raise ImageError(f"{path.name}: {err.message}") from None
    return images


def from_clipboard() -> list[Image]:
    """Ảnh trong clipboard: ảnh chụp màn hình, ảnh copy từ trình duyệt, hay tệp ảnh copy trong Explorer."""
    if os.name != "nt":
        raise ImageError(WINDOWS_ONLY)
    kind, value = _Clipboard().read()
    if kind == "paths":
        paths = [path for path in value if path.suffix.lower() in IMAGE_SUFFIXES]
        if not paths:
            raise ImageError(NO_IMAGE)
        return from_files(paths)
    return [prepare(value)]


def prepare(raw: bytes) -> Image:
    """Kiểm loại ảnh, thu nhỏ khi cạnh dài quá MAX_SIDE, xoay theo EXIF, và giữ dưới MAX_IMAGE_BYTES."""
    mime = sniff_mime(raw)
    if mime is None:
        raise ImageError(UNREADABLE)
    if mime == "image/webp":
        # GDI+ không đọc được WebP, nên không thu nhỏ được: gửi nguyên nếu vừa.
        if len(raw) > MAX_IMAGE_BYTES:
            raise ImageError(f"Ảnh WebP nặng {format_size(len(raw))}, Peto chỉ gửi được ảnh WebP dưới "
                             f"{format_size(MAX_IMAGE_BYTES)}. Lưu lại thành PNG hoặc JPEG rồi thử lại nhé.")
        return Image(raw, mime, 0, 0)
    if os.name != "nt":
        raise ImageError(WINDOWS_ONLY)
    try:
        return _gdiplus().prepare(raw, mime)
    except OSError:
        # Lỗi Windows khi đọc ảnh không được lọt ra ngoài: dòng nhập coi OSError là console hỏng.
        raise ImageError(UNREADABLE) from None


# --- Clipboard ---------------------------------------------------------------

CF_DIB, CF_HDROP = 8, 15


def dib_to_bmp(dib: bytes) -> bytes:
    """CF_DIB là tệp BMP thiếu phần đầu 14 byte: thêm vào để GDI+ đọc như một tệp BMP."""
    if len(dib) < 16:
        raise ImageError(UNREADABLE)
    header_size = int.from_bytes(dib[:4], "little")
    if header_size == 12:
        bit_count = int.from_bytes(dib[10:12], "little")
        palette = (1 << bit_count) * 3 if bit_count <= 8 else 0
    elif 40 <= header_size <= len(dib):
        bit_count = int.from_bytes(dib[14:16], "little")
        compression = int.from_bytes(dib[16:20], "little")
        colors = int.from_bytes(dib[32:36], "little")
        # Tiêu đề 40 byte với BI_BITFIELDS (3) hay BI_ALPHABITFIELDS (6) có mặt nạ màu nằm ngay sau.
        masks = {3: 12, 6: 16}.get(compression, 0) if header_size == 40 else 0
        palette = (colors or (1 << bit_count if bit_count <= 8 else 0)) * 4
        header_size += masks
    else:
        raise ImageError(UNREADABLE)
    offset = 14 + header_size + palette
    return b"BM" + struct.pack("<IHHI", 14 + len(dib), 0, 0, offset) + dib


class _Clipboard:
    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        handle = wintypes.HANDLE
        signatures = [
            (self.user32.OpenClipboard, [wintypes.HWND], wintypes.BOOL),
            (self.user32.CloseClipboard, [], wintypes.BOOL),
            (self.user32.IsClipboardFormatAvailable, [wintypes.UINT], wintypes.BOOL),
            (self.user32.GetClipboardData, [wintypes.UINT], handle),
            (self.user32.RegisterClipboardFormatW, [wintypes.LPCWSTR], wintypes.UINT),
            (self.kernel32.GlobalLock, [handle], ctypes.c_void_p),
            (self.kernel32.GlobalUnlock, [handle], wintypes.BOOL),
            (self.kernel32.GlobalSize, [handle], ctypes.c_size_t),
            (self.shell32.DragQueryFileW, [handle, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT], wintypes.UINT),
        ]
        for function, arguments, result in signatures:
            function.argtypes, function.restype = arguments, result

    def read(self) -> tuple[str, object]:
        user32 = self.user32
        for _ in range(10):
            if user32.OpenClipboard(None):
                break
            time.sleep(0.03)
        else:
            raise ImageError(CLIPBOARD_BUSY)
        try:
            # Trình duyệt và công cụ chụp màn hình thường để sẵn bản PNG, giữ đúng nền trong suốt.
            for name in ("PNG", "image/png"):
                fmt = user32.RegisterClipboardFormatW(name)
                if fmt and user32.IsClipboardFormatAvailable(fmt):
                    data = self._global_bytes(user32.GetClipboardData(fmt))
                    if sniff_mime(data) == "image/png":
                        return "bytes", data
            if user32.IsClipboardFormatAvailable(CF_DIB):
                return "bytes", dib_to_bmp(self._global_bytes(user32.GetClipboardData(CF_DIB)))
            if user32.IsClipboardFormatAvailable(CF_HDROP):
                return "paths", self._dropped(user32.GetClipboardData(CF_HDROP))
        finally:
            user32.CloseClipboard()
        raise ImageError(NO_IMAGE)

    def _global_bytes(self, handle) -> bytes:
        if not handle:
            return b""
        size = self.kernel32.GlobalSize(handle)
        if size > MAX_SOURCE_BYTES:
            raise ImageError(TOO_LARGE)
        pointer = self.kernel32.GlobalLock(handle)
        if not pointer:
            return b""
        try:
            return self.ctypes.string_at(pointer, size)
        finally:
            self.kernel32.GlobalUnlock(handle)

    def _dropped(self, handle) -> list[Path]:
        if not handle:
            return []
        paths = []
        for index in range(min(self.shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0), 64)):
            length = self.shell32.DragQueryFileW(handle, index, None, 0)
            buffer = self.ctypes.create_unicode_buffer(length + 1)
            if self.shell32.DragQueryFileW(handle, index, buffer, length + 1):
                paths.append(Path(buffer.value))
        return paths


# --- GDI+ ----------------------------------------------------------------------

PNG_ENCODER = "557CF406-1A04-11D3-9A73-0000F81EF32E"
JPEG_ENCODER = "557CF401-1A04-11D3-9A73-0000F81EF32E"
ENCODER_QUALITY = "1D5BE4B5-FA4A-452D-9CDD-5DB35105E7EB"
PIXEL_24BPP_RGB, PIXEL_32BPP_ARGB = 0x00021808, 0x0026200A
IMAGE_FLAGS_HAS_ALPHA = 0x0002
EXIF_ORIENTATION = 0x0112
# Hướng EXIF 2…8 thành kiểu xoay/lật của GDI+.
ROTATE_FLIP = {2: 4, 3: 2, 4: 6, 5: 5, 6: 1, 7: 7, 8: 3}
STATUS_OUT_OF_MEMORY = 3

_instance = None


def _gdiplus() -> _Gdiplus:
    global _instance
    if _instance is None:
        try:
            _instance = _Gdiplus()
        except OSError:
            raise ImageError(UNREADABLE) from None
    return _instance


class _Gdiplus:
    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        pointer = ctypes.c_void_p
        out = ctypes.POINTER(ctypes.c_void_p)
        uint_out = ctypes.POINTER(ctypes.c_uint)

        class Guid(ctypes.Structure):
            _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16), ("data3", ctypes.c_uint16),
                        ("data4", ctypes.c_ubyte * 8)]

        class StartupInput(ctypes.Structure):
            _fields_ = [("version", ctypes.c_uint32), ("debug_callback", ctypes.c_void_p),
                        ("suppress_background_thread", wintypes.BOOL), ("suppress_external_codecs", wintypes.BOOL)]

        class EncoderParameter(ctypes.Structure):
            _fields_ = [("guid", Guid), ("count", ctypes.c_ulong), ("type", ctypes.c_ulong),
                        ("value", ctypes.c_void_p)]

        class EncoderParameters(ctypes.Structure):
            _fields_ = [("count", ctypes.c_uint), ("parameter", EncoderParameter * 1)]

        class PropertyItem(ctypes.Structure):
            _fields_ = [("id", ctypes.c_uint32), ("length", ctypes.c_ulong), ("type", ctypes.c_ushort),
                        ("value", ctypes.c_void_p)]

        self.Guid, self.EncoderParameters, self.PropertyItem = Guid, EncoderParameters, PropertyItem
        self.gdiplus = gdiplus = ctypes.WinDLL("gdiplus")
        self.shlwapi = shlwapi = ctypes.WinDLL("shlwapi")
        status = ctypes.c_int
        signatures = [
            (gdiplus.GdiplusStartup, [ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(StartupInput), pointer], status),
            (gdiplus.GdipCreateBitmapFromStream, [pointer, out], status),
            (gdiplus.GdipGetImageWidth, [pointer, uint_out], status),
            (gdiplus.GdipGetImageHeight, [pointer, uint_out], status),
            (gdiplus.GdipGetImageFlags, [pointer, uint_out], status),
            (gdiplus.GdipGetPropertyItemSize, [pointer, ctypes.c_uint32, uint_out], status),
            (gdiplus.GdipGetPropertyItem, [pointer, ctypes.c_uint32, ctypes.c_uint, pointer], status),
            (gdiplus.GdipImageRotateFlip, [pointer, ctypes.c_int], status),
            (gdiplus.GdipCreateBitmapFromScan0, [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, pointer, out],
             status),
            (gdiplus.GdipGetImageGraphicsContext, [pointer, out], status),
            (gdiplus.GdipSetInterpolationMode, [pointer, ctypes.c_int], status),
            (gdiplus.GdipSetPixelOffsetMode, [pointer, ctypes.c_int], status),
            (gdiplus.GdipSetCompositingMode, [pointer, ctypes.c_int], status),
            (gdiplus.GdipCreateImageAttributes, [out], status),
            (gdiplus.GdipSetImageAttributesWrapMode, [pointer, ctypes.c_int, ctypes.c_uint32, wintypes.BOOL], status),
            (gdiplus.GdipDrawImageRectRectI, [pointer, pointer] + [ctypes.c_int] * 9 + [pointer, pointer, pointer],
             status),
            (gdiplus.GdipSaveImageToStream, [pointer, pointer, ctypes.POINTER(Guid), pointer], status),
            (gdiplus.GdipDeleteGraphics, [pointer], status),
            (gdiplus.GdipDisposeImageAttributes, [pointer], status),
            (gdiplus.GdipDisposeImage, [pointer], status),
            (shlwapi.SHCreateMemStream, [ctypes.c_char_p, ctypes.c_uint], pointer),
            (shlwapi.IStream_Size, [pointer, ctypes.POINTER(ctypes.c_ulonglong)], ctypes.HRESULT),
            (shlwapi.IStream_Reset, [pointer], ctypes.HRESULT),
            (shlwapi.IStream_Read, [pointer, pointer, ctypes.c_ulong], ctypes.HRESULT),
        ]
        for function, arguments, result in signatures:
            function.argtypes, function.restype = arguments, result
        token = ctypes.c_size_t()
        startup = StartupInput(1, None, False, False)
        if gdiplus.GdiplusStartup(ctypes.byref(token), ctypes.byref(startup), None) != 0:
            raise OSError("GdiplusStartup")
        # Không gọi GdiplusShutdown: GDI+ sống tới khi peto thoát.
        self.token = token

    def _guid(self, text: str):
        return self.Guid.from_buffer_copy(uuid.UUID(text).bytes_le)

    def _check(self, status: int) -> None:
        if status == STATUS_OUT_OF_MEMORY:
            raise ImageError(TOO_LARGE)
        if status != 0:
            raise ImageError(UNREADABLE)

    def _release(self, stream: int) -> None:
        ctypes = self.ctypes
        vtable = ctypes.cast(stream, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])(stream)

    def _size(self, image) -> tuple[int, int]:
        width, height = self.ctypes.c_uint(), self.ctypes.c_uint()
        self._check(self.gdiplus.GdipGetImageWidth(image, self.ctypes.byref(width)))
        self._check(self.gdiplus.GdipGetImageHeight(image, self.ctypes.byref(height)))
        return width.value, height.value

    def _orientation(self, image) -> int:
        ctypes = self.ctypes
        size = ctypes.c_uint()
        if self.gdiplus.GdipGetPropertyItemSize(image, EXIF_ORIENTATION, ctypes.byref(size)) != 0 or size.value < 24:
            return 1
        buffer = ctypes.create_string_buffer(size.value)
        if self.gdiplus.GdipGetPropertyItem(image, EXIF_ORIENTATION, size.value, buffer) != 0:
            return 1
        item = self.PropertyItem.from_buffer(buffer)
        if item.type != 3 or item.length < 2 or not item.value:
            return 1
        return ctypes.cast(item.value, ctypes.POINTER(ctypes.c_ushort))[0]

    def prepare(self, raw: bytes, mime: str) -> Image:
        ctypes, gdiplus = self.ctypes, self.gdiplus
        stream = self.shlwapi.SHCreateMemStream(raw, len(raw))
        if not stream:
            raise ImageError(TOO_LARGE)
        image = ctypes.c_void_p()
        try:
            self._check(gdiplus.GdipCreateBitmapFromStream(stream, ctypes.byref(image)))
            width, height = self._size(image)
            if not width or not height:
                raise ImageError(UNREADABLE)
            if width * height > MAX_SOURCE_PIXELS:
                raise ImageError(TOO_LARGE)
            orientation = self._orientation(image)
            scale = min(1.0, MAX_SIDE / max(width, height))
            if (mime != "image/bmp" and scale == 1.0 and orientation == 1 and len(raw) <= MAX_IMAGE_BYTES):
                return Image(raw, mime, width, height)
            if orientation in ROTATE_FLIP:
                self._check(gdiplus.GdipImageRotateFlip(image, ROTATE_FLIP[orientation]))
                width, height = self._size(image)
                scale = min(1.0, MAX_SIDE / max(width, height))
            flags = ctypes.c_uint()
            self._check(gdiplus.GdipGetImageFlags(image, ctypes.byref(flags)))
            alpha = bool(flags.value & IMAGE_FLAGS_HAS_ALPHA)
            while True:
                target_width, target_height = max(1, round(width * scale)), max(1, round(height * scale))
                data, out_mime = self._render(image, width, height, target_width, target_height, alpha)
                if len(data) <= MAX_IMAGE_BYTES:
                    return Image(data, out_mime, target_width, target_height)
                if max(target_width, target_height) <= 480:
                    raise ImageError(TOO_LARGE)
                scale *= 0.7
        finally:
            if image:
                gdiplus.GdipDisposeImage(image)
            self._release(stream)

    def _render(self, image, width: int, height: int, target_width: int, target_height: int,
                alpha: bool) -> tuple[bytes, str]:
        ctypes, gdiplus = self.ctypes, self.gdiplus
        bitmap, graphics, attributes = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        self._check(gdiplus.GdipCreateBitmapFromScan0(target_width, target_height, 0,
                                                       PIXEL_32BPP_ARGB if alpha else PIXEL_24BPP_RGB, None,
                                                       ctypes.byref(bitmap)))
        try:
            try:
                self._check(gdiplus.GdipGetImageGraphicsContext(bitmap, ctypes.byref(graphics)))
                self._check(gdiplus.GdipSetInterpolationMode(graphics, 7))  # HighQualityBicubic
                self._check(gdiplus.GdipSetPixelOffsetMode(graphics, 2))  # HighQuality
                if alpha:
                    self._check(gdiplus.GdipSetCompositingMode(graphics, 1))  # SourceCopy: giữ nguyên độ trong suốt
                # Lật ảnh ở mép khi lấy mẫu, để ảnh thu nhỏ không có viền mờ.
                self._check(gdiplus.GdipCreateImageAttributes(ctypes.byref(attributes)))
                self._check(gdiplus.GdipSetImageAttributesWrapMode(attributes, 3, 0, False))
                self._check(gdiplus.GdipDrawImageRectRectI(graphics, image, 0, 0, target_width, target_height, 0, 0,
                                                            width, height, 2, attributes, None, None))
            finally:
                if graphics:
                    gdiplus.GdipDeleteGraphics(graphics)
                if attributes:
                    gdiplus.GdipDisposeImageAttributes(attributes)
            data, mime = self._encode(bitmap, PNG_ENCODER), "image/png"
            if not alpha and len(data) > PNG_PREFERRED_BYTES:
                jpeg = self._encode(bitmap, JPEG_ENCODER, JPEG_QUALITY)
                if len(jpeg) < len(data):
                    data, mime = jpeg, "image/jpeg"
            return data, mime
        finally:
            gdiplus.GdipDisposeImage(bitmap)

    def _encode(self, image, encoder: str, quality: int | None = None) -> bytes:
        ctypes = self.ctypes
        stream = self.shlwapi.SHCreateMemStream(None, 0)
        if not stream:
            raise ImageError(TOO_LARGE)
        try:
            parameters = None
            value = ctypes.c_ulong(quality or 0)
            if quality is not None:
                parameters = self.EncoderParameters(1)
                parameters.parameter[0].guid = self._guid(ENCODER_QUALITY)
                parameters.parameter[0].count = 1
                parameters.parameter[0].type = 4  # EncoderParameterValueTypeLong
                parameters.parameter[0].value = ctypes.addressof(value)
            clsid = self._guid(encoder)
            self._check(self.gdiplus.GdipSaveImageToStream(
                image, stream, ctypes.byref(clsid), ctypes.byref(parameters) if parameters is not None else None))
            size = ctypes.c_ulonglong()
            self.shlwapi.IStream_Size(stream, ctypes.byref(size))
            self.shlwapi.IStream_Reset(stream)
            buffer = ctypes.create_string_buffer(size.value)
            self.shlwapi.IStream_Read(stream, buffer, size.value)
            return buffer.raw
        finally:
            self._release(stream)
