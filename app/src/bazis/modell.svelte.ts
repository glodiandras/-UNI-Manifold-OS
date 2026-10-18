// A Bases-nézet modellje (C12): a core-lekérdezés eredménye, sorszámozott kérésekkel (az elavult válasz eldobódik),
// frissítés a `.base` szövegének, a `vault_valtozas` eseménynek (300 ms késleltetéssel) és az `index` kész-jelnek a
// változására. Az írás (`modosit`) a forráson át megy; a core csak az új szöveget számolja.

import { ApiHiba } from '../lib/core/api';
import { frissitoSor } from '../lib/core/frissitoSor';
import type { CoreKapcsolat } from '../lib/core/ws.svelte';
import { bazisApi, type BazisApi } from './api';
import type { BazisForras } from './forras';
import type { ModositValasz, Muvelet, Valasz } from './tipusok';
import { t } from '../lib/i18n';

export const FRISSITES_KESLELTETES = 300;

export interface ModellOpciok {
  api?: BazisApi;
  kapcsolat?: CoreKapcsolat | null;
  /** a kezdő nézet (sorszám vagy név) */
  nezet?: number | string | null;
  maxSor?: number;
}

export class BazisModell {
  valasz = $state.raw<Valasz | null>(null);
  hiba = $state<string | null>(null);
  /** az első válasz még nem jött meg */
  tolt = $state(true);
  nezet = $state<number | string | null>(null);
  /** a teljes YAML-forrás szerkesztője nyitva van (a nézet helyén) */
  forrasMod = $state(false);
  /** az utolsó írás hibája (a művelet nem alkalmazható / nem írható) */
  irasHiba = $state<string | null>(null);
  /** az utolsó válasz megérkezésének ideje (`performance.now()`): a rajzolás idejének mérése */
  megerkezett = 0;
  private readonly api: BazisApi;
  private readonly maxSor?: number;
  private sorszam = 0;
  /** a modell azonosítója a core-nak: az azonos nézetre küldött újabb kérés leállítja a régebbit (T040) */
  private readonly azon = `bm-${Math.random().toString(36).slice(2, 12)}`;
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private lekotesek: Array<() => void> = [];
  /** az írások sorban futnak: két gyors művelet (pl. oszlopméret és rendezés) nem írja felül egymást */
  private irasSor: Promise<unknown> = Promise.resolve();

  constructor(
    readonly forras: BazisForras,
    private readonly opciok: ModellOpciok = {},
  ) {
    this.api = opciok.api ?? bazisApi();
    this.maxSor = opciok.maxSor;
    this.nezet = opciok.nezet ?? null;
  }

  /** Feliratkozások és az első lekérdezés. */
  indit(): void {
    this.lekotesek.push(this.forras.figyel(() => this.utemez(0)));
    const k = this.opciok.kapcsolat;
    if (k) {
      // C33 (T070): a vault változására a közös frissítő-soron (a gráf és a kapcsolatok kéréseivel nem párhuzamosan)
      this.lekotesek.push(k.figyel('vault_valtozas', () => frissitoSor.ker(this.azon, () => this.frissit(), FRISSITES_KESLELTETES)));
      this.lekotesek.push(k.figyel('index', () => this.utemez(0)));
    }
    this.utemez(0);
  }

  lebont(): void {
    for (const f of this.lekotesek) f();
    this.lekotesek = [];
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = null;
    frissitoSor.elvet(this.azon);
    this.sorszam++; // az úton lévő válasz eldobódik
  }

  utemez(ms = FRISSITES_KESLELTETES): void {
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = setTimeout(() => {
      this.idozito = null;
      void this.frissit();
    }, ms);
  }

  async frissit(): Promise<void> {
    const n = ++this.sorszam;
    try {
      const v = await this.api.lekerdez(this.forras.szoveg(), {
        ez: this.forras.ez,
        nezet: this.nezet,
        ...(this.maxSor ? { max_sor: this.maxSor } : {}),
        kerdes: n,
        azon: this.azon,
      });
      if (n !== this.sorszam) return;
      this.valasz = v;
      this.hiba = null;
      this.megerkezett = performance.now();
    } catch (e) {
      if (n !== this.sorszam) return;
      this.hiba = e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e);
    } finally {
      if (n === this.sorszam) this.tolt = false;
    }
  }

  nezetValt(n: number | string): void {
    if (this.nezet === n) return;
    this.nezet = n;
    this.utemez(0);
  }

  /** Egy módosítás próbája: a core csak számol (élő ellenőrzés), nem ír és nem változtat semmit. */
  modosit(muvelet: Muvelet): Promise<ModositValasz> {
    return this.api.modosit(this.forras.szoveg(), muvelet);
  }

  /** Egy módosítás alkalmazása: a core új szöveget számol, a forrás beírja (az egyetlen írási úton). A hibás
   *  művelet nem ír semmit; az eredmény a core válasza (a `hibak` a mező alatt jelenik meg). Az írások sorban
   *  futnak, mindegyik a legutóbbi szövegből számol. */
  alkalmaz(muvelet: Muvelet, ujNezet?: number): Promise<ModositValasz & { irva: boolean }> {
    const p = this.irasSor.then(() => this.alkalmazMost(muvelet, ujNezet));
    this.irasSor = p.catch(() => undefined);
    return p;
  }

  private async alkalmazMost(muvelet: Muvelet, ujNezet?: number): Promise<ModositValasz & { irva: boolean }> {
    const alap = this.forras.szoveg();
    const tiltas = this.forras.csakOlvashato();
    if (tiltas) {
      this.irasHiba = tiltas;
      return { ok: false, szoveg_uj: this.forras.szoveg(), valtozas: '', hibak: [{ hely: 'iras', uzenet: tiltas }], irva: false };
    }
    try {
      const r = await this.api.modosit(alap, muvelet);
      // A számoló csak az elküldött szövegből dolgozik. Egy másik szerkesztő vagy külső frissítés közben új alapot adhat:
      // az aktuális Dokumentum hash-e azt már nem védené a régi eredményünktől. A no-op ág előtt is ellenőrzünk.
      const mostani = this.forras.szoveg();
      const mostaniTiltas = this.forras.csakOlvashato();
      if (mostaniTiltas || mostani !== alap) {
        const uzenet = mostaniTiltas ?? t('A szöveg közben változott; próbáld újra.');
        this.irasHiba = uzenet;
        return { ok: false, szoveg_uj: mostani, valtozas: '', hibak: [{ hely: 'iras', uzenet }], irva: false };
      }
      if (!r.ok) {
        this.irasHiba = r.hibak[0]?.uzenet ?? t('A módosítás nem alkalmazható.');
        return { ...r, irva: false };
      }
      const irva = r.szoveg_uj === alap || await this.forras.ir(r.szoveg_uj);
      // Sikertelen mentésnél marad az előző nézet. A forrás mentése előtt is jelezhet változást, ezért siker után az új nézetet külön lekérjük.
      if (irva && ujNezet !== undefined) this.nezetValt(ujNezet);
      this.irasHiba = irva ? null : t('A módosítás nem íródott be.');
      return { ...r, irva };
    } catch (e) {
      const uzenet = e instanceof Error ? e.message : String(e);
      this.irasHiba = uzenet;
      return { ok: false, szoveg_uj: this.forras.szoveg(), valtozas: '', hibak: [{ hely: 'iras', uzenet }], irva: false };
    }
  }
}
