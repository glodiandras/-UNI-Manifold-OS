// A címkefa adata (C11b): `/api/vault/cimkek` — minden címke és minden szülője a `/` mentén, számlálóval. A felület
// a fát ebből építi (`cimkeFa`); a szűrt lista a keresés `tag:` operátorából jön (a gyerekeket is hozza).

import { locale } from '../i18n';

import { ApiHiba, kerdez } from '../core/api';
import type { CoreKapcsolat } from '../core/ws.svelte';
import { modulEngedelyezett } from '../beallitasok/allapot.svelte';
import type { ListaRendezes } from '../elrendezes/felulet.svelte';

export interface CimkeCsucs {
  /** a megjelenített teljes út (a leggyakoribb írásmód): `Fizika/Mechanika` */
  cimke: string;
  /** a kisbetűs út (a kulcs) */
  kis: string;
  /** a pontosan ezt a címkét viselő jegyzetek száma */
  db: number;
  /** ezé és a gyerekeié (egy jegyzet egyszer) */
  ossz: number;
}

export interface CimkeFaElem extends CimkeCsucs {
  /** a megjelenített név: az utolsó szegmens */
  nev: string;
  melyseg: number;
  van_gyerek: boolean;
}

/** A lapos listából a fa sorai megjelenítési sorrendben (a szülők előtt a gyerekeik), a `nyitott` kulcsokig lenyitva.
 *  `rendezes` (03-properties-11): a testvérek sorrendje név (A–Z / Z–A) vagy darabszám (csökkenő / növekvő) szerint; a szülő mindig
 *  a gyerekei előtt áll, az egyenlő darabszám név szerint dönt. */
export function cimkeFa(lista: CimkeCsucs[], nyitott: ReadonlySet<string>, rendezes: ListaRendezes = 'nev'): CimkeFaElem[] {
  const nevCmp = (a: CimkeCsucs, b: CimkeCsucs) => a.kis.localeCompare(b.kis, locale(), { numeric: true });
  const cmp =
    rendezes === 'nev-forditott' ? (a: CimkeCsucs, b: CimkeCsucs) => nevCmp(b, a)
    : rendezes === 'db' ? (a: CimkeCsucs, b: CimkeCsucs) => b.ossz - a.ossz || nevCmp(a, b)
    : rendezes === 'db-forditott' ? (a: CimkeCsucs, b: CimkeCsucs) => a.ossz - b.ossz || nevCmp(a, b)
    : nevCmp;
  const kulcsok = new Set(lista.map((c) => c.kis));
  const gyerekek = new Map<string, CimkeCsucs[]>();
  for (const c of lista) {
    const i = c.kis.lastIndexOf('/');
    const szulo = i > 0 ? c.kis.slice(0, i) : '';
    // gyökér: nincs `/`; olyan, amelynek a szülője hiányzik a listából, sosem látszik (mint eddig)
    if (i > 0 && !kulcsok.has(szulo)) continue;
    let l = gyerekek.get(szulo);
    if (!l) gyerekek.set(szulo, (l = []));
    l.push(c);
  }
  const ki: CimkeFaElem[] = [];
  const bejar = (szulo: string, melyseg: number) => {
    for (const c of (gyerekek.get(szulo) ?? []).sort(cmp)) {
      const van = (gyerekek.get(c.kis)?.length ?? 0) > 0;
      ki.push({ ...c, nev: c.cimke.slice(c.cimke.lastIndexOf('/') + 1), melyseg, van_gyerek: van });
      if (van && nyitott.has(c.kis)) bejar(c.kis, melyseg + 1);
    }
  };
  bejar('', 0);
  return ki;
}

export class VaultCimkek {
  lista = $state.raw<CimkeCsucs[]>([]);
  betoltve = $state(false);
  hiba = $state<string | null>(null);
  /** a címkefa látszik-e (a Címkék fül nyitva): csak ekkor töltődik újra a vault változására, különben csak jelöli */
  latszik = false;
  private elavult = true;
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private sorszam = 0;
  private igenylok = 0;
  private folyamat: Promise<void> | null = null;
  private elavultVerzio = 0;

  private get aktiv(): boolean { return this.latszik || this.igenylok > 0; }

  /** Szerkesztő/egyéb fogyasztó életidejére igényelt közös cache; a visszaadott feloldás idempotens. */
  igenyel(): () => void {
    this.igenylok++;
    void this.kerjen();
    let el = true;
    return () => {
      if (!el) return;
      el = false;
      this.igenylok--;
      if (!this.aktiv && this.idozito) { clearTimeout(this.idozito); this.idozito = null; }
    };
  }

  /** A kiegészítés csak szükség esetén vár: betöltött, érvényes listán nincs új API-kérés. */
  async kerjen(): Promise<void> {
    if (!modulEngedelyezett('cimkek')) return;
    if (this.folyamat) return this.folyamat;
    if (this.elavult || !this.betoltve) return this.frissit();
  }

  /** A Címkék fül megjelent: ha a lista elavult vagy még nincs, töltődik. */
  megjelenik(): void {
    this.latszik = true;
    void this.kerjen();
  }

  frissit(): Promise<void> {
    if (!modulEngedelyezett('cimkek')) return Promise.resolve();
    if (this.folyamat) return this.folyamat;
    const en = ++this.sorszam;
    const verzio = this.elavultVerzio;
    this.folyamat = (async () => {
      try {
        const d = await kerdez<{ cimkek: CimkeCsucs[] }>('/api/vault/cimkek', { idokorlat: 8000 });
        if (en !== this.sorszam) return;
        this.lista = d.cimkek ?? [];
        this.betoltve = true;
        this.elavult = verzio !== this.elavultVerzio;
        this.hiba = null;
      } catch (e) {
        if (en !== this.sorszam || e instanceof ApiHiba && e.statusz === 503) return; // az index esemény hoz újra
        this.hiba = e instanceof Error ? e.message : String(e);
      } finally {
        if (en === this.sorszam) {
          this.folyamat = null;
          // A kérés alatt érkezett esemény nem veszhet el az együtt kezelt kérések miatt.
          if (verzio !== this.elavultVerzio && this.aktiv) this.utemez(0);
        }
      }
    })();
    return this.folyamat;
  }

  private utemez(ms = 800) {
    this.elavult = true;
    this.elavultVerzio++;
    if (!this.aktiv || !modulEngedelyezett('cimkek')) return;
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = setTimeout(() => {
      this.idozito = null;
      if (this.aktiv && modulEngedelyezett('cimkek')) void this.frissit();
    }, ms);
  }

  figyel(k: CoreKapcsolat): () => void {
    const le1 = k.figyel('vault_valtozas', () => this.utemez());
    const le2 = k.figyel('index', () => this.utemez(0));
    const le3 = k.figyel('hello', () => this.utemez(0));
    return () => {
      le1();
      le2();
      le3();
      if (this.idozito) clearTimeout(this.idozito);
      this.idozito = null;
      this.sorszam++;
      this.folyamat = null;
      this.elavult = true;
    };
  }
}

export const cimkek = new VaultCimkek();
