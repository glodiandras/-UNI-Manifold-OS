"""A program-homokozó biztonsági próbái ezen a gépen (C36a): `bin/mos cpp homokozo-proba` és a tesztek közös készlete.

Minden próba egy kitörési vagy korlát-kísérlet, és akkor RENDBEN, ha a homokozó nem engedi (illetve ha a megengedett dolog
működik). A futtató és a fordító profil külön próbákat kap, rendszer-binárisokkal (`/bin/bash`, `/bin/cat`, a hordozható
Python: a profil szempontjából mind egy Mach-O program) és, ha az eszközlánc megvan, lefordított C++-szal. A próbák a vaultot
és a home-ot csak olvasni próbálják, írni csak a saját ideiglenes mappájukba; a kitörés-ellenőrzést a szülő végzi (a fájl nem
jött létre).
"""
from __future__ import annotations

import os
import shlex
import shutil
import sys
import tempfile
import time
from pathlib import Path

from core import cpp_teszt as T
from modulok.homokozo.program import Programhomokozo

from . import ellenorzes
from .eszkoztar import Eszkoztar

PY = Path(os.path.realpath(sys.executable))
PY_PREFIX = Path(os.path.realpath(sys.base_prefix))

# Egy lefordított C++ program, amely mindent megpróbál, amit a futtató profil tilt; a stdin három sora: a titkos fájl, egy
# munkán kívüli írandó fájl, egy munkán kívüli mappa. A várt kimenet a `KITORES_VART`.
KITORES_CPP = r'''
#include <cstdio>
#include <cstdlib>
#include <cerrno>
#include <csignal>
#include <iostream>
#include <string>
#include <fstream>
#include <dirent.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
using namespace std;
static void jel(const char* nev, bool engedett) { cout << nev << (engedett ? " ENGEDETT" : " TILTOTT") << "\n"; }
int main() {
    string titok, kint_ir, mappa;
    getline(cin, titok); getline(cin, kint_ir); getline(cin, mappa);
    { FILE* f = fopen(titok.c_str(), "r"); jel("olvas_kint", f != nullptr); }
    { FILE* f = fopen(kint_ir.c_str(), "w"); jel("ir_kint", f != nullptr); if (f) fclose(f); }
    { FILE* f = fopen("munka.txt", "w"); jel("ir_munka", f != nullptr); if (f) fclose(f); }
    { int s = socket(AF_INET, SOCK_STREAM, 0); sockaddr_in a{}; a.sin_family = AF_INET; a.sin_port = htons(9);
      inet_pton(AF_INET, "127.0.0.1", &a.sin_addr); jel("tcp", s >= 0 && connect(s, (sockaddr*)&a, sizeof a) == 0); }
    { jel("fork", fork() != -1); }
    { jel("exec", system("echo x > /dev/null") == 0); }
    { jel("jel", kill(1, 0) == 0); }
    { DIR* d = opendir(mappa.c_str()); jel("lista", d != nullptr); }
}
'''
KITORES_VART = ("olvas_kint TILTOTT\nir_kint TILTOTT\nir_munka ENGEDETT\ntcp TILTOTT\nfork TILTOTT\nexec TILTOTT\n"
                "jel TILTOTT\nlista TILTOTT\n")


def _q(p) -> str:
    return shlex.quote(str(p))


class _Probak:
    def __init__(self, cfg, ph: Programhomokozo, e: Eszkoztar | None):
        self.cfg, self.ph, self.e = cfg, ph, e
        alap = cfg.path("tmp")
        alap.mkdir(parents=True, exist_ok=True)
        self.t = Path(tempfile.mkdtemp(prefix="mos-hk-proba-", dir=alap)).resolve()
        self.kint = self.t / "kint"
        self.kint.mkdir()
        (self.kint / "titok.txt").write_text("TITOK\n")
        self.sdk, self.pot = self.t / "sdk", self.t / "pot"
        for d in (self.sdk, self.pot):
            d.mkdir()
        self.sorok: list[dict] = []
        self._n = 0

    def munka(self) -> Path:
        self._n += 1
        m = self.t / f"munka-{self._n}"
        m.mkdir()
        return m

    def fut(self, nev: str, f, kell: str | None = None):
        """`f()` → (rendben, allapot, uzenet, csucs_mb)."""
        if kell:
            self.sorok.append({"nev": nev, "rendben": True, "kihagyva": True, "allapot": "kihagyva", "uzenet": kell, "csucs_mb": 0.0})
            return
        try:
            ok, allapot, uzenet, csucs = f()
        except Exception as exc:                                  # egy próba hibája nem viszi a többit
            ok, allapot, uzenet, csucs = False, "kivetel", f"{type(exc).__name__}: {exc}", 0.0
        self.sorok.append({"nev": nev, "rendben": bool(ok), "kihagyva": False, "allapot": allapot, "uzenet": uzenet,
                           "csucs_mb": csucs})

    # -- futtató profil, rendszer-binárisokkal
    def bash(self, szkript, **kw):
        return self.ph.futtat(Path("/bin/bash"), argv=["-c", szkript], munka=self.munka(), **kw)

    def python(self, kod, **kw):
        kw.setdefault("memoria_mb", 512)
        return self.ph.futtat(PY, argv=["-I", "-B", "-X", "utf8", "-c", kod], munka=self.munka(), bin_mappa=PY_PREFIX, **kw)

    def fordit(self, szkript, **kw):
        return self.ph.fordit(["/bin/bash", "-c", szkript], munka=self.munka(), llvm=Path("/bin"), llvm_bin=Path("/bin"),
                              sdk=self.sdk, pot=self.pot, **kw)


def _tag(e: dict) -> tuple:
    return e["allapot"], e.get("uzenet") or "", e.get("csucs_mb", 0.0)


def futtat(cfg, ph: Programhomokozo | None = None, e: Eszkoztar | None = None) -> list[dict]:
    """A teljes készlet → [{nev, rendben, kihagyva, allapot, uzenet, csucs_mb}] (a sorrend a futtatás sorrendje)."""
    ph = ph or Programhomokozo(cfg)
    try:
        e = e or Eszkoztar(cfg)
    except (ValueError, KeyError):
        e = None
    p = _Probak(cfg, ph, e)
    try:
        _futtato_probak(p)
        _fordito_probak(p)
        _cpp_probak(p)
    finally:
        shutil.rmtree(p.t, ignore_errors=True)
    return p.sorok


def _futtato_probak(p: _Probak) -> None:
    kint_ir, szulo = p.kint / "kint.txt", p.t / "szulo.txt"

    def f1():
        r = p.ph.futtat(Path("/bin/cat"), bemenet=b"hello\n", munka=p.munka())
        return r["allapot"] == "ok" and r["stdout"] == b"hello\n", *_tag(r)
    p.fut("F1 rendes program (stdin → stdout)", f1)

    def f2():
        r = p.bash(f"echo ok > a.txt; echo tiltott > {_q(kint_ir)}")
        return (not kint_ir.exists()) and b"Operation not permitted" in r["stderr"], *_tag(r)
    p.fut("F2 írás: a munka/ engedett, máshova tiltott", f2)

    def f3():
        r = p.bash(f"read -r x < {_q(p.kint / 'titok.txt')}; echo \"[$x]\"")
        return b"TITOK" not in r["stdout"] and b"Operation not permitted" in r["stderr"], *_tag(r)
    p.fut("F3 olvasás a munkán kívül tiltott", f3)

    def f4():
        r = p.bash("exec 3<>/dev/tcp/127.0.0.1/9")
        return r["kilepes"] != 0 and b"Operation not permitted" in r["stderr"], *_tag(r)
    p.fut("F4 hálózat (TCP) tiltott", f4)

    def f5():
        r1, r2 = p.bash("/bin/ls /"), p.bash("(echo gyermek)")
        return r1["kilepes"] == 126 and b"gyermek" not in r2["stdout"] and b"fork" in r2["stderr"], *_tag(r1)
    p.fut("F5 másik program indítása és fork tiltott", f5)

    def f6():
        r1, r2 = p.bash("kill -0 1"), p.bash("kill -ABRT $$")
        return r1["kilepes"] != 0 and r2["jel"] == "SIGABRT", *_tag(r2)
    p.fut("F6 jel másik folyamatnak tiltott, az önjel (abort) működik", f6)

    def f7():
        r = p.bash("while :; do :; done", idokorlat_s=0.6)
        el = True
        try:
            os.kill(r["pid"], 0)
        except ProcessLookupError:
            el = False
        return r["allapot"] == "idotullepes" and not el, *_tag(r)
    p.fut("F7 végtelen ciklus: időtúllépés, nincs árva folyamat", f7)

    def f8():
        r = p.python("x = [0] * (10**8)\nprint(len(x))", memoria_mb=256)
        return r["allapot"] == "memoria", *_tag(r)
    p.fut("F8 memória: a korlát fölött leáll (256 MB)", f8)

    def f9():
        r = p.python("import sys\nwhile True: sys.stdout.buffer.write(b'x' * 1000000)", kimenet_max_kb=1024, idokorlat_s=5)
        return r["allapot"] == "kimenet_tullepes", *_tag(r)
    p.fut("F9 kimenet-áradat (stdout)", f9)

    def f10():
        r = p.python("f = open('nagy.bin', 'wb')\nwhile True: f.write(b'x' * 1000000)", munka_max_mb=4, idokorlat_s=5)
        return r["allapot"] == "iras_korlat", *_tag(r)
    p.fut("F10 lemez-áradat: nagy fájl a munka/ mappában", f10)

    def f10b():
        r = p.python("i = 0\nwhile True:\n    open(f'f{i}', 'w').close()\n    i += 1", munka_max_fajl=100, idokorlat_s=5)
        return r["allapot"] == "iras_korlat", *_tag(r)
    p.fut("F10 lemez-áradat: sok fájl a munka/ mappában", f10b)

    def f11():
        adat = os.urandom(3_000_000)
        r = p.ph.futtat(Path("/bin/cat"), bemenet=adat, munka=p.munka(), kimenet_max_kb=8192, idokorlat_s=10)
        return r["allapot"] == "ok" and r["stdout"] == adat, *_tag(r)
    p.fut("F11 nagy bemenet és kimenet egyszerre (nincs holtpont)", f11)

    def f12():
        r = p.python("import ctypes\nctypes.string_at(0)")
        return r["allapot"] == "jel" and r["jel"] == "SIGSEGV", *_tag(r)
    p.fut("F12 szegmentációs hiba: jel, nem a homokozó hibája", f12)

    def f13():
        p.bash("while :; do :; done", idokorlat_s=0.4)
        r = p.ph.futtat(Path("/bin/cat"), bemenet=b"ujra\n", munka=p.munka())
        return r["allapot"] == "ok" and r["stdout"] == b"ujra\n", *_tag(r)
    p.fut("F13 a leállított futás után a következő tiszta", f13)

    def f14():
        t0 = time.monotonic()
        r = p.bash("while :; do :; done", idokorlat_s=30, megszakit=lambda: time.monotonic() - t0 > 0.3)
        return r["allapot"] == "megszakitva" and r["ido_ms"] < 3000, *_tag(r)
    p.fut("F14 megszakítás: a futás leáll", f14)


def _fordito_probak(p: _Probak) -> None:
    kint_ir = p.kint / "prog"

    def c1():
        r = p.fordit(f"echo kesz > prog; echo x > {_q(kint_ir)}")
        return not kint_ir.exists() and r["kilepes"] != 0, *_tag(r)
    p.fut("P1 fordító-profil: írás a munka/ engedett, máshova tiltott", c1)

    def c2():
        r = p.fordit(f"read -r c < {_q(p.kint / 'titok.txt')}; echo \"[$c]\"")
        return "TITOK" not in r["stdout"] and "Operation not permitted" in r["stderr"], *_tag(r)
    p.fut("P2 fordító-profil: olvasás a munkán kívül tiltott", c2)

    def c3():
        r = p.fordit("exec 3<>/dev/tcp/127.0.0.1/9")
        r2 = p.fordit("/usr/bin/true")
        return r["kilepes"] != 0 and r2["kilepes"] != 0 and "Operation not permitted" in r2["stderr"], *_tag(r)
    p.fut("P3 fordító-profil: hálózat és az eszközláncon kívüli program tiltott", c3)

    def c4():
        r = p.fordit("while :; do :; done", idokorlat_s=0.5)
        return r["allapot"] == "idotullepes", *_tag(r)
    p.fut("P4 fordító-profil: időkorlát", c4)

    def c5():                                       # Audit 3 A3-07: a fordítás lemezkorlátja (a gyermekére is)
        # a fordító-profil csak a `llvm_bin` mappából enged exec-et (itt /bin): a `/usr/bin/head` nem indulna el, a `/bin/dd igen
        # (a /dev/urandom olvasható a profilban); a `bash -c` a gyermek-örökléshez kell (a dd a bash gyermeke)
        r = p.fordit("/bin/bash -c '/bin/dd if=/dev/urandom of=prog bs=1048576 count=20 2>/dev/null'; exit 1", munka_max_mb=8)
        return r["allapot"] == "iras_korlat", *_tag(r)
    p.fut("P5 fordító-profil: lemezkorlát (RLIMIT_FSIZE a gyermekre is, munka/-méret)", c5)

    def c6():                                       # Audit 3 A3-16: a folyamatcsoport memóriája
        r = p.fordit("/bin/bash -c 's=$(printf \"%*s\" 400000000 \"\"); sleep 10'", memoria_mb=150, idokorlat_s=20)
        return r["allapot"] == "memoria", *_tag(r)
    p.fut("P6 fordító-profil: a gyermekfolyamat memóriája is számít (csoport-összeg)", c6)


def _cpp_probak(p: _Probak) -> None:
    e = p.e
    hiany = None if (e is not None and e.kesz() and e.sdk_tbd_igazitva()) else \
        "nincs C++ eszköztár vagy az SDK-másolat nincs igazítva (bin/mos cpp telepit --igen)"
    forras_ut = p.t / "proba.cpp"

    def futtat_cpp(forras: str, tesztek: list, mod: str = "gyors") -> tuple[dict, list[dict]]:
        forras_ut.write_text(forras, encoding="utf-8")
        esem: list[dict] = []
        r = ellenorzes.Ellenorzes(p.cfg, esemeny=esem.append, eszkoztar=e, homokozo=p.ph).fut(forras_ut, tesztek, mod)
        return r, esem

    def elso_teszt(esem: list[dict]) -> dict:
        return next((x["teszt"] for x in esem if x["szakasz"] == "teszt"),
                    {"allapot": "nincs_teszt", "uzenet": "", "csucs_mb": 0.0, "jelentes": None})

    def teszt(bemenet: str, kimenet: str) -> T.Teszt:
        return T.Teszt(1, 1, None, bemenet, kimenet, 5.0)

    osszeg = ("#include <iostream>\nint main() {\n    int a, b;\n    std::cin >> a >> b;\n"
              "    std::cout << a + b << \"\\n\";\n}\n")

    def rendes(mod: str):
        def f():
            r, esem = futtat_cpp(osszeg, [teszt("3 4\n", "7\n")], mod)
            t = elso_teszt(esem)
            return r["atment"], t["allapot"], t["uzenet"], t["csucs_mb"]
        return f

    def kitores(mod: str):
        def f():
            bemenet = f"{p.kint / 'titok.txt'}\n{p.kint / 'kint-iras.txt'}\n{p.kint}\n"
            r, esem = futtat_cpp(KITORES_CPP, [teszt(bemenet, KITORES_VART)], mod)
            t = elso_teszt(esem)
            return r["atment"] and not (p.kint / "kint-iras.txt").exists(), t["allapot"], t["uzenet"], t["csucs_mb"]
        return f

    def asan():
        forras = ("#include <iostream>\n#include <vector>\nint main() {\n    std::vector<int> v(3);\n    int s = 0;\n"
                  "    for (int i = 0; i <= 3; i++) s += v[i];\n    std::cout << s << \"\\n\";\n}\n")
        _, esem = futtat_cpp(forras, [teszt("", "0\n")], "hibakereso")
        t = elso_teszt(esem)
        sor = (t.get("jelentes") or {}).get("sor")
        return t["allapot"] == "szanitizer" and sor == 6, t["allapot"], f"forrássor: {sor}", t["csucs_mb"]

    def include_kivul():
        r, esem = futtat_cpp(f'#include "{p.kint}/titok.txt"\nint main() {{}}\n', [teszt("", "")])
        return not r["fordit_ok"] and "TITOK" not in str(esem), "fordit_hiba" if not r["fordit_ok"] else "lefordult", "", 0.0

    def constexpr():
        forras = "constexpr int f(int n) { return f(n + 1); }\nconstexpr int x = f(0);\nint main() { return x; }\n"
        t0 = time.monotonic()
        r, _ = futtat_cpp(forras, [teszt("", "")])
        return not r["fordit_ok"] and time.monotonic() - t0 < 25, "fordit_hiba" if not r["fordit_ok"] else "lefordult", "", 0.0

    p.fut("C4 C++: rendes program lefordul és átmegy (gyors)", rendes("gyors"), hiany)
    p.fut("C4 C++: hibakereső mód lefordul és átmegy (ASan + UBSan)", rendes("hibakereso"), hiany)
    p.fut("F2–F7 lefordított C++ programmal: fájl, hálózat, fork, exec, jel, mappalista tiltva (gyors)", kitores("gyors"), hiany)
    p.fut("F2–F7 lefordított C++ programmal (hibakereső mód)", kitores("hibakereso"), hiany)
    p.fut("C5 C++: ASan túlindexelés a helyes forrássorral", asan, hiany)
    p.fut("C1 C++: `#include` a munkán kívülre nem lát", include_kivul, hiany)
    p.fut("C3 C++: végtelen constexpr nem akasztja meg a fordítót", constexpr, hiany)

    def nagy_objektum():                            # Audit 3 A3-07, a 400 MB-os repró kicsinyítve (8 MB-os korlát)
        m = p.munka()
        (m / "f.cpp").write_text("char a[40000000] = {1};\nint main() { return a[5]; }\n", encoding="utf-8")
        from .eszkoztar import fordit_kornyezet
        r = p.ph.fordit(e.parancs(str(m / "f.cpp"), str(m / "prog"), "gyors"), munka=m, llvm=e.llvm, sdk=e.sdk, pot=e.pot,
                        kornyezet=fordit_kornyezet(m, e.sdk), idokorlat_s=60, munka_max_mb=8)
        meret = sum(f.stat().st_size for f in m.rglob("*") if f.is_file())
        return r["allapot"] == "iras_korlat" and meret <= 8 * 2 ** 20, r["allapot"], f"{meret} bájt", r["csucs_mb"]

    def formaz():                                   # Audit 3 A3-23: a clang-format a fordító-profil alatt
        ok, ki = e.formaz("int main(){return 0;}\n", homokozo=p.ph)
        return ok and ki == "int main() {\n    return 0;\n}\n", "ok" if ok else "hiba", "" if ok else ki[:200], 0.0

    p.fut("C6 C++: a 40 MB-os tömb objektumfájlja a fordítási lemezkorlátba ütközik", nagy_objektum, hiany)
    p.fut("C7 C++: a clang-format a fordító-profil alatt fut", formaz, hiany)
