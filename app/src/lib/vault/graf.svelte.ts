// A gráf adata a core indexéből (C13): `/api/vault/graf` (csúcsok és élek = a core gráfja), `/api/vault/graf-meta`
// (címke, tulajdonság) és `/api/vault/graf-beallitasok` (az Obsidian graph.json-ja, csak olvasható). A fájltípus a
// fájllistából jön. WS-eseményre (`vault_valtozas`, `index`, `hello`) csak akkor töltődik újra, ha gráfnézet látszik;
// különben csak elavultnak jelöli magát, és a nézet megjelenésekor tölt (a címkefa mintája). Ha a szerkezet (csúcsok és
// élek) nem változott, az eredmény ugyanaz marad: a fizika nem indul újra, a nézet nem számol.
//
// C33 (T070): a gráf és a graf-meta feltételes kéréssel tölt (ETag/304): a core a szerkezeti generáció szerint tárolja őket,
// így a tartalmi mentés után 304 jön, és a `GrafAdat` nem épül újra a fő szálon. A vault változására induló töltés a közös
// frissítő-soron megy (`frissitoSor`), nem párhuzamosan a többi panellel.

import { ApiHiba, kerdez, kerdezEtag } from '../core/api';
import { frissitoSor } from '../core/frissitoSor';
import type { CoreKapcsolat } from '../core/ws.svelte';
import type { GrafJson } from '../graf/beallitasok';
import { fnv, GrafAdat, type FajlTipus, type GrafMeta, type GrafValasz } from '../graf/modell';

export type TipusFn = (ut: string) => FajlTipus | undefined;

export class VaultGraf {
  adat = $state.raw<GrafAdat | null>(null);
  json = $state.raw<GrafJson | null>(null);
  betoltve = $state(false);
  hiba = $state<string | null>(null);

  private latszok = 0;
  private elavult = true;
  private jsonElavult = true;
  private tipusFn: TipusFn = () => undefined;
  private valasz: GrafValasz | null = null;
  private meta: GrafMeta | null = null;
  private attr = '';
  private sorszam = 0;
  private etagGraf: string | null = null;
  private etagMeta: string | null = null;
  /** Hányszor épült a `GrafAdat` (a teszt és a mérés olvassa). */
  epitesek = 0;

  /** Egy gráfnézet megjelent (vagy látszik): ha az adat elavult vagy még nincs, tölt. A visszaadott függvény jelzi az eltűnését. */
  megjelenik(tipusFn: TipusFn): () => void {
    this.tipusFn = tipusFn;
    this.latszok++;
    if (this.elavult || !this.betoltve || this.jsonElavult) void this.frissit();
    let kesz = false;
    return () => {
      if (kesz) return;
      kesz = true;
      this.latszok = Math.max(0, this.latszok - 1);
      if (!this.latszok) frissitoSor.elvet('graf');
    };
  }

  /** Töltés; `json`: a graph.json is újra (a nézet megnyitásakor és újracsatlakozás után). */
  async frissit(): Promise<void> {
    const en = ++this.sorszam;
    const jsonKell = this.jsonElavult;
    try {
      // a már betöltött adatnál feltételes kérés: változatlan szerkezetre 304, a régi adat marad (T070)
      const vanAdat = this.valasz !== null;
      const [valasz, meta, json] = await Promise.all([
        kerdezEtag<GrafValasz>('/api/vault/graf', vanAdat ? this.etagGraf : null, { idokorlat: 15000 }),
        kerdezEtag<GrafMeta>('/api/vault/graf-meta', vanAdat ? this.etagMeta : null, { idokorlat: 15000 }),
        jsonKell ? kerdez<GrafJson>('/api/vault/graf-beallitasok', { idokorlat: 5000 }) : Promise.resolve(null),
      ]);
      if (en !== this.sorszam) return;
      if (json) {
        this.json = json;
        this.jsonElavult = false;
      }
      const valtozott = valasz.adat !== null || meta.adat !== null || json !== null;
      if (valasz.adat !== null) this.valasz = valasz.adat;
      if (meta.adat !== null) this.meta = meta.adat;
      this.etagGraf = valasz.etag;
      this.etagMeta = meta.etag;
      if (valtozott) this.epit();
      this.betoltve = true;
      this.elavult = false;
      this.hiba = null;
    } catch (e) {
      if (e instanceof ApiHiba && e.statusz === 503) return; // az index még épül: az `index` esemény hoz újra
      this.hiba = e instanceof Error ? e.message : String(e);
    }
  }

  /** A fájllista (típusok) frissült: ha a típusok változtak, az adat újraépül (a szerkezet nem). */
  tipusokFrissit(): void {
    if (this.valasz) this.epit();
  }

  /** A graph.json újraolvasása a következő töltéskor. */
  jsonAvult(): void {
    this.jsonElavult = true;
  }

  private epit(): void {
    if (!this.valasz) return;
    this.epitesek++;
    const uj = new GrafAdat(this.valasz, this.tipusFn, this.meta);
    const attr = `${fnv(JSON.stringify(this.meta ?? {}), 0x811c9dc5).toString(16)}|${fnv(uj.tipus.join(','), 0x811c9dc5).toString(16)}|${fnv(Array.from(uj.irany).join(''), 0x811c9dc5).toString(16)}`;
    // ugyanaz a szerkezet és ugyanazok az attribútumok: a régi marad (nincs újrarajzolás, nincs fizika)
    if (this.adat && this.adat.alairas === uj.alairas && this.attr === attr) return;
    this.attr = attr;
    this.adat = uj;
  }

  private utemez(ms: number): void {
    this.elavult = true;
    if (!this.latszok) return;
    frissitoSor.ker('graf', () => this.frissit(), ms);
  }

  figyel(k: CoreKapcsolat): () => void {
    // a szerkesztés (mentés) linket változtathat, ezért minden vault-változás után újratöltünk, de csak látszó nézetnek,
    // összevonva; az aláírás miatt változatlan szerkezetnél semmi nem számol
    const le1 = k.figyel('vault_valtozas', () => this.utemez(1200));
    const le2 = k.figyel('index', () => this.utemez(300));
    const le3 = k.figyel('hello', () => {
      this.jsonElavult = true;
      this.utemez(300);
    });
    return () => {
      le1();
      le2();
      le3();
      frissitoSor.elvet('graf');
    };
  }
}

export const grafAdat = new VaultGraf();
