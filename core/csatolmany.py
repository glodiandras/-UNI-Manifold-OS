"""CX-004: kézi, darabolt fájlimport. Nem indít AI-t, meglévő fájlt nem ír felül."""
from __future__ import annotations
import base64
import binascii
import contextlib
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from pathlib import Path
from . import frame, rejtett, snapshot, tartos, vaultio
from .utvonalak import HttpError
from .hibakod import kodol

DARAB = 4 * 1024 * 1024
ELAVULT_MP = 24 * 3600          # ennyi ideje nem érintett feltöltési mappa elavult (félbehagyott vagy rég lezárt import)
TAKARITAS_MP = 600              # a takarítás legfeljebb ennyi másodpercenként fut (a feltöltés útvonalán)
_AZON = re.compile('[a-f0-9]{32}')

# Feltöltésenkénti zár, használat-számlálóval: az utolsó kilépő (siker, hiba vagy megszakadt kérés) törli a bejegyzést,
# így a szótár nem nő a feltöltések számával.
_ZARAK: dict[str, list] = {}
_ZARAK_ZAR = threading.Lock()
_utolso_takaritas = 0.0


@contextlib.contextmanager
def _import_zar(azon: str):
    with _ZARAK_ZAR:
        bej = _ZARAK.setdefault(azon, [threading.Lock(), 0])
        bej[1] += 1
    try:
        with bej[0]:
            yield
    finally:
        with _ZARAK_ZAR:
            bej[1] -= 1
            if bej[1] == 0 and _ZARAK.get(azon) is bej:
                del _ZARAK[azon]


@contextlib.contextmanager
def _kor_zar(cfg):
    """A kör-zár a felhasználói műveletnek (import lezárása, új mappa, Kuka): a rövid zár-tartást (bundle) a felhasználói
    türelemmel kivárja (`frame.felhasznaloi_turelem`, mint a visszavonás és az átnevezés); a foglalt zár 409 `foglalt: true`
    (a `frame.Busy` nem 500 — 2026-10-14, F2). A blokkban keletkező `Busy` nem a mi zárunk hibája: változatlanul megy tovább."""
    with contextlib.ExitStack() as verem:
        try:
            verem.enter_context(frame.run_lock(cfg, wait=False, turelem_mp=frame.felhasznaloi_turelem(cfg)))
        except frame.Busy as e:
            raise HttpError(409, 'Egy másik vault-művelet (gépi írás vagy mentés) éppen fut. Próbáld újra egy kicsit később.', kod="csatolmany.masik_vault_muvelet_fut",
                            foglalt=True) from e
        yield


def _legutobb_erintve(m: Path) -> float:
    ido = m.lstat().st_mtime
    for f in m.iterdir():
        with contextlib.suppress(OSError):
            ido = max(ido, f.lstat().st_mtime)
    return ido


def takarit(gyoker: Path, most: float | None = None, kor_mp: float = ELAVULT_MP) -> list[str]:
    """A core saját `{tmp}/csatolmany/` mappájában törli az elavult feltöltési mappákat (§4: a saját `var/tmp` fájljai).

    Csak a 32 hex nevű, nem szimbolikus link mappát, amelyet éppen nem használ feltöltés, és amelynek egyik fájlja sem
    módosult `kor_mp` óta. → a törölt azonosítók."""
    most = time.time() if most is None else most
    torolt = []
    try:
        mappak = list(gyoker.iterdir())
    except OSError:
        return torolt
    for m in mappak:
        if not _AZON.fullmatch(m.name) or m.is_symlink() or not m.is_dir():
            continue
        with _ZARAK_ZAR:
            if m.name in _ZARAK:
                continue
            try:
                if most - _legutobb_erintve(m) < kor_mp:
                    continue
                shutil.rmtree(m)
                torolt.append(m.name)
            except OSError:
                continue
    return torolt


def _takarit_neha(gyoker: Path) -> None:
    global _utolso_takaritas
    most = time.time()
    if most - _utolso_takaritas < TAKARITAS_MP:
        return
    _utolso_takaritas = most
    takarit(gyoker, most)


def nev_ellenor(nev):
    if not isinstance(nev, str) or not nev.strip() or nev.startswith('.') or vaultio._TILTOTT_NEV.search(nev) or len(nev.encode()) > 200:
        raise HttpError(400, 'Érvénytelen fájlnév.', kod="csatolmany.ervenytelen_fajlnev")
    return vaultio.norm_path(nev.strip())


def beallitas(vault_gyoker) -> str:
    """Az `.obsidian/app.json` `attachmentFolderPath` nyers értéke — a beállítás EGYETLEN olvasója (80(c); a CX-004 feltöltése és a
    83. döntés javaslatának `.apkg`-médiája is ezt használja). Csak olvasunk (24(b)). Hiányzó/olvashatatlan fájl vagy kulcs: `''`
    (az Obsidian alapja: a vault gyökere); nem szöveges érték: 400."""
    try:
        cel = json.loads((Path(vault_gyoker) / '.obsidian/app.json').read_text(encoding='utf-8')).get('attachmentFolderPath', '')
    except (OSError, ValueError, AttributeError):
        cel = ''
    if not isinstance(cel, str):
        raise HttpError(400, 'Hibás csatolmány-mappa a vault beállításában.', kod="csatolmany.hibas_csatolmany_mappa")
    return cel


def mappa(vault_gyoker, jegyzet_ut: str) -> str:
    """A `jegyzet_ut` (vault-relatív; nem kell léteznie — az új kísérőjegyzeté is) csatolmány-mappája, vault-relatív NFC úton
    (`''` = a gyökér), az Obsidian szabályával: `''`/`/` → gyökér, `.`/`./x` → a jegyzet mappája (alatta `x`), más → a gyökértől.
    Az érvénytelen mappa (`..`, rejtett vagy a vaultban tiltott jelű szegmens) `vaultio.Invalid`: ilyen helyre semmi nem kerül."""
    jegyzet_ut = vaultio.norm_path(jegyzet_ut)
    cel = vaultio.nfc(beallitas(vault_gyoker)).replace('\\', '/').strip()
    if cel in ('', '/'):
        return ''
    if cel == '.' or cel.startswith('./'):
        cel = str(Path(jegyzet_ut).parent / cel[2:]) if cel != '.' else str(Path(jegyzet_ut).parent)
    if cel in ('', '.'):
        return ''
    cel = vaultio.norm_path(cel)
    if any(vaultio._TILTOTT_NEV.search(r) for r in cel.split('/')):
        raise kodol(vaultio.Invalid(f'a csatolmány-mappa (attachmentFolderPath) érvénytelen: {cel}'), "csatolmany.csatolmany_mappa_attachmentfolderpath_ervenytelen_cel", {"cel": cel})
    return cel


def csatolmany_mappa(v, forras):
    """CX-004: a feltöltés célja a (létező) `forras` jegyzet csatolmány-mappája (`mappa`)."""
    forras = vaultio.norm_path(forras)
    v.lemezen(forras)
    return mappa(v.root, forras)


def kovetett(repo, utak):
    if not utak:
        return []
    p = repo.git('--no-literal-pathspecs', 'check-ignore', '--no-index', '-z', '--stdin',
                 input='\0'.join(utak) + '\0', check=False)
    if p.returncode not in (0, 1):
        raise snapshot.SnapshotError('A pillanatkép-hatókör nem ellenőrizhető.')
    kimarad = set(filter(None, p.stdout.split('\0')))
    return [u for u in utak if u not in kimarad]


def feltolt(app, d):
    v = app.vault
    azon = d.get('azon') or secrets.token_hex(16)
    if not isinstance(azon, str) or not _AZON.fullmatch(azon):
        raise HttpError(400, 'Érvénytelen feltöltésazonosító.', kod="csatolmany.ervenytelen_feltoltesazonosito")
    offset = d.get('offset', 0)
    if type(offset) is not int or offset < 0:
        raise HttpError(400, 'Érvénytelen darabpozíció.', kod="csatolmany.ervenytelen_darabpozicio")
    adat = d.get('adat', '')
    if not isinstance(adat, str) or len(adat) > DARAB * 4 // 3 + 8:
        raise HttpError(413, 'Túl nagy feltöltési darab.', kod="csatolmany.tul_nagy_feltoltesi_darab")
    try:
        bajtok = base64.b64decode(adat, validate=True)
    except (ValueError, binascii.Error):
        raise HttpError(400, 'Hibás feltöltési adat.', kod="csatolmany.hibas_feltoltesi_adat") from None
    gyoker = app.cfg.path('tmp') / 'csatolmany'
    _takarit_neha(gyoker)
    m = gyoker / azon
    with _import_zar(azon):
        eredmeny = m / 'eredmeny.json'
        if eredmeny.exists():
            return json.loads(eredmeny.read_text())
        meta = m / 'meta.json'
        if not meta.exists():
            if offset:
                raise HttpError(409, 'A feltöltés első darabja hiányzik.', kod="csatolmany.elso_darab_hianyzik")
            nev = nev_ellenor(d.get('nev'))
            cel = csatolmany_mappa(v, d['forras']) if d.get('forras') else (vaultio.norm_path(d['mappa']) if d.get('mappa') else '')
            v._abs(cel) if cel else v.root
            m.mkdir(parents=True)
            tartos.atomi_ir(meta, json.dumps({'nev': nev, 'mappa': cel}).encode())
        adatok = json.loads(meta.read_text())
        part = m / 'adat.part'
        hossz = part.stat().st_size if part.exists() else 0
        vege = d.get('vege') is True
        if offset != hossz:
            # Az utolsó darab ismétlése (a lezárás az előző próbán foglalt zárral vagy hibával megállt, a darab már hozzáfűződött):
            # ugyanazzal a tartalommal nem hiba, a lezárás újra fut (2026-10-14, F2).
            if not (vege and bajtok and offset + len(bajtok) == hossz and _vege_egyezik(part, bajtok)):
                raise HttpError(409, 'A feltöltési darabok sorrendje eltér.', kod="csatolmany.darabok_sorrendje_elter", offset=hossz)
        else:
            if hossz + len(bajtok) > 20 * 1024 ** 3:
                raise HttpError(413, 'A fájl nagyobb 20 GiB-nál.', kod="csatolmany.fajl_tul_nagy")
            with part.open('ab') as f:
                f.write(bajtok); f.flush(); os.fsync(f.fileno())
            hossz += len(bajtok)
        if not vege:
            return {'azon': azon, 'offset': hossz, 'kesz': False}
        # A (akár 20 GiB-os) másolás a kör-zár ELŐTT, egy rejtett `.manifold-tmp` célra a célmappában (a pillanatkép kizárja);
        # a zár alatt csak a kézi commit, a névválasztás és az ütközésmentes átnevezés fut — a visszavonást és a gépi írást
        # a másolás nem tartja fel (F2).
        nev = adatok['nev']
        cel_mappa = v._abs(adatok['mappa']) if adatok['mappa'] else v.root
        cel_mappa.mkdir(parents=True, exist_ok=True)
        atmeneti = tartos.tmp_ut(cel_mappa / nev)
        try:
            with part.open('rb') as be, atmeneti.open('xb') as ki:
                shutil.copyfileobj(be, ki, 1024 * 1024)
                ki.flush(); os.fsync(ki.fileno())
            with _kor_zar(app.cfg):
                if not atmeneti.is_file():
                    raise HttpError(409, 'A célmappa a feltöltés közben megváltozott. Próbáld újra.', kod="csatolmany.celmappa_megvaltozott")
                repo = v.repo()
                if repo:
                    repo.commit('kézi változások import előtt', {'Mos-Forras': 'kezi'})
                for i in range(10000):
                    jelolt = nev if i == 0 else f'{Path(nev).stem} {i}{Path(nev).suffix}'
                    if any(vaultio.nfc(n).casefold() == jelolt.casefold() for n in os.listdir(cel_mappa)):
                        continue
                    cel = cel_mappa / jelolt
                    try:
                        tartos.rename_excl(atmeneti, cel)
                    except FileExistsError:
                        continue
                    tartos.fsync_mappa(cel_mappa)
                    break
                else:
                    raise HttpError(409, 'Nincs szabad fájlnév.', kod="csatolmany.nincs_szabad_fajlnev")
                return _lezar(app, v, repo, cel, azon, eredmeny, part)
        finally:
            atmeneti.unlink(missing_ok=True)


def _vege_egyezik(part: Path, bajtok: bytes) -> bool:
    """A részfájl vége bájtra azonos a `bajtok`-kal (az utolsó darab ismétlése)."""
    try:
        with part.open('rb') as f:
            f.seek(-len(bajtok), os.SEEK_END)
            return f.read(len(bajtok)) == bajtok
    except OSError:
        return False


def _lezar(app, v, repo, cel: Path, azon: str, eredmeny: Path, part: Path) -> dict:
    """A bemásolt fájl gépi commitja, a tartós visszaigazolás és az index frissítése (a kör-zár alatt)."""
    rp = vaultio.nfc(cel.relative_to(v.root).as_posix())
    sha, figy = None, None
    if repo:
        try:
            utak = kovetett(repo, [rp])
            if utak:
                sha = repo.commit_machine('kézi fájlimport: ' + rp,
                    {'Mos-Forras': vaultio.FORRAS, 'Mos-Kor': frame.new_id('IMPORT'), 'Mos-Tetel': rp}, utak)
        except snapshot.SnapshotError:
            figy = 'A fájl bemásolódott, a szöveges pillanatkép nem sikerült.'
    r = {'ok': True, 'kesz': True, 'azon': azon, 'ut': rp, 'figyelmeztetes': figy}
    tartos.atomi_ir(eredmeny, json.dumps(r, ensure_ascii=False).encode())
    part.unlink(missing_ok=True)
    # A visszaigazolás előbb tartós: indexhiba miatti újraküldés sem duplikálhat.
    try:
        if not app.index.frissit([app.index.lemez_ut(rp)]):
            r['figyelmeztetes'] = 'A fájl bemásolódott, az index frissítése még folyamatban van.'
    except Exception:
        r['figyelmeztetes'] = 'A fájl bemásolódott, az index frissítése még várat magára.'
    return r


def uj_mappa(app, d):
    szulo = vaultio.norm_path(d['mappa']) if d.get('mappa') else ''
    nev = nev_ellenor(d.get('nev'))
    rp = f'{szulo}/{nev}' if szulo else nev
    with _kor_zar(app.cfg):
        p = app.vault._abs(rp)
        if any(vaultio.nfc(n).casefold() == nev.casefold() for n in os.listdir(p.parent)):
            raise HttpError(409, 'Már van ilyen nevű fájl vagy mappa.', kod="csatolmany.nev_foglalt")
        p.mkdir(); tartos.fsync_mappa(p.parent)
        app.index.frissit([app.index.lemez_ut(rp)])
    return {'ok': True, 'ut': rp}


def hej_cli(cfg) -> Path:
    """A héj futtathatója a `--kuka` CLI-módhoz: az `[utak] hej_cli` (`MOS_HEJ_CLI`); régi konfigurációban a `naptar_seged`.

    Ugyanaz a bináris (32(a): a segéd a Manifold.app futtathatója), de külön kulcs: a tesztek `MOS_NAPTAR_SEGED` ál-segédje így
    nem kapja meg a Kuka-parancsot."""
    return cfg.utak.get('hej_cli') or cfg.path('naptar_seged')


def kuka(app, d, vegrehajt=None):
    if d.get('megerosit') is not True:
        raise HttpError(400, 'A Kukába helyezést meg kell erősíteni.', kod="csatolmany.kuka_megerosites")
    rp = app.vault.kanonikus(vaultio.norm_path(d.get('ut')))
    with _kor_zar(app.cfg), contextlib.ExitStack() as verem:
        p = app.vault.lemezen(rp)
        gy, szulo = app.vault.root.resolve(), p.parent.resolve()
        if not p.name or szulo / p.name == gy or (szulo != gy and gy not in szulo.parents):
            raise HttpError(400, 'Csak a vaulton belüli fájl vagy mappa tehető a Kukába.', kod="csatolmany.csak_vaulton_belul_kukaba")
        utak = [rp]
        if p.is_dir():
            for dp, dn, fn in os.walk(p):        # I6 (F3): a `.manifold` (állapot) nélkül; a többi mappa (`.git`, `node_modules` …) zárolt marad (v2)
                rejtett.metsz_munkater(dn)
                utak += [vaultio.nfc((Path(dp) / f).relative_to(app.vault.root).as_posix()) for f in fn
                         if (Path(dp) / f).is_file()]
        zarak = {}
        for u in sorted(utak, key=lambda u: vaultio.nfc(u).casefold()):
            z = vaultio._ut_zar(u)
            zarak[id(z)] = z
        for z in zarak.values():
            if not z.acquire(timeout=3):
                raise HttpError(409, 'Az egyik fájl mentése még tart. Próbáld újra.', kod="csatolmany.fajl_mentese_tart")
            verem.callback(z.release)
        kulcs = vaultio.nfc(rp).casefold()
        if any(vaultio.nfc(u).casefold() == kulcs or vaultio.nfc(u).casefold().startswith(kulcs + '/') for u in app.atnevezes.mentetlen()):
            raise HttpError(409, 'A fájlban vagy mappában mentetlen dokumentum van.', kod="csatolmany.mentetlen_dokumentum")
        repo = app.vault.repo()
        if repo:
            repo.commit('kézi változások a Kukába helyezés előtt', {'Mos-Forras': 'kezi'})
        if vegrehajt:
            vegrehajt(p)
        else:
            valasz: dict = {}
            try:
                # a gyökeret a segéd is ellenőrzi (`shell/Sources/Kuka.swift`): csak a vault alatti elemet teszi a Kukába
                h = subprocess.run([str(hej_cli(app.cfg)), '--kuka'],
                                   input=json.dumps({'ut': str(p), 'gyoker': str(app.vault.root)}),
                                   capture_output=True, text=True, timeout=60)
                with contextlib.suppress(ValueError):
                    valasz = json.loads(h.stdout or '{}')
                if not isinstance(valasz, dict):
                    valasz = {}
                siker = h.returncode == 0 and valasz.get('ok') is True
            except (OSError, subprocess.TimeoutExpired):
                siker = False
            if not siker:
                uzenet, mezok = _kuka_hiba(valasz, p, app.vault.root)
                raise HttpError(503, uzenet, **mezok)
        app.index.frissit([app.index.lemez_ut(rp)])

    return {'ok': True}


def _kuka_hiba(valasz: dict, p: Path, gyoker: Path) -> tuple:
    """A Kuka-segéd hibaválaszából (`{"ok": false, "kod", "hiba"}`, `shell/Sources/Kuka.swift`) a HttpError üzenete és mezői:
    a segéd magyar szövege (abszolút út nélkül, 78(e): a vault-útból legfeljebb a relatív rész marad), a `kod` a válasz
    `kod` mezőjébe (a `cpp_utvonal` mintája). Régi segéd vagy olvashatatlan válasz: az általános üzenet."""
    alap = 'A macOS Kuka nem jelezte vissza a műveletet. Ellenőrizd a fájlfát és a Kukát.'
    hiba, kod = valasz.get('hiba'), valasz.get('kod')
    if not isinstance(hiba, str) or not hiba.strip():
        hiba = alap
    for abs_ut, helyette in ((str(p), p.name), (str(gyoker), 'a vault')):
        if abs_ut and abs_ut != '/':
            hiba = hiba.replace(abs_ut, helyette)
    hiba = hiba.strip()[:500]
    return (hiba, {'kod': kod} if isinstance(kod, str) and re.fullmatch(r'[a-z_]{1,40}', kod) else {})


def utvonalak(r):
    r.post('/api/vault/import', lambda k: feltolt(k.app, k.torzs()))
    r.post('/api/vault/mappa', lambda k: uj_mappa(k.app, k.torzs()))
    r.post('/api/vault/kuka', lambda k: kuka(k.app, k.torzs()))
