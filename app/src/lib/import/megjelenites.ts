// Az importok állandó szövegei és segédei. A szövegek `tk()`-val jelöltek (a ratchet nem enged dinamikus kulcsot), megjelenítéskor
// `t()` fordít. A core stabil kódjait (akadály, figyelmeztetés, kihagyás oka, hibakód) itt fordítjuk érthető mondattá.
import { ApiHiba, hibaUzenet } from '../core/api';
import { locale, t, tk } from '../i18n';
import type { ImportAllapot, ImportAllapotKod } from './tipusok';

/** A felhasználónak mutatható szöveg a kód táblájából; ismeretlen kódnál az általános tartalék. */
export function kodSzoveg(tabla: Record<string, string>, kod: string, tartalek: string): string {
  return t(Object.hasOwn(tabla, kod) ? tabla[kod] : tartalek);
}

/** Akadályok: az import nem indulhat (az előnézet `akadaly` kódjai és az `import.tilos` hiba `param.akadaly`-ja). */
export const AKADALY: Record<string, string> = {
  forras_nem_mappa: tk('import.akadaly.forras_nem_mappa'),
  forras_nem_olvashato: tk('import.akadaly.forras_nem_olvashato'),
  cel_a_forrasban: tk('import.akadaly.cel_a_forrasban'),
  forras_a_celban: tk('import.akadaly.forras_a_celban'),
  cel_nem_ures: tk('import.akadaly.cel_nem_ures'),
  cel_munkater: tk('import.akadaly.cel_munkater'),
  nev_utkozes: tk('import.akadaly.nev_utkozes'),
  fajl_utkozes: tk('import.akadaly.fajl_utkozes'),
  keves_hely: tk('import.akadaly.keves_hely'),
  nincs_install: tk('import.akadaly.nincs_install'),
  import_fut: tk('import.akadaly.import_fut'),
  hordozhato_elrendezes: tk('import.akadaly.hordozhato_elrendezes'),
  nem_mappa: tk('import.akadaly.nem_mappa'),
  nem_letezik: tk('import.akadaly.nem_letezik'),
  szulo_hianyzik: tk('import.akadaly.szulo_hianyzik'),
  nem_irhato: tk('import.akadaly.nem_irhato'),
  kodfaban: tk('import.akadaly.kodfaban'),
  telepitesben: tk('import.akadaly.telepitesben'),
  kodfat_tartalmaz: tk('import.akadaly.kodfat_tartalmaz'),
  telepitest_tartalmaz: tk('import.akadaly.telepitest_tartalmaz'),
  munkateren_belul: tk('import.akadaly.munkateren_belul'),
  munkater_symlink: tk('import.akadaly.munkater_symlink'),
  workspace_toml_hibas: tk('import.akadaly.workspace_toml_hibas'),
  workspace_id_hibas: tk('import.akadaly.workspace_id_hibas'),
  workspace_ujabb: tk('import.akadaly.workspace_ujabb'),
  munkateret_tartalmaz: tk('import.akadaly.munkateret_tartalmaz'),
  masik_telepites_fut: tk('import.akadaly.masik_telepites_fut'),
  halozati_kotet: tk('import.akadaly.halozati_kotet'),
  nincs_munkater: tk('import.akadaly.nincs_munkater'),
  v2_nincs_konfig: tk('import.akadaly.v2_nincs_konfig'),
  v2_toml_hibas: tk('import.akadaly.v2_toml_hibas'),
  sema_cel_kivul: tk('import.akadaly.sema_cel_kivul'),
};
export const AKADALY_TARTALEK = tk('import.akadaly.ismeretlen');

export const FIGYELMEZTETES: Record<string, string> = {
  forras_munkater: tk('import.figy.forras_munkater'),
  keves_hely: tk('import.figy.keves_hely'),
  kihagyott_elemek: tk('import.figy.kihagyott_elemek'),
  nem_tamogatott_pluginok: tk('import.figy.nem_tamogatott_pluginok'),
  nagy_vault: tk('import.figy.nagy_vault'),
  nem_apfs: tk('import.figy.nem_apfs'),
  szinkron_mappa: tk('import.figy.szinkron_mappa'),
  allapot_mas_koteten: tk('import.figy.allapot_mas_koteten'),
  utkozes_kihagyva: tk('import.figy.utkozes_kihagyva'),
};
export const FIGYELMEZTETES_TARTALEK = tk('import.figy.ismeretlen');

export const KIHAGYAS_OKA: Record<string, string> = {
  olvashatatlan: tk('import.kihagy.olvashatatlan'),
  nev_ervenytelen: tk('import.kihagy.nev_ervenytelen'),
  symlink: tk('import.kihagy.symlink'),
  manifold: tk('import.kihagy.manifold'),
  git: tk('import.kihagy.git'),
  opcio: tk('import.kihagy.opcio'),
  obsidian_kuka: tk('import.kihagy.obsidian_kuka'),
  rejtett: tk('import.kihagy.rejtett'),
  rendszer: tk('import.kihagy.rendszer'),
  specialis: tk('import.kihagy.specialis'),
};
export const KIHAGYAS_TARTALEK = tk('import.kihagy.ismeretlen');

export const UTKOZES_OKA: Record<string, string> = {
  kis_nagy: tk('import.utkozes.kis_nagy'),
  normalizalas: tk('import.utkozes.normalizalas'),
  cel_elter: tk('import.utkozes.cel_elter'),
  olvashatatlan: tk('import.utkozes.olvashatatlan'),
  sema_elter: tk('import.utkozes.sema_elter'),
};
export const UTKOZES_TARTALEK = tk('import.utkozes.ismeretlen');

export const NEM_ATVETT_OKA: Record<string, string> = {
  opcio: tk('import.nematvett.opcio'),
  hianyzik: tk('import.nematvett.hianyzik'),
  tul_nagy: tk('import.nematvett.tul_nagy'),
  hibas_json: tk('import.nematvett.hibas_json'),
  ervenytelen: tk('import.nematvett.ervenytelen'),
  nem_tamogatott: tk('import.nematvett.nem_tamogatott'),
  masolva_nem_olvasott: tk('import.nematvett.masolva_nem_olvasott'),
  sema_hibas: tk('import.nematvett.sema_hibas'),
  // 13-palette-01: a hotkeys.json soronkénti jelentése (semmi sem marad ki csendben)
  hotkey_nincs_parancs: tk('import.nematvett.hotkey_nincs_parancs'),
  hotkey_ures: tk('import.nematvett.hotkey_ures'),
  hotkey_ervenytelen: tk('import.nematvett.hotkey_ervenytelen'),
  hotkey_foglalt: tk('import.nematvett.hotkey_foglalt'),
  hotkey_utkozes: tk('import.nematvett.hotkey_utkozes'),
  hotkey_tobb: tk('import.nematvett.hotkey_tobb'),
};
export const NEM_ATVETT_TARTALEK = tk('import.nematvett.ismeretlen');

export const BEALLITAS_MOD: Record<string, string> = {
  ir: tk('import.beallitas.mod.ir'),
  azonos: tk('import.beallitas.mod.azonos'),
  munkater: tk('import.beallitas.mod.munkater'),
  kozvetlen: tk('import.beallitas.mod.kozvetlen'),
};

/** A leképezett beállítások neve (a core pontozott kulcsa a „beallitasok.” előtag nélkül). */
export const BEALLITAS_CIM: Record<string, string> = {
  'fajlok.wikilinkek': tk('import.beallitas.wikilinkek'),
  'fajlok.link_formatum': tk('import.beallitas.link_formatum'),
  'fajlok.csatolmany_mappa': tk('import.beallitas.csatolmany_mappa'),
  'fajlok.uj_mappa': tk('import.beallitas.uj_mappa'),
  'szerkeszto.olvashato_szelesseg': tk('import.beallitas.olvashato_szelesseg'),
  'szerkeszto.helyesiras': tk('import.beallitas.helyesiras'),
  'szerkeszto.tab_meret': tk('import.beallitas.tab_meret'),
  'szerkeszto.mod': tk('import.beallitas.szerkeszto_mod'),
  'megjelenes.betumeret': tk('import.beallitas.betumeret'),
  'megjelenes.tema': tk('import.beallitas.tema'),
  'sablon.datum': tk('import.beallitas.sablon_datum'),
  'sablon.ido': tk('import.beallitas.sablon_ido'),
  'sablon.mappa': tk('import.beallitas.sablon_mappa'),
  'naplo.ut': tk('import.beallitas.naplo_ut'),
  'naplo.sablon': tk('import.beallitas.naplo_sablon'),
  tulajdonsag_tipusok: tk('import.beallitas.tulajdonsag_tipusok'),
};
const ERTEK_CIM: Record<string, string> = {
  rovid: tk('import.ertek.rovid'), relativ: tk('import.ertek.relativ'), abszolut: tk('import.ertek.abszolut'),
  rendszer: tk('import.ertek.rendszer'), vilagos: tk('import.ertek.vilagos'), sotet: tk('import.ertek.sotet'),
  elo: tk('import.ertek.elo'), forras: tk('import.ertek.forras'),
};

export function beallitasCim(kulcs: string): string {
  const rovid = kulcs.replace(/^beallitasok\./, '');
  if (rovid.startsWith('billentyuk.')) return t('Gyorsbillentyű: {parancs}', { parancs: rovid.slice('billentyuk.'.length) });
  return Object.hasOwn(BEALLITAS_CIM, rovid) ? t(BEALLITAS_CIM[rovid]) : rovid;
}

/** Egy beállítás értéke olvasható alakban (logikai: Be/Ki; ismert felsorolás: fordított név; egyéb: az érték). */
export function ertekSzoveg(ertek: unknown): string {
  if (typeof ertek === 'boolean') return ertek ? t('import.ertek.be') : t('import.ertek.ki');
  if (typeof ertek === 'string') return Object.hasOwn(ERTEK_CIM, ertek) ? t(ERTEK_CIM[ertek]) : ertek;
  if (ertek === null || ertek === undefined) return '–';
  if (typeof ertek === 'number') return String(ertek);
  return JSON.stringify(ertek);
}

export const FAJL_FAJTA: Record<string, string> = {
  md: tk('import.fajta.md'), canvas: tk('import.fajta.canvas'), base: tk('import.fajta.base'), csatolmany: tk('import.fajta.csatolmany'),
  obsidian: tk('import.fajta.obsidian'), egyeb: tk('import.fajta.egyeb'),
};

export const MUVELET: Record<string, string> = {
  masol: tk('import.muvelet.masol'), megvan: tk('import.muvelet.megvan'), utkozes: tk('import.muvelet.utkozes'),
};

/** A plugin állapota (az előnézet `mag_pluginok` / `kozossegi_pluginok` sorai). */
export const PLUGIN_ALLAPOT: Record<string, string> = {
  tamogatott: tk('import.plugin.tamogatott'), beepitett: tk('import.plugin.beepitett'), nem_tamogatott: tk('import.plugin.nem_tamogatott'),
};

export const MEGTARTVA_OKA: Record<string, string> = {
  modositott: tk('import.megtartva.modositott'),
  idegen: tk('import.megtartva.idegen'),
};

export const ALLAPOT_CIM: Record<ImportAllapotKod | 'megszakadt', string> = {
  fut: tk('import.allapot.fut'),
  megszakadt: tk('import.allapot.megszakadt'),
  hiba: tk('import.allapot.hiba'),
  megszakitva: tk('import.allapot.megszakitva'),
  kesz: tk('import.allapot.kesz'),
  visszaforditva: tk('import.allapot.visszaforditva'),
  reszben_visszaforditva: tk('import.allapot.reszben_visszaforditva'),
};

/** Egy napló-állapot megjelenített állapota: a `fut` állapot élő zár nélkül megszakadt futás (folytatható). */
export function allapotKulcs(a: Pick<ImportAllapot, 'allapot' | 'fut'>): ImportAllapotKod | 'megszakadt' {
  return a.allapot === 'fut' && a.fut === false ? 'megszakadt' : a.allapot;
}

export const FAJTA_CIM = { obsidian: tk('import.fajta_cim.obsidian'), v2: tk('import.fajta_cim.v2') } as const;

export const LEPES_CIM: Record<string, string> = {
  masolas: tk('import.lepes.masolas'),
  munkater: tk('import.lepes.munkater'),
  beallitasok: tk('import.lepes.beallitasok'),
};

/** A hibakódhoz tartozó teendő („Fix” sor a hibapanelben). */
const JAVITAS: Record<string, string> = {
  'import.terv_valtozott': tk('import.javitas.terv_valtozott'),
  'import.fut': tk('import.javitas.fut'),
  'import.nem_fut': tk('import.javitas.nem_fut'),
  'import.megszakitva': tk('import.javitas.megszakitva'),
  'import.utkozes': tk('import.javitas.utkozes'),
  'import.munkater_hasznalatban': tk('import.javitas.munkater_hasznalatban'),
  'import.visszafordit_utkozes': tk('import.javitas.visszafordit_utkozes'),
  'import.forras_valtozik': tk('import.javitas.forras_valtozik'),
  'import.masolas_hiba': tk('import.javitas.masolas_hiba'),
  'import.nincs': tk('import.javitas.nincs'),
  'import.tilos': tk('import.javitas.tilos'),
  'import.ervenytelen_keres': tk('import.javitas.ervenytelen_keres'),
  'import.beallitas_hibas': tk('import.javitas.beallitas_hibas'),
  'import.munkater_csere': tk('import.javitas.munkater_csere'),
  'import.fejleszto_mod': tk('import.javitas.fejleszto_mod'),
};
const JAVITAS_TARTALEK = tk('import.javitas.ismeretlen');
const KAPCSOLAT_JAVITAS = tk('import.javitas.kapcsolat');

export interface ImportHiba {
  /** Mi történt (ikonnal és szóval jelenik meg). */
  mi: string;
  /** Mit tegyen a felhasználó. */
  javitas: string;
  /** Részletező sorok (pl. az akadályok), mindegyik érthető mondat. */
  lista: string[];
  kod?: string;
}

/** A core `kod`-ja és `param`-ja (WS-esemény `hiba` mezője, napló-állapot `hiba`) → ImportHiba. */
export function hibaKodbol(kod: string | undefined, uzenet: string | undefined, param: Record<string, unknown> | undefined): ImportHiba {
  const k = kod ?? 'import.masolas_hiba';
  const lista = k === 'import.tilos' && typeof param?.akadaly === 'string'
    ? param.akadaly.split(',').map((x) => x.trim()).filter(Boolean).map((x) => kodSzoveg(AKADALY, x, AKADALY_TARTALEK))
    : [];
  const mi = k === 'import.tilos' ? t('import.hiba.tilos') : kodMondat(k, uzenet, param);
  return { mi, javitas: kodSzoveg(JAVITAS, k, JAVITAS_TARTALEK), lista, kod: k };
}

function kodMondat(kod: string, uzenet: string | undefined, param: Record<string, unknown> | undefined): string {
  const ps: Record<string, string | number | boolean> = {};
  for (const [a, v] of Object.entries(param ?? {})) if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') ps[a] = v;
  const fordito = hibaUzenet(new ApiHiba(0, uzenet ?? '', { kod, param: ps }));
  return fordito || uzenet || t('import.hiba.altalanos');
}

/** Egy kérés hibája (ApiHiba vagy bármi) a hibapanelhez. A kapcsolati hiba külön teendőt kap. */
export function importHiba(e: unknown): ImportHiba {
  if (e instanceof ApiHiba) {
    if (e.kod) {
      // az `e.message` már a fordított mondat (vagy a core angol tartaléka); a kód a teendőt adja
      return hibaKodbol(e.kod, e.message, e.adat.param as Record<string, unknown> | undefined);
    }
    return { mi: e.message, javitas: t(e.fajta ? KAPCSOLAT_JAVITAS : JAVITAS_TARTALEK), lista: [] };
  }
  return { mi: hibaUzenet(e), javitas: t(JAVITAS_TARTALEK), lista: [] };
}

/** Időpont a core napló-állapotából (`2026-10-16T10:00:00`), a helyi nyelven; érvénytelen értéknél a nyers szöveg. */
export function idoSzoveg(s: string | undefined | null): string {
  if (!s) return '–';
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString(locale());
}

/** Abszolút útvonal-e (a core a relatív utat a saját munkakönyvtárához oldaná: ezt a felület nem engedi). */
export function abszolutUt(ut: string): boolean {
  const s = ut.trim();
  return s.startsWith('/') || s === '~' || s.startsWith('~/');
}

/** A célmappa javaslata a forrásból: ugyanott, „<név> (Manifold)” néven. */
export function celJavaslat(forras: string): string {
  const s = forras.trim().replace(/\/+$/, '');
  return s && abszolutUt(s) && s !== '~' ? `${s} (Manifold)` : '';
}

/** Egész szám a helyi nyelv szerint (ezres tagolással). */
export function szam(n: number | null | undefined): string {
  return new Intl.NumberFormat(locale()).format(n ?? 0);
}
