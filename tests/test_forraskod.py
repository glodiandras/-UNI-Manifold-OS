"""Forráskód-őrök (C29.6, 2. audit T100): amit nem a viselkedés, hanem a kód alakja véd."""
import ast
import unittest

from tests.helpers import REPO

CORE = REPO / "core"
# Indokolt kivétel: a teljes mentés változatai között a külső mentés-kötetén (a mentendő gyökereken kívül, `vaultkivul`
# ellenőrzi) linkel; a vaultot és a figyelt fákat nem érinti (CX-012). Ugyanígy a belső lemezes állapotmásolat: a változatlan
# fájl két `{backup}/mos-allapot-*` másolat között linkelődik (a forrás és a cél is a `{backup}` alatt, nem figyelt fa).
KIVETEL = {"core/teljes_mentes.py:_linkel", "core/mentes.py:_masol_vagy_linkel"}


class HardLinkTilos(unittest.TestCase):
    def test_a_core_nem_hasznal_hard_linket(self):
        """T100: a C16.5 indoklása téves volt — a hard linkkel létrehozott fájl későbbi törlését az FSEvents EGYÁLTALÁN nem
        jelenti (nem az „eltűnt első néven”), így az index nem venné észre a visszavonást. A vaultba író kód `open(.., "xb")`-et
        vagy `tartos.kizaro_ir`-t (tmp + `renamex_np`) használ, `os.link`-et soha."""
        talalat = []
        for p in sorted(CORE.rglob("*.py")):
            rel = str(p.relative_to(REPO))
            fa = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
            kizart = [(f.lineno, f.end_lineno) for f in ast.walk(fa)
                      if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f"{rel}:{f.name}" in KIVETEL]
            for n in ast.walk(fa):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                    if n.func.attr in ("link", "hardlink_to", "link_to") and \
                            (not isinstance(n.func.value, ast.Name) or n.func.value.id in ("os", "self")):
                        if not any(a <= n.lineno <= b for a, b in kizart):
                            talalat.append(f"{rel}:{n.lineno} .{n.func.attr}(")
        self.assertEqual(talalat, [], "hard link a core kódjában")


if __name__ == "__main__":
    unittest.main()
