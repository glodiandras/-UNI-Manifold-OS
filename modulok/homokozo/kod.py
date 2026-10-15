"""Nem megbízható SymPy-kód futtatása a homokozó gyermekében (a `kod` művelet; a C24b és a `matek_cas` használja).

Az itteni szűrés **csak az első védvonal**: AST-szűrő, szűkített `__builtins__`, import-fehérlista. Nem
határ, mert a SymPy maga is futtat Python-kódot (a `sympify("…")` az `eval`-on át). A tényleges határ a
`sandbox-exec` profil (fájl, hálózat, exec, fork), a szülő memóriaőre és a kemény időkorlát.
"""
from __future__ import annotations

import ast
import builtins
import io

MAX_KOD = 20_000
ENGEDETT_MODULOK = ("sympy", "math", "fractions", "itertools", "functools", "operator")
TILTOTT_NEVEK = frozenset({
    "eval", "exec", "compile", "open", "globals", "locals", "vars", "getattr", "setattr", "delattr", "input",
    "breakpoint", "exit", "quit", "help", "memoryview", "object", "type", "super", "dir", "id", "hasattr",
    "classmethod", "staticmethod", "property", "bytearray", "bytes", "copyright", "credits", "license"})
_ENGEDETT_BEEPITETT = (
    "abs", "all", "any", "bool", "complex", "dict", "divmod", "enumerate", "filter", "float", "frozenset", "int",
    "isinstance", "len", "list", "map", "max", "min", "next", "iter", "pow", "range", "reversed", "round", "set",
    "slice", "sorted", "str", "sum", "tuple", "zip", "True", "False", "None", "Exception", "ValueError",
    "TypeError", "ZeroDivisionError", "ArithmeticError", "IndexError", "KeyError",
    "NotImplementedError", "StopIteration")


class Tiltott(Exception):
    """A kód a fehérlistán kívüli dolgot kért (import, név, attribútum)."""


class _Szuro(ast.NodeVisitor):
    def visit_Import(self, n):
        for a in n.names:
            _modul_ok(a.name)
        self.generic_visit(n)

    def visit_ImportFrom(self, n):
        if n.level:
            raise Tiltott("relatív import")
        _modul_ok(n.module or "")
        for a in n.names:
            if a.name == "*" or a.name.startswith("_"):
                raise Tiltott(f"tiltott import-név: {a.name}")
        self.generic_visit(n)

    def visit_Name(self, n):
        if n.id.startswith("_") or n.id in TILTOTT_NEVEK:
            raise Tiltott(f"tiltott név: {n.id}")
        self.generic_visit(n)

    def visit_Attribute(self, n):
        if n.attr.startswith("_"):
            raise Tiltott(f"tiltott attribútum: {n.attr}")
        if isinstance(n.ctx, (ast.Store, ast.Del)):
            raise Tiltott("attribútum-értékadás")                  # a SymPy/a pontozó felülírása ellen
        self.generic_visit(n)

    def visit_FunctionDef(self, n):
        if n.name.startswith("_"):
            raise Tiltott(f"tiltott név: {n.name}")
        self.generic_visit(n)

    def visit_ClassDef(self, n):
        raise Tiltott("osztály-definíció")

    def visit_Global(self, n):
        raise Tiltott("global")

    def visit_Nonlocal(self, n):
        raise Tiltott("nonlocal")

    def visit_arg(self, n):
        if n.arg.startswith("_"):
            raise Tiltott(f"tiltott név: {n.arg}")
        self.generic_visit(n)

    def visit_keyword(self, n):
        if n.arg and n.arg.startswith("_"):
            raise Tiltott(f"tiltott kulcsszó: {n.arg}")
        self.generic_visit(n)


def _modul_ok(nev: str) -> None:
    if nev.split(".")[0] not in ENGEDETT_MODULOK or any(r.startswith("_") for r in nev.split(".")):
        raise Tiltott(f"tiltott import: {nev}")


def _orzott_import(nev, globals=None, locals=None, fromlist=(), level=0):
    if level:
        raise Tiltott("relatív import")
    _modul_ok(nev)
    return builtins.__import__(nev, globals, locals, fromlist, level)


def ellenoriz(kod: str) -> ast.Module:
    """A kód AST-je, ha a szűrőn átmegy; különben `Tiltott` (vagy `SyntaxError`)."""
    if len(kod) > MAX_KOD:
        raise Tiltott(f"túl hosszú kód ({len(kod)} > {MAX_KOD} karakter)")
    fa = ast.parse(kod, mode="exec")
    _Szuro().visit(fa)
    return fa


def futtat(kod: str, valtozo: str = "EREDMENY", kimenet_max: int = 20_000) -> tuple[object, str]:
    """Lefuttatja a kódot szűkített névtérben → (a `valtozo` értéke, a `print` kimenete levágva)."""
    fa = ellenoriz(kod)
    puffer = io.StringIO()

    def kiir(*a, sep=" ", end="\n", **_):
        if puffer.tell() < kimenet_max:
            puffer.write(sep.join(str(x) for x in a)[:kimenet_max] + end)

    bi = {k: getattr(builtins, k) for k in _ENGEDETT_BEEPITETT if hasattr(builtins, k)}
    bi.update({"print": kiir, "__import__": _orzott_import})
    nevter = {"__builtins__": bi, "__name__": "homokozo_kod"}
    exec(compile(fa, "<homokozo>", "exec"), nevter)                 # noqa: S102 — a homokozó gyermekében, szűrve
    if valtozo not in nevter:
        raise LookupError(f"a kód nem állította be az {valtozo} változót")
    return nevter[valtozo], puffer.getvalue()[:kimenet_max]


# ------------------------------------------------------------------ az eredmény JSON-alakja

def szerializal(ertek, max_elem: int = 200) -> dict:
    """SymPy/Python eredmény → JSON. Kód nem kerül bele: a szülő a szövegalakot a fehérlistás elemzővel olvassa.

    `halmaz` (véges halmaz, lista, tuple, Python-halmaz), `par` (dict, vagy egyelemű lista dict-tel), `intervallum`
    (Interval / Union darabjai, egyváltozós egyenlőtlenség), `kifejezes`, `logikai`, `egyeb`."""
    import sympy as sp

    def s(e) -> str:
        return sp.sstr(e)[:2000]

    if isinstance(ertek, (bool, sp.logic.boolalg.BooleanAtom)):
        return {"tipus": "logikai", "ertek": bool(ertek)}
    if isinstance(ertek, list) and len(ertek) == 1 and isinstance(ertek[0], dict):
        ertek = ertek[0]
    if isinstance(ertek, dict):
        return {"tipus": "par", "ertekek": {s(k): s(v) for k, v in list(ertek.items())[:max_elem]}}
    if isinstance(ertek, sp.Rel) and len(ertek.free_symbols) == 1:
        try:
            ertek = ertek.as_set()
        except (NotImplementedError, TypeError, ValueError):
            return {"tipus": "egyeb", "ertek": s(ertek)}
    if ertek is sp.S.EmptySet:
        return {"tipus": "halmaz", "elemek": []}
    if isinstance(ertek, (sp.Interval, sp.Union)) and all(isinstance(d, (sp.Interval, sp.FiniteSet))
                                                          for d in (ertek.args if isinstance(ertek, sp.Union)
                                                                    else (ertek,))):
        darabok = []
        for d in (ertek.args if isinstance(ertek, sp.Union) else (ertek,)):
            if isinstance(d, sp.FiniteSet):
                darabok += [{"a": s(p), "b": s(p), "bal_nyitott": False, "jobb_nyitott": False} for p in d]
            else:
                darabok.append({"a": s(d.start), "b": s(d.end), "bal_nyitott": bool(d.left_open),
                                "jobb_nyitott": bool(d.right_open)})
        return {"tipus": "intervallum", "darabok": darabok[:max_elem]}
    if isinstance(ertek, (sp.FiniteSet, list, tuple, set, frozenset)):
        elemek = list(ertek)
        if any(isinstance(e, (list, tuple, dict, sp.Set)) for e in elemek):
            return {"tipus": "egyeb", "ertek": s(ertek)}
        try:
            elemek = sorted(elemek, key=lambda e: sp.sstr(e))
        except TypeError:
            pass
        return {"tipus": "halmaz", "elemek": [s(e) for e in elemek[:max_elem]]}
    if isinstance(ertek, (int, float)) or isinstance(ertek, sp.Expr):
        return {"tipus": "kifejezes", "ertek": s(ertek)}
    if isinstance(ertek, sp.Set):
        return {"tipus": "egyeb", "ertek": s(ertek)}
    return {"tipus": "egyeb", "ertek": str(ertek)[:2000]}
