# SPDX-License-Identifier: GPL-3.0-or-later
"""A QR code as a PNG, for the scanner to be shown (MESHSAT_APP_SCAN_SOURCE reads the file)."""


def write_png(value: str, path: str) -> str:
    import qrcode  # noqa: PLC0415 - python3-qrcode, a dependency of the package

    image = qrcode.make(value, border=4, box_size=8)
    image.save(path)
    return path


def write_blank_png(path: str, size: int = 64) -> str:
    """A grey square with no code in it: the scanner keeps looking."""
    import struct  # noqa: PLC0415
    import zlib  # noqa: PLC0415

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + bytes([0x80]) * size for _ in range(size))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(png)
    return path
