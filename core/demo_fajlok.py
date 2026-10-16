"""Demo workspace: synthetic binary files, generated from code (no personal material, no third-party library).

- `pdf(lapok, cim)`: a small valid PDF 1.4 (Helvetica, one content stream per page, plain text plus simple vector shapes), with
  no date or producer field, so the same input always gives the same bytes.
- `png(szeles, magas, rajz)`: a small RGB PNG drawn from primitives (`Vaszon`), deterministic (fixed zlib level).

Pure functions: bytes in, bytes out. Nothing here touches the disk.
"""
from __future__ import annotations

import math
import struct
import textwrap
import zlib

# ------------------------------------------------------------------ PDF

LAP_SZELES, LAP_MAGAS, MARGO = 612, 792, 72


def _pdf_szoveg(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


SOR_MAGAS, BEKEZDES_KOZ, KARAKTER_SZELES = 15, 9, 5.3


def sorok_helye(lap: dict):
    """The text lines of a page as `(text, baseline_y, paragraph_index, offset_in_paragraph)`, in drawing order."""
    y = LAP_MAGAS - MARGO - (34 if lap.get("cim") else 0)
    for i, b in enumerate(lap.get("bekezdesek", [])):
        pos = 0
        for sor in textwrap.wrap(b, 78) or [""]:
            kezd = b.find(sor, pos) if sor else pos
            yield sor, y, i, kezd
            pos = kezd + len(sor)
            y -= SOR_MAGAS
        y -= BEKEZDES_KOZ


def kiemeles_teglalapok(lap: dict, mondat: str) -> list[list[float]]:
    """Normalised highlight rectangles `[x, y_from_top, width, height]` (0-1) covering `mondat` on a page (approximate glyph widths)."""
    ki = []
    for sor, y, i, kezd in sorok_helye(lap):
        b = lap["bekezdesek"][i]
        h = b.find(mondat)
        if h < 0:
            continue
        a, z = max(h, kezd), min(h + len(mondat), kezd + len(sor))
        if a >= z:
            continue
        ki.append([round((MARGO + (a - kezd) * KARAKTER_SZELES) / LAP_SZELES, 4), round((LAP_MAGAS - (y + 10)) / LAP_MAGAS, 4),
                   round((z - a) * KARAKTER_SZELES / LAP_SZELES, 4), round(13 / LAP_MAGAS, 4)])
    return ki


def _lap_tartalom(lap: dict) -> bytes:
    """One page: `{"cim": str, "bekezdesek": [str], "alakzatok": [(x, y, sz, m, "kor"|"teglalap"|"vonal")...]}`."""
    ki: list[str] = []
    if lap.get("cim"):
        ki.append(f"BT /F2 18 Tf {MARGO} {LAP_MAGAS - MARGO} Td ({_pdf_szoveg(lap['cim'])}) Tj ET")
    for sor, y, _, _ in sorok_helye(lap):
        ki.append(f"BT /F1 11 Tf {MARGO} {y} Td ({_pdf_szoveg(sor)}) Tj ET")
    for a in lap.get("alakzatok", []):
        x, yy, sz, m, fajta = a
        if fajta == "teglalap":
            ki.append(f"0.75 w {x} {yy} {sz} {m} re S")
        elif fajta == "vonal":
            ki.append(f"0.75 w {x} {yy} m {x + sz} {yy + m} l S")
        elif fajta in ("kor", "ellipszis"):
            rx, ry = sz, (m if fajta == "ellipszis" else sz)
            kx, ky = 0.5523 * rx, 0.5523 * ry
            ki.append(f"0.75 w {x - rx} {yy} m {x - rx} {yy + ky} {x - kx} {yy + ry} {x} {yy + ry} c "
                      f"{x + kx} {yy + ry} {x + rx} {yy + ky} {x + rx} {yy} c {x + rx} {yy - ky} {x + kx} {yy - ry} {x} {yy - ry} c "
                      f"{x - kx} {yy - ry} {x - rx} {yy - ky} {x - rx} {yy} c S")
    if lap.get("felirat"):
        ki.append(f"BT /F1 9 Tf {MARGO} {MARGO - 30} Td ({_pdf_szoveg(lap['felirat'])}) Tj ET")
    return "\n".join(ki).encode("latin-1")


def pdf(lapok: list[dict], cim: str) -> bytes:
    """A complete PDF file. Text is ASCII/Latin-1 (the demo is English)."""
    targyak: list[bytes] = []

    def uj(tartalom: bytes) -> int:
        targyak.append(tartalom)
        return len(targyak)

    uj(b"<< /Type /Catalog /Pages 2 0 R >>")                                   # 1
    n = len(lapok)
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n))
    uj(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())                # 2
    uj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")        # 3
    uj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")   # 4
    for i, lap in enumerate(lapok):
        folyam = _lap_tartalom(lap)
        uj(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {LAP_SZELES} {LAP_MAGAS}] /Contents {6 + 2 * i} 0 R "
           f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>".encode())
        uj(b"<< /Length " + str(len(folyam)).encode() + b" >>\nstream\n" + folyam + b"\nendstream")
    info = uj(f"<< /Title ({_pdf_szoveg(cim)}) >>".encode())
    ki = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsetek = []
    for i, t in enumerate(targyak, 1):
        offsetek.append(len(ki))
        ki += f"{i} 0 obj\n".encode() + t + b"\nendobj\n"
    xref = len(ki)
    ki += f"xref\n0 {len(targyak) + 1}\n".encode() + b"0000000000 65535 f \n"
    for o in offsetek:
        ki += f"{o:010d} 00000 n \n".encode()
    ki += f"trailer\n<< /Size {len(targyak) + 1} /Root 1 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(ki)


# ------------------------------------------------------------------ PNG

class Vaszon:
    """An RGB canvas with a few primitives (solid colours only)."""

    def __init__(self, szeles: int, magas: int, hatter=(250, 248, 244)):
        self.sz, self.m = szeles, magas
        self.px = bytearray(bytes(hatter) * (szeles * magas))

    def pont(self, x: int, y: int, szin) -> None:
        if 0 <= x < self.sz and 0 <= y < self.m:
            i = (y * self.sz + x) * 3
            self.px[i:i + 3] = bytes(szin)

    def teglalap(self, x0, y0, x1, y1, szin, kitoltott=True, vastag=2) -> None:
        for y in range(int(y0), int(y1) + 1):
            for x in range(int(x0), int(x1) + 1):
                if kitoltott or min(x - x0, x1 - x, y - y0, y1 - y) < vastag:
                    self.pont(x, y, szin)

    def korong(self, cx, cy, r, szin) -> None:
        r2 = r * r
        for y in range(int(cy - r), int(cy + r) + 1):
            for x in range(int(cx - r), int(cx + r) + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r2:
                    self.pont(x, y, szin)

    def vonal(self, x0, y0, x1, y1, szin, vastag=2) -> None:
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        r = max(vastag / 2, 0.5)
        for i in range(n + 1):
            t = i / n
            self.korong(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r, szin)

    def gorbe(self, fv, x_tol, x_ig, szin, vastag=3, lepes=0.5) -> None:
        """Plots `y = fv(x)` in pixel coordinates (the function returns a pixel row)."""
        elozo = None
        x = x_tol
        while x <= x_ig:
            y = fv(x)
            if elozo is not None:
                self.vonal(elozo[0], elozo[1], x, y, szin, vastag)
            elozo = (x, y)
            x += lepes

    def ellipszis(self, cx, cy, a, b, szin, vastag=2) -> None:
        elozo = None
        for i in range(0, 361, 2):
            t = math.radians(i)
            p = (cx + a * math.cos(t), cy + b * math.sin(t))
            if elozo:
                self.vonal(*elozo, *p, szin, vastag)
            elozo = p

    def png(self) -> bytes:
        nyers = b"".join(b"\x00" + bytes(self.px[y * self.sz * 3:(y + 1) * self.sz * 3]) for y in range(self.m))

        def blokk(tipus: bytes, adat: bytes) -> bytes:
            return struct.pack(">I", len(adat)) + tipus + adat + struct.pack(">I", zlib.crc32(tipus + adat) & 0xFFFFFFFF)
        return (b"\x89PNG\r\n\x1a\n" + blokk(b"IHDR", struct.pack(">IIBBBBB", self.sz, self.m, 8, 2, 0, 0, 0))
                + blokk(b"IDAT", zlib.compress(nyers, 6)) + blokk(b"IEND", b""))


SOTET, KEK, PIROS, ZOLD, SARGA, SZURKE, BORDO = (40, 40, 48), (52, 110, 190), (200, 70, 60), (60, 150, 90), (230, 180, 40), (190, 190, 196), (110, 28, 52)


def tengelyek(v: Vaszon, x0, y0, x1, y1) -> None:
    v.vonal(x0, y1, x1, y1, SZURKE, 2)
    v.vonal(x0, y0, x0, y1, SZURKE, 2)


def kep_parabola() -> bytes:
    v = Vaszon(400, 260)
    tengelyek(v, 40, 20, 370, 230)
    v.vonal(205, 20, 205, 230, SZURKE, 1)
    v.gorbe(lambda x: 215 - (1 - ((x - 205) / 120) ** 2) * 170, 85, 325, KEK, 3)
    v.korong(205, 45, 5, PIROS)
    v.korong(85, 215, 5, SOTET)
    v.korong(325, 215, 5, SOTET)
    return v.png()


def kep_palya() -> bytes:
    v = Vaszon(400, 260)
    v.ellipszis(200, 130, 150, 90, SZURKE, 2)
    v.korong(262, 130, 22, SARGA)
    v.korong(200 + 150 * math.cos(math.radians(130)), 130 + 90 * math.sin(math.radians(130)), 9, KEK)
    v.vonal(262, 130, 200 + 150 * math.cos(math.radians(130)), 130 + 90 * math.sin(math.radians(130)), SOTET, 1)
    return v.png()


def kep_haromszog() -> bytes:
    v = Vaszon(400, 260)
    a, b, c = (60, 220), (340, 220), (60, 50)
    v.vonal(*a, *b, SOTET, 3)
    v.vonal(*b, *c, SOTET, 3)
    v.vonal(*c, *a, SOTET, 3)
    v.teglalap(60, 196, 84, 220, PIROS, kitoltott=False, vastag=2)
    return v.png()


def kep_vizkoerforgas() -> bytes:
    v = Vaszon(400, 260)
    v.teglalap(0, 190, 399, 259, KEK)
    v.korong(330, 50, 24, SARGA)
    v.korong(130, 70, 28, SZURKE)
    v.korong(165, 66, 24, SZURKE)
    v.korong(100, 76, 20, SZURKE)
    for x in (110, 130, 150):
        v.vonal(x, 100, x - 8, 150, KEK, 2)
    v.vonal(250, 190, 250, 100, ZOLD, 3)
    v.vonal(250, 100, 238, 114, ZOLD, 3)
    v.vonal(250, 100, 262, 114, ZOLD, 3)
    return v.png()


def kep_sejt() -> bytes:
    v = Vaszon(400, 260)
    v.ellipszis(200, 130, 170, 105, ZOLD, 4)
    v.korong(200, 130, 38, BORDO)
    v.korong(200, 130, 16, SOTET)
    for cx, cy in ((110, 90), (290, 170), (120, 180), (285, 80)):
        v.ellipszis(cx, cy, 22, 11, KEK, 2)
    return v.png()
