"""A PDF-szövegkinyerő gyermekfolyamat (C25c): `python -I -B -X utf8 pdf_gyerek.py <pdf> <lap_max> <ossz_max>`, a
`pdf_profil.sb` sandbox-exec profilja alatt (a szülő: `core/index/pdfszoveg.py`).

A PDF nem megbízható bemenet (a MuPDF C-kódja elemzi), ezért külön, elzárt folyamatban fut: a hibája vagy összeomlása a
core-t nem viszi el, és a GIL-t sem foglalja. Kimenet (stdout, soronként egy JSON): `{"lapok": N}`, lapról lapra
`{"o": <oldal 1-től>, "s": <szöveg>}`, a végén `{"kesz": true}`; hibánál `{"hiba": "…"}`. A szöveg NFC, soronként a
szóközök összevonva, az üres sorok nélkül, az elválasztás (`szö-\\nveg`) visszaillesztve, a ligatúra kibontva; a lap
legfeljebb `lap_max`, az egész legfeljebb `ossz_max` karakter (a többi lemarad, `{"csonka": true}`).

Csak a standard könyvtárat és a PyMuPDF-et importálja (a profil a core kódját nem engedi olvasni).
"""
import json
import os
import sys
import unicodedata

_VEZERLO = dict.fromkeys(c for c in range(32) if c not in (9, 10))


def tisztit(s: str) -> str:
    s = unicodedata.normalize("NFC", s.translate(_VEZERLO).replace("­", ""))
    sorok = (" ".join(x.split()) for x in s.split("\n"))
    return "\n".join(x for x in sorok if x)


def ki(o) -> None:
    sys.stdout.write(json.dumps(o) + "\n")


def main() -> int:
    try:
        os.nice(10)
    except OSError:
        pass
    ut, lap_max, ossz_max = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    try:
        import pymupdf
    except ImportError as e:
        ki({"hiba": f"a PyMuPDF nem tölthető be: {e}"})
        return 0
    flags = getattr(pymupdf, "TEXT_DEHYPHENATE", 0) | getattr(pymupdf, "TEXT_MEDIABOX_CLIP", 0)
    try:
        doc = pymupdf.open(ut)
    except Exception as e:  # noqa: BLE001 — a hibás PDF a kimenetben jelzett hiba
        ki({"hiba": f"a PDF nem nyitható meg: {type(e).__name__}: {e}"[:300]})
        return 0
    with doc:
        if doc.needs_pass:
            ki({"hiba": "jelszóval védett PDF"})
            return 0
        ki({"lapok": doc.page_count})
        ossz = 0
        for i in range(doc.page_count):
            try:
                s = tisztit(doc[i].get_text("text", flags=flags))
            except Exception as e:  # noqa: BLE001 — egy rossz lap nem viszi el a többit
                s = ""
                ki({"o": i + 1, "s": "", "laphiba": f"{type(e).__name__}"[:100]})
                continue
            s = s[:lap_max]
            if ossz + len(s) > ossz_max:
                ki({"o": i + 1, "s": s[:max(0, ossz_max - ossz)]})
                ki({"csonka": True})
                break
            ossz += len(s)
            ki({"o": i + 1, "s": s})
    ki({"kesz": True})
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
