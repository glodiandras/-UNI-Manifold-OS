"""A vault fájlfigyelője: FSEvents (ctypes, telepítés nélkül), tartalékként stat-alapú lekérdezés.

A figyelő csak jelez: a megváltozott vault-relatív (nyers, a lemezen álló) utakat adja a hívónak
(`jelez(utak, teljes)`); hogy mi változott, azt az index dönti el stat és hash alapján. Így a git, az
Obsidian, a Finder vagy egy lánc írása egyformán látszik, és a saját írás sem okoz hamis változást.

`teljes=True`: a kernel eldobott eseményeket (`MustScanSubDirs`, `UserDropped`, `KernelDropped`), vagy a
gyökér megváltozott (`RootChanged`, pl. kihúzott SSD): a hívó a megadott alfát (vagy a teljes vaultot)
újra bejárja.

A munkatér mappája (`<vault>/.manifold`: állapot, próbaklónok — F3, I6) a folyamból ki van zárva
(`FSEventStreamSetExclusionPaths`), és ami mégis átjön alóla, azt a callback eldobja; a lekérdező tartalék a
`feloldas.bejaras`-sal jár be, amely a `rejtett` mappákat metszi.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import threading
import unicodedata

from ..config import BUNDLE_ID

# FSEventStreamCreateFlags
_NO_DEFER, _WATCH_ROOT, _FILE_EVENTS = 0x02, 0x04, 0x10
# FSEventStreamEventFlags
_MUST_SCAN, _USER_DROPPED, _KERNEL_DROPPED, _ROOT_CHANGED = 0x01, 0x02, 0x04, 0x20
_SINCE_NOW = 0xFFFFFFFFFFFFFFFF
KIZART = (".manifold",)          # a vault gyökerében: ezek eseményei nem jutnak a hívóhoz (az FSEvents ki is zárja őket)
_UTF8 = 0x08000100


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


class FigyeloHiba(RuntimeError):
    """Az FSEvents nem tölthető be vagy nem indul."""


class FSEvents:
    """FSEvents-folyam a vault gyökerére, saját dispatch-sorral."""

    fajta = "fsevents"

    def __init__(self, root, jelez, latencia: float = 0.03):
        self.root = os.path.realpath(os.fspath(root))
        self._root_nfc = _nfc(self.root)
        self.jelez = jelez
        self.latencia = float(latencia)
        self._stream = self._queue = None
        self._cb = None
        self._lock = threading.Lock()
        try:
            self._cs = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreServices"))
            self._cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
            self._sys = ctypes.CDLL(None)
        except (OSError, TypeError) as e:
            raise FigyeloHiba(f"az FSEvents nem tölthető be: {e}") from e
        self._tipusok()

    def _tipusok(self) -> None:
        cf, cs, sy = self._cf, self._cs, self._sys
        vp = ctypes.c_void_p
        cf.CFStringCreateWithCString.restype = vp
        cf.CFStringCreateWithCString.argtypes = [vp, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFArrayCreate.restype = vp
        cf.CFArrayCreate.argtypes = [vp, ctypes.POINTER(vp), ctypes.c_long, vp]
        cf.CFRelease.argtypes = [vp]
        self._CB = ctypes.CFUNCTYPE(None, vp, vp, ctypes.c_size_t, ctypes.POINTER(ctypes.c_char_p),
                                    ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint64))
        cs.FSEventStreamCreate.restype = vp
        cs.FSEventStreamCreate.argtypes = [vp, self._CB, vp, vp, ctypes.c_uint64, ctypes.c_double, ctypes.c_uint32]
        cs.FSEventStreamSetDispatchQueue.argtypes = [vp, vp]
        cs.FSEventStreamSetExclusionPaths.argtypes = [vp, vp]
        cs.FSEventStreamSetExclusionPaths.restype = ctypes.c_bool
        cs.FSEventStreamStart.restype = ctypes.c_bool
        cs.FSEventStreamStart.argtypes = [vp]
        for f in ("FSEventStreamStop", "FSEventStreamInvalidate", "FSEventStreamRelease"):
            getattr(cs, f).argtypes = [vp]
        sy.dispatch_queue_create.restype = vp
        sy.dispatch_queue_create.argtypes = [ctypes.c_char_p, vp]
        sy.dispatch_release.argtypes = [vp]
        self._DISPATCH_CB = ctypes.CFUNCTYPE(None, vp)
        sy.dispatch_sync_f.argtypes = [vp, vp, self._DISPATCH_CB]
        sy.dispatch_sync_f.restype = None
        self._sor_ures = self._DISPATCH_CB(lambda _: None)
        self._array_cb = ctypes.c_void_p.in_dll(cf, "kCFTypeArrayCallBacks")

    def _esemeny(self, stream, info, n, utak, jelek, azonok):
        valtozott, teljes = [], []
        for i in range(n):
            try:
                p = _nfc(os.fsdecode(utak[i]))
            except (UnicodeDecodeError, TypeError):
                continue
            fl = jelek[i]
            if fl & _ROOT_CHANGED:
                teljes.append("")
                continue
            if p != self._root_nfc and not p.startswith(self._root_nfc + "/"):
                continue
            rel = p[len(self._root_nfc) + 1:] if p != self._root_nfc else ""
            if rel.split("/", 1)[0] in KIZART:
                continue
            if fl & (_MUST_SCAN | _USER_DROPPED | _KERNEL_DROPPED):
                teljes.append(rel)
            elif rel:
                valtozott.append(rel)
        try:
            if valtozott:
                self.jelez(valtozott, False)
            for rel in dict.fromkeys(teljes):
                self.jelez([rel], True)
        except Exception:  # noqa: BLE001 — a GCD-szálon kivétel nem szállhat el
            pass

    def indit(self) -> None:
        cf, cs = self._cf, self._cs
        with self._lock:
            if self._stream:
                return
            s = cf.CFStringCreateWithCString(None, self.root.encode("utf-8"), _UTF8)
            arr = (ctypes.c_void_p * 1)(s)
            paths = cf.CFArrayCreate(None, arr, 1, ctypes.addressof(self._array_cb))
            self._cb = self._CB(self._esemeny)
            stream = cs.FSEventStreamCreate(None, self._cb, None, paths, _SINCE_NOW, self.latencia,
                                            _NO_DEFER | _WATCH_ROOT | _FILE_EVENTS)
            cf.CFRelease(paths)
            cf.CFRelease(s)
            if not stream:
                raise FigyeloHiba("az FSEventStreamCreate nem adott folyamot")
            self._kizar(stream)
            q = self._sys.dispatch_queue_create(f"{BUNDLE_ID}.index.fsevents".encode(), None)
            cs.FSEventStreamSetDispatchQueue(stream, q)
            if not cs.FSEventStreamStart(stream):
                cs.FSEventStreamInvalidate(stream)
                self._sys.dispatch_sync_f(q, None, self._sor_ures)
                cs.FSEventStreamRelease(stream)
                self._sys.dispatch_release(q)
                raise FigyeloHiba("az FSEventStreamStart nem indult")
            self._stream, self._queue = stream, q

    def _kizar(self, stream) -> None:
        """A `KIZART` mappák kizárása a folyamból (az indítás előtt; legfeljebb 8 út). Hiba nem állít meg semmit: a callback
        szűrője akkor is eldobja az eseményeiket."""
        cf = self._cf
        nevek = [n for n in (cf.CFStringCreateWithCString(None, os.path.join(self.root, k).encode("utf-8"), _UTF8)
                             for k in KIZART) if n]
        try:
            if not nevek:
                return
            arr = (ctypes.c_void_p * len(nevek))(*nevek)
            paths = cf.CFArrayCreate(None, arr, len(nevek), ctypes.addressof(self._array_cb))
            if not paths:
                return
            try:
                self._cs.FSEventStreamSetExclusionPaths(stream, paths)
            finally:
                cf.CFRelease(paths)
        finally:
            for n in nevek:
                cf.CFRelease(n)

    def leallit(self) -> None:
        # A hívó az index kezelőszála, soha nem az FSEvents saját callbackje.
        # Invalidate után még lehet folyó/várakozó callback. A sor kiürítéséig a ctypes closure éljen:
        # különben a Python GC felszabadíthatja, miközben a GCD még meghívja (CX-014, reprodukált SIGSEGV).
        with self._lock:
            stream, q = self._stream, self._queue
            if stream:
                cs = self._cs
                cs.FSEventStreamStop(stream)
                cs.FSEventStreamInvalidate(stream)
                self._sys.dispatch_sync_f(q, None, self._sor_ures)
                cs.FSEventStreamRelease(stream)
                self._sys.dispatch_release(q)
                self._stream = self._queue = None
                self._cb = None


class Lekerdezo:
    """Tartalék: `mp` másodpercenként stat-bejárás; a méret vagy az mtime változása = esemény."""

    fajta = "lekerdezes"

    def __init__(self, root, jelez, mp: float = 2.0, bejaras=None):
        from .feloldas import bejaras as _b
        self.root, self.jelez, self.mp = os.fspath(root), jelez, float(mp)
        self._bejaras = bejaras or _b
        self._stop = threading.Event()
        self._szal: threading.Thread | None = None
        self._elozo: dict[str, tuple[int, int]] | None = None

    def _pillanat(self) -> dict[str, tuple[int, int]]:
        out = {}
        for _, lemez in self._bejaras(self.root):
            try:
                st = os.stat(os.path.join(self.root, lemez))
                out[lemez] = (st.st_size, st.st_mtime_ns)
            except OSError:
                pass
        return out

    def _fut(self) -> None:
        while not self._stop.wait(self.mp):
            if not os.path.isdir(self.root):
                continue
            most = self._pillanat()
            elozo = self._elozo or {}
            valt = [k for k, v in most.items() if elozo.get(k) != v] + [k for k in elozo if k not in most]
            self._elozo = most
            if valt:
                try:
                    self.jelez(valt, False)
                except Exception:  # noqa: BLE001
                    pass

    def indit(self) -> None:
        if self._szal:
            return
        self._elozo = self._pillanat() if os.path.isdir(self.root) else {}
        self._szal = threading.Thread(target=self._fut, name="index-lekerdezo", daemon=True)
        self._szal.start()

    def leallit(self) -> None:
        self._stop.set()
        if self._szal:
            self._szal.join(5)
            self._szal = None


def keszit(root, jelez, fajta: str = "fsevents", latencia: float = 0.03, mp: float = 2.0):
    """A kért figyelő; ha az FSEvents nem indul, a lekérdező tartalék."""
    if fajta == "fsevents":
        try:
            f = FSEvents(root, jelez, latencia)
            f.indit()
            return f
        except FigyeloHiba:
            pass
    f = Lekerdezo(root, jelez, mp)
    f.indit()
    return f
