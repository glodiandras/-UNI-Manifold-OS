"""A szövegkiegészítés (CX-011, J2): fókuszt nem kérő szellemszöveg és kézi hívás (⌘J). A vaultba nem ír.

Három mód (`mod`): `folytat` (a kurzor előtti szöveg folytatása), `kifejt` (a kijelölés kifejtése, a kijelölés után),
`osszefoglal` (a kijelölés összefoglalása, a kijelölés helyére). A javaslat a szerkesztőben díszítés, **csak az elfogadás**
(Tab) teszi a jegyzetbe, egyetlen szerkesztő-tranzakcióval (⌘Z egy lépés).

Forrás: a `folytat` módban előbb a helyi, elfogadott szövegminták (modell nélkül), utána a `general` (a core a
`kiegeszites_modell.general`-t köti be: csak a `[asszisztens.kiegeszites] modell = true` és a router kalibrált sora mellett,
a munkakeretben, a workeren át; a nem mért kérés `proba`-ként jön, D9). Az automatikus (nem kézi) kérést a hangolás
(`Hangolo`, `kiegeszites` fajta, a mód mint helyzet) némíthatja: néma helyzetben modell sem fut.
"""
import re
import threading
import time
from ..utvonalak import HttpError

MODOK = ("folytat", "kifejt", "osszefoglal")
_AZON = re.compile(r"[a-zA-Z0-9-]{12,80}")


class Kiegeszites:
    def __init__(self, allapot, kapcsolo, general=None, megszakit=lambda _: None, hangolo=None):
        self.allapot, self.kapcsolo = allapot, kapcsolo
        self.general = general or (lambda *_: {'szoveg': '', 'ok': 'Nincs kalibrált kiegészítő modell.'})
        self.megszakit = megszakit
        self.hangolo = hangolo
        self._zar = threading.Lock()
        self._fut = threading.Lock()
        self._keresek = {}

    def mintak(self):
        lista = self.allapot.olvas().get('kiegeszites_mintak', [])
        if not isinstance(lista, list): lista = []
        return {'mintak': [m for m in lista if isinstance(m, dict) and isinstance(m.get('elotte'), str)
                          and isinstance(m.get('szoveg'), str)][-50:]}

    def torol(self):
        with self._zar:
            self.allapot.modosit(lambda d: d.update(kiegeszites_mintak=[]))
            for k in self._keresek.values(): k['torolt'] = True
        return {'ok': True}

    def torol_minta(self, elotte):
        """Egy szövegminta törlése (a „Mit tanult” lista egy sora): az előzménye azonosítja."""
        if not isinstance(elotte, str):
            raise HttpError(400, 'Az `elotte` a törlendő minta előzménye.')
        van = any(m['elotte'] == elotte for m in self.mintak()['mintak'])
        if van:
            with self._zar:
                self.allapot.modosit(lambda d: d.update(
                    kiegeszites_mintak=[m for m in self.mintak()['mintak'] if m['elotte'] != elotte]))
        return {'ok': van}

    def tanit(self, d):
        elotte, szoveg = d.get('elotte'), d.get('szoveg')
        if (not isinstance(elotte, str) or not 8 <= len(elotte.strip()) <= 100
                or len(elotte) > 100 or not isinstance(szoveg, str)
                or not szoveg.strip() or len(szoveg) > 800 or '\x00' in elotte + szoveg):
            raise HttpError(400, 'Adj meg 8–100 karakteres előzményt és legfeljebb 800 karakteres folytatást.')
        with self._zar:
            def ir(d):
                regi = [m for m in self.mintak()['mintak'] if m['elotte'] != elotte]
                d['kiegeszites_mintak'] = (regi + [{'elotte': elotte, 'szoveg': szoveg}])[-50:]
            self.allapot.modosit(ir)
        return self.mintak()

    def _allas(self, mod):
        return self.hangolo.allas('kiegeszites', mod) if self.hangolo else None

    def ker(self, d):
        azon, elotte, utana = d.get('azon'), d.get('elotte'), d.get('utana', '')
        mod, kijeloles, kezi = d.get('mod', 'folytat'), d.get('kijeloles', ''), d.get('kezi', False)
        if not isinstance(azon, str) or not _AZON.fullmatch(azon):
            raise HttpError(400, 'Érvénytelen kiegészítésazonosító.')
        if not isinstance(elotte, str) or not isinstance(utana, str) or len(elotte) > 6000 or len(utana) > 2000:
            raise HttpError(400, 'A kiegészítés szövegkörnyezete túl hosszú vagy hiányzik.')
        if mod not in MODOK:
            raise HttpError(400, 'A mód folytat, kifejt vagy osszefoglal lehet.')
        if not isinstance(kijeloles, str) or len(kijeloles) > 4000 or not isinstance(kezi, bool):
            raise HttpError(400, 'A kijelölés legfeljebb 4000 karakter, a `kezi` igaz vagy hamis.')
        if not self.kapcsolo(): return {'szoveg': '', 'ok': 'Az asszisztens ki van kapcsolva.'}
        if mod == 'folytat' and not elotte.strip(): return {'szoveg': '', 'ok': ''}
        if mod != 'folytat' and not kijeloles.strip():
            return {'szoveg': '', 'ok': 'Jelöld ki a kifejtendő vagy összefoglalandó szöveget.'}
        allas = self._allas(mod)
        if not kezi and allas and allas['szint'] == 'nema':
            return {'szoveg': '', 'ok': '', 'nema': True, 'allas': allas}       # a hangolás elnémította: modell sem fut
        with self._zar:
            most = time.monotonic()
            self._keresek = {k: v for k, v in self._keresek.items() if most - v['ido'] < 300}
            while len(self._keresek) >= 128: self._keresek.pop(next(iter(self._keresek)))
            if azon in self._keresek: return {'szoveg': '', 'ok': ''}
            k = {'ido': most, 'elotte': elotte[-100:], 'szoveg': '', 'torolt': False, 'mod': mod, 'proba': False}
            self._keresek[azon] = k
        if not self._fut.acquire(blocking=False): return {'szoveg': '', 'ok': 'Az asszisztens még dolgozik.'}
        try:
            minta = None
            if mod == 'folytat':
                minta = next((m for m in reversed(self.mintak()['mintak'])
                              if len(m['elotte'].strip()) >= 8 and elotte.endswith(m['elotte'])), None)
            r = ({'szoveg': minta['szoveg'], 'forras': 'helyi minta'} if minta
                 else self.general(elotte, utana, azon, mod, kijeloles))
            sz = r.get('szoveg', '')
            if not isinstance(sz, str): sz = ''
            sz = sz[:800 if mod == 'folytat' else 2000].replace('\x00', '')
            with self._zar:
                if k['torolt'] or not self.kapcsolo(): return {'szoveg': '', 'ok': ''}
                k['szoveg'], k['proba'] = sz, bool(r.get('proba'))
            return {**r, 'szoveg': sz, 'azon': azon, 'mod': mod, 'proba': bool(r.get('proba')), 'allas': allas}
        finally:
            self._fut.release()

    def elvet(self, azon, kifejezett=False):
        """A javaslat eldobása. A látott javaslat kifejezett elvetése (Esc) elutasítás, az átírt vagy elhagyott javaslat
        csak kis súlyú „figyelmen kívül” a hangolásban; a még nem látott (folyó) kérés megszakítása nem számít."""
        if not isinstance(azon, str) or not _AZON.fullmatch(azon):
            raise HttpError(400, 'Érvénytelen kiegészítésazonosító.')
        with self._zar:
            k = self._keresek.get(azon)
            if k:
                k['torolt'] = True
                lattott = bool(k['szoveg'])
            else:
                lattott = False
                while len(self._keresek) >= 128: self._keresek.pop(next(iter(self._keresek)))
                self._keresek[azon] = {'ido': time.monotonic(), 'torolt': True, 'szoveg': ''}
        if k: self.megszakit(azon)
        if k and lattott and self.hangolo and self.kapcsolo():
            self.hangolo.rogzit('kiegeszites', k.get('mod', 'folytat'),
                                'elutasit' if kifejezett is True else 'figyelmen_kivul')
        return {'ok': True}

    def elfogad(self, azon):
        if not isinstance(azon, str): raise HttpError(400, 'Érvénytelen kiegészítésazonosító.')
        with self._zar:
            k = self._keresek.pop(azon, None)
            if not self.kapcsolo() or not k or k['torolt'] or not k['szoveg']:
                return {'ok': False}
            if k.get('mod', 'folytat') == 'folytat':
                def ir(d):
                    regi = [m for m in self.mintak()['mintak'] if m['elotte'] != k['elotte']]
                    d['kiegeszites_mintak'] = (regi + [{'elotte': k['elotte'], 'szoveg': k['szoveg']}])[-50:]
                self.allapot.modosit(ir)
        if self.hangolo:
            self.hangolo.rogzit('kiegeszites', k.get('mod', 'folytat'), 'elfogad')
        return {'ok': True}
