// A kód-munkafelület nyelvei és eszközláncai a felületen (F10): melyik core-szolgáltatás futtat egy forrást, és mi a nyelvenkénti
// eszközlánc-állapot (`GET /api/kod/nyelvek`: elérhető / hiányzik + a core érthető teendője a `kod.*` hibakódból).
//
// Két motor van, és a `.cpp` megmarad a régin: a C36a `/api/cpp/*` (a `.cpp` forrás és az ilyet beágyazó jegyzet: `cpp_futas` /
// `cpp_ai` WS-esemény, tracker-jelzés, kalibrált AI) változatlanul él; minden más nyelv (és a `.cc`, `.cxx`, `.c`) az általános
// `/api/kod/*`-on megy (`kod_futas` / `kod_ai`). A felület mindkettőt ugyanazzal az állapotmodellel kezeli (`futas.svelte.ts`).

import { kerdez, kodUzenet } from '../lib/core/api';
import { t } from '../lib/i18n';
import { elsoBeagyazottKod, nyelvAzonosito, nyelvUt, type KodNyelv } from '../lib/vault/kodFajl';

export { BEAGYAZOTT_KOD, KOD_NYELVEK, KOD_UT, nyelvAzonosito, nyelvKeritesbol, nyelvUt, type KodNyelv } from '../lib/vault/kodFajl';

/** `cpp`: a C36a szolgáltatás (`/api/cpp`); `kod`: az általános (`/api/kod`). */
export type Motor = 'cpp' | 'kod';

/** A C36a szolgáltatás forrása: a `.cpp` (a `.cc` / `.cxx` / `.c` már az általános motoron fut). */
export const REGI_CPP = /\.cpp$/i;

/** A forrás motorja; ismeretlen (nincs forrás): a régi, változatlan viselkedés (`cpp`). */
export function motorForras(forras: string | null | undefined): Motor {
  return !forras || REGI_CPP.test(forras) ? 'cpp' : 'kod';
}

/** Az út motorja: a `.md` (a jegyzetből indított futás, a forrás még nem ismert) és a `.cpp` a régi, minden más forrás az általános. */
export function motorUt(ut: string): Motor {
  return /\.md$/i.test(ut) ? 'cpp' : motorForras(ut);
}

/** A jegyzet nyelve és motorja: az első beágyazott forrás szerint (a core is az elsőt választja). */
export function jegyzetNyelve(szoveg: string): { forras: string; nyelv: KodNyelv | null; motor: Motor } | null {
  const forras = elsoBeagyazottKod(szoveg);
  return forras ? { forras, nyelv: nyelvUt(forras), motor: motorForras(forras) } : null;
}

/** A core `kod.`-előtagú hibakódja a felület rövid kódjára (`kod.nincs_eszkozlanc` → `nincs_eszkozlanc`); a régi kódok változatlanok. */
export function rovidKod(kod: unknown): string | null {
  return typeof kod === 'string' && kod !== '' ? kod.replace(/^kod\./, '') : null;
}

// --- eszközlánc-állapot -------------------------------------------------------------------------------------------------------

export interface EszkozInfo {
  nev: string;
  ok: boolean;
  ut?: string | null;
  forras?: string | null;
  verzio?: string | null;
}

export interface NyelvHiba {
  kod: string;
  param?: Record<string, unknown>;
  uzenet: string;
}

/** Egy nyelv a `GET /api/kod/nyelvek` válaszából (a profil + az eszközlánc felderített állapota). */
export interface NyelvAllapot {
  azonosito: string;
  nev: string;
  kiterjesztesek: string[];
  motor: 'cpp' | 'nyelv';
  nativ: boolean;
  eszkozlanc: 'beagyazott' | 'rendszer';
  kalibracios_kulcs: string;
  ai_modok: string[];
  modok: string[];
  telepites_tipp: string;
  elerheto: boolean;
  eszkozok: EszkozInfo[];
  hiba: NyelvHiba | null;
}

export class KodNyelvek {
  /** a core eszközlánc-listája; `null`, amíg nem érkezett meg */
  lista = $state.raw<NyelvAllapot[] | null>(null);
  folyamatban = $state(false);
  /** nyitva van-e az összes nyelv eszközlánc-listája (a kód-fül jelvényére kattintva) */
  panelNyitva = $state(false);
  /** a lekérdezés hibája (a core nem válaszol, a motor nem indul) */
  hiba = $state.raw<string | null>(null);
  private igeret: Promise<void> | null = null;
  /** volt-e már lekérdezés: a hibás válasz után a kód-fül nem próbálkozik magától újra (az „Újraellenőrzés” gomb igen) */
  private probalt = false;

  /** A lista betöltése (egyszerre egy kérés); `frissit`: a core gyorsítótárát megkerülő új felderítés. */
  betolt(frissit = false): Promise<void> {
    if (this.igeret) return this.igeret;
    this.folyamatban = true;
    this.probalt = true;
    this.hiba = null;
    // a felderítés a fordító-homokozóban futtatja a verzió-próbát: az első hívás másodpercekig tarthat
    this.igeret = kerdez<{ nyelvek: NyelvAllapot[] }>(`/api/kod/nyelvek${frissit ? '?frissit=1' : ''}`, { idokorlat: 130_000 })
      .then((d) => {
        this.lista = Array.isArray(d.nyelvek) ? d.nyelvek : [];
      })
      .catch((e: unknown) => {
        this.hiba = e instanceof Error ? e.message : String(e);
      })
      .finally(() => {
        this.folyamatban = false;
        this.igeret = null;
      });
    return this.igeret;
  }

  /** Csak az első kód-fül megnyitásakor kér (egyszer): ha a válasz hibás, nem kér újra magától. */
  kellLista(): void {
    if (!this.probalt) void this.betolt();
  }

  /** Az állapot törlése (a tesztek között; a kód-fül következő megnyitása újra lekérdez). */
  visszaallit(): void {
    this.lista = null;
    this.hiba = null;
    this.folyamatban = false;
    this.panelNyitva = false;
    this.probalt = false;
    this.igeret = null;
  }

  kap(azonosito: string | null | undefined): NyelvAllapot | null {
    return this.lista?.find((n) => n.azonosito === azonosito) ?? null;
  }

  /** Igaz / hamis a felderítés szerint; `null`: még nem ismert. */
  elerheto(azonosito: string | null | undefined): boolean | null {
    const n = this.kap(azonosito);
    return n ? n.elerheto : null;
  }

  /** A hiányzó eszközlánc érthető teendője (a core `kod.*` hibakódjának szövege, majd a telepítési tipp); elérhetőnél `null`. */
  teendo(azonosito: string | null | undefined): string | null {
    const n = this.kap(azonosito);
    if (!n || n.elerheto) return null;
    const szoveg = n.hiba ? kodUzenet({ hiba: n.hiba.uzenet, kod: n.hiba.kod, param: n.hiba.param }, '') : '';
    return szoveg || n.telepites_tipp || t('Az eszközlánc nem található.');
  }

  /** A hiányzó eszközök nevei (a sorban a „mi hiányzik”). */
  hianyzo(azonosito: string | null | undefined): string[] {
    return this.kap(azonosito)?.eszkozok.filter((e) => !e.ok).map((e) => e.nev) ?? [];
  }
}

export const kodNyelvek = new KodNyelvek();

/** Egy nyelv megjelenő neve az azonosítóból (ismeretlen: maga az azonosító). */
export function nyelvNev(azonosito: string | null | undefined): string {
  return nyelvAzonosito(azonosito)?.nev ?? azonosito ?? '';
}
