"""Generate the Subtitle Translator icon (assets/icon.ico + assets/icon.png).

Pure Python standard library: every size is rendered directly from signed-distance
shapes (anti-aliased, crisp at 16 px), then written as PNG and as a multi-size ICO
(BMP frames up to 128 px, a PNG frame at 256 px, which is what Windows expects).

Design: white rounded speech bubble with two "subtitle bars", on a rounded square
in the accent colour (blue gradient).

Run:  .venv\\Scripts\\python.exe assets\\make_icon.py
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
PNG_SIZE = 512

# Colours (sRGB)
ACCENT_TOP = (0x2F, 0x86, 0xF0)
ACCENT_BOTTOM = (0x16, 0x5A, 0xC8)
WHITE = (0xFF, 0xFF, 0xFF)
BAR = (0x1C, 0x66, 0xD6)


# ---------------------------------------------------------------- shapes (unit square, y down)
def sd_round_rect(px, py, x0, y0, x1, y1, r):
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2 - r, (y1 - y0) / 2 - r
    dx, dy = abs(px - cx) - hx, abs(py - cy) - hy
    outside = math.hypot(max(dx, 0.0), max(dy, 0.0))
    inside = min(max(dx, dy), 0.0)
    return outside + inside - r


def sd_polygon(px, py, pts):
    """Signed distance to a simple polygon (negative inside)."""
    d = float("inf")
    sign = 1.0
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[i - 1]
        ex, ey = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        t = max(0.0, min(1.0, (wx * ex + wy * ey) / (ex * ex + ey * ey)))
        qx, qy = wx - ex * t, wy - ey * t
        d = min(d, qx * qx + qy * qy)
        c1 = py >= ay
        c2 = py < by
        c3 = ex * wy > ey * wx
        if (c1 and c2 and c3) or (not c1 and not c2 and not c3):
            sign = -sign
    return sign * math.sqrt(d)


def sd_capsule_h(px, py, x0, x1, yc, half):
    """Horizontal pill from x0 to x1 (centre line yc), half-thickness `half`."""
    cx = min(max(px, x0), x1)
    return math.hypot(px - cx, py - yc) - half


def coverage(dist, pix):
    """Anti-aliased coverage from a signed distance in unit coords; pix = 1 pixel in units."""
    return min(1.0, max(0.0, 0.5 - dist / pix))


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def render(size: int) -> bytes:
    """Return RGBA bytes (top-down rows) for a size x size icon."""
    pix = 1.0 / size
    small = size <= 24
    # Shape geometry (slightly bolder at tiny sizes so it stays readable).
    m = 0.0 if small else 0.03                      # outer margin
    bg_r = 0.20 if small else 0.22
    bub = (0.15, 0.20, 0.85, 0.68) if small else (0.17, 0.21, 0.83, 0.67)
    bub_r = 0.13
    tail = [(0.27, 0.60), (0.47, 0.60), (0.25, 0.84)] if small else [(0.29, 0.60), (0.46, 0.60), (0.26, 0.82)]
    bar_half = 0.055 if small else 0.038
    bars = ([(0.29, 0.71, 0.36), (0.36, 0.64, 0.52)] if small
            else [(0.29, 0.71, 0.375), (0.35, 0.65, 0.505)])
    if small:
        # Snap the bars to whole pixel rows so they stay crisp instead of blurring.
        thick = max(1, round(size * 0.07))
        bar_half = thick / 2 * pix
        bars = [(x0, x1, (math.floor(yc * size - thick / 2 + 0.5) + thick / 2) * pix)
                for x0, x1, yc in bars]

    out = bytearray()
    for j in range(size):
        py = (j + 0.5) * pix
        grad = mix(ACCENT_TOP, ACCENT_BOTTOM, py)
        for i in range(size):
            px = (i + 0.5) * pix
            a_bg = coverage(sd_round_rect(px, py, m, m, 1 - m, 1 - m, bg_r), pix)
            if a_bg <= 0.0:
                out += b"\0\0\0\0"
                continue
            d_bub = min(sd_round_rect(px, py, *bub, bub_r), sd_polygon(px, py, tail))
            a_bub = coverage(d_bub, pix)
            col = mix(grad, WHITE, a_bub)
            if a_bub > 0.0:
                d_bar = min(sd_capsule_h(px, py, x0, x1, yc, bar_half) for x0, x1, yc in bars)
                a_bar = coverage(d_bar, pix) * a_bub
                col = mix(col, BAR, a_bar)
            out += bytes((round(col[0]), round(col[1]), round(col[2]), round(255 * a_bg)))
    return bytes(out)


# ---------------------------------------------------------------- encoders
def png_bytes(size: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    stride = size * 4
    raw = b"".join(b"\0" + rgba[y * stride:(y + 1) * stride] for y in range(size))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def bmp_icon_bytes(size: int, rgba: bytes) -> bytes:
    """32-bit BGRA DIB (bottom-up) + 1-bit AND mask, as stored inside .ico files."""
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    stride = size * 4
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        row = rgba[y * stride:(y + 1) * stride]
        for x in range(size):
            r, g, b, a = row[x * 4:x * 4 + 4]
            pixels += bytes((b, g, r, a))
    mask_stride = ((size + 31) // 32) * 4
    mask = bytearray()
    for y in range(size - 1, -1, -1):
        bits = bytearray(mask_stride)
        for x in range(size):
            if rgba[(y * size + x) * 4 + 3] == 0:
                bits[x // 8] |= 0x80 >> (x % 8)
        mask += bits
    return header + bytes(pixels) + bytes(mask)


def ico_bytes(frames: list[tuple[int, bytes]]) -> bytes:
    count = len(frames)
    offset = 6 + 16 * count
    head = struct.pack("<HHH", 0, 1, count)
    entries, blobs = b"", b""
    for size, blob in frames:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    return head + entries + blobs


def main() -> None:
    frames = []
    for size in ICO_SIZES:
        rgba = render(size)
        blob = png_bytes(size, rgba) if size >= 256 else bmp_icon_bytes(size, rgba)
        frames.append((size, blob))
        print(f"rendered {size}x{size}")
    (HERE / "icon.ico").write_bytes(ico_bytes(frames))
    (HERE / "icon.png").write_bytes(png_bytes(PNG_SIZE, render(PNG_SIZE)))
    print(f"wrote {HERE / 'icon.ico'} and {HERE / 'icon.png'} ({PNG_SIZE}px)")


if __name__ == "__main__":
    main()
