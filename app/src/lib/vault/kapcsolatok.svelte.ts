// Az aktív jegyzet kapcsolatai a jobb panelnek (C10): visszahivatkozások (a sor szövegével), linkeletlen
// említések és a kimenő linkek a core indexéből. A feloldás a core-é (L42); itt csak lekérés és frissítés van:
// az aktív fül váltására és a `vault_valtozas` / `index` eseményre (300 ms-os összevonással) újratölt.

import { ApiHiba, kerdez } from '../core/api';
import { frissitoSor } from '../core/frissitoSor';
import type { CoreKapcsolat } from '../core/ws.svelte';

export interface VisszaLink {
  fajta: string;
  sor: number | null;
  oszlop: number | null;
  hossz: number | null;
  alcel: string | null;
  alias: string | null;
  beagyazas: boolean;
  /** a frontmatter kulcsa, ha a link ott áll (pl. `Source`) */
  tulajdonsag: string | null;
  csomopont: string | null;
  /** a link sora (legfeljebb 400 karakter) */
  kornyezet: string | null;
}

export interface VisszaForras {
  ut: string;
  linkek: VisszaLink[];
}

export interface Emlites {
  sor: number;
  oszlop: number;
  hossz: number;
  /** az egész sor szövege (legfeljebb 400 karakter) */
  szoveg: string;
}

export interface EmlitesForras {
  ut: string;
  talalatok: Emlites[];
}

export interface KimenoLink {
  fajta: string;
  cel_nyers: string;
  cel: string | null;
  alcel: string | null;
  alias: string | null;
  beagyazas: boolean;
  tulajdonsag: string | null;
  sor: number | null;
}

const q = encodeURIComponent;
const TOMB: never[] = [];

export class Kapcsolatok {
  ut = $state<string | null>(null);
  visszahivatkozasok = $state.raw<VisszaForras[]>(TOMB);
  emlitesek = $state.raw<EmlitesForras[]>(TOMB);
  kimeno = $state.raw<KimenoLink[]>(TOMB);
  betolt = $state(false);
  hiba = $state<string | null>(null);
  private sorszam = 0;
  private readonly kulcs = `kapcsolatok-${Math.random().toString(36).slice(2, 10)}`;

  /** Az `ut` jegyzet kapcsolatainak (újra)töltése; `null`: nincs megnyitott fájl. */
  async frissit(ut: string | null): Promise<void> {
    const en = ++this.sorszam;
    this.ut = ut;
    if (!ut) {
      this.visszahivatkozasok = this.emlitesek = TOMB;
      this.kimeno = TOMB;
      this.betolt = false;
      this.hiba = null;
      return;
    }
    this.betolt = true;
    const md = ut.toLowerCase().endsWith('.md');
    const szolgal = (p: string) => kerdez<Record<string, unknown>>(p, { idokorlat: 8000 });
    try {
      const [vissza, emlit, jegyzet] = await Promise.all([
        szolgal(`/api/vault/visszahivatkozasok?ut=${q(ut)}`),
        md ? szolgal(`/api/vault/emlitesek?ut=${q(ut)}&limit=100`) : Promise.resolve({ forrasok: [] }),
        md || ut.toLowerCase().endsWith('.canvas') ? szolgal(`/api/vault/jegyzet?ut=${q(ut)}`) : Promise.resolve({ linkek: [] }),
      ]);
      if (en !== this.sorszam) return; // közben másik jegyzet lett az aktív
      this.visszahivatkozasok = (vissza.forrasok as VisszaForras[]) ?? TOMB;
      this.emlitesek = (emlit.forrasok as EmlitesForras[]) ?? TOMB;
      this.kimeno = ((jegyzet.linkek as KimenoLink[]) ?? TOMB).filter((l) => l.fajta !== 'md' || l.cel_nyers);
      this.hiba = null;
    } catch (e) {
      if (en !== this.sorszam) return;
      this.visszahivatkozasok = this.emlitesek = TOMB;
      this.kimeno = TOMB;
      // a fájl még nincs az indexben (új), vagy az index épül: nem hiba, a következő esemény újratölt
      this.hiba = e instanceof ApiHiba && (e.statusz === 404 || e.statusz === 503) ? null : e instanceof Error ? e.message : String(e);
    } finally {
      if (en === this.sorszam) this.betolt = false;
    }
  }

  /** WS-figyelés: a vault változására az aktív jegyzet kapcsolatai újratöltődnek. `aktivUt`: az aktív fül útja;
   *  `undefined`: most nem kell tölteni (a rejtett panel a régi listát megtartja, C38). */
  figyel(k: CoreKapcsolat, aktivUt: () => string | null | undefined): () => void {
    // C33 (T070): a vault változására a frissítés a közös frissítő-soron megy (a gráf és a Bases kéréseivel nem párhuzamosan)
    const utemez = () =>
      frissitoSor.ker(
        this.kulcs,
        () => {
          const ut = aktivUt();
          return ut !== undefined ? this.frissit(ut) : undefined;
        },
        300,
      );
    const le1 = k.figyel('vault_valtozas', utemez);
    const le2 = k.figyel('index', utemez);
    return () => {
      le1();
      le2();
      frissitoSor.elvet(this.kulcs);
    };
  }
}

/** A link megjelenített helye: a link szövege a sorban (kódpont-oszlopokkal), a környezeti sorból kivágva. */
export function kornyezetReszek(sor: string, oszlop: number | null, hossz: number | null): { elotte: string; link: string; utana: string } {
  const cp = Array.from(sor);
  if (oszlop === null || hossz === null || oszlop > cp.length) return { elotte: sor, link: '', utana: '' };
  return { elotte: cp.slice(0, oszlop).join(''), link: cp.slice(oszlop, oszlop + hossz).join(''), utana: cp.slice(oszlop + hossz).join('') };
}
