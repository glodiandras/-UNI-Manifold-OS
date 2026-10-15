// A beágyazott kvíz kitöltésének állapotgépe (C22a): betöltés → kezdőlap → kérdésenként válasz, ellenőrzés, visszajelzés →
// a végén a core értékelése és elemzése. A pontszámot a core számolja; a felület csak mutat, és a kulcs a válasz előtt
// nincs a kliensben (a megoldás kérdésenként, az ellenőrzés után jön).
//
// A kitöltés **tokenje** (A3-03) a betöltéskor jön, és a kiértékelés válaszában újul meg: a core a válaszokat ebben rögzíti
// (`megoldas`), és a pontszámot a rögzített válaszokból számolja — a kliens által küldött lista nem számít.
//
// A tipp jelzése a válasz *előtt* dől el („Ellenőrzés — biztos vagyok” / „Csak tippeltem” / „Nem tudom”): ebből jön az elemzés
// négy kategóriája (tudod · szerencsés tipp · tévképzet · hiány). A kitöltés egyszeri `kulcsot` kap: a hálózati hiba utáni
// újrapróba ugyanazzal a kulccsal megy, a core nem hoz létre második kitöltést.

import { kvizApi, type KvizApi } from './api';
import type { Ertekeles, KitoltesValaszEgy, KvizKerdes, KvizMod, KvizValasz, Megoldas } from './tipusok';

export type Fazis = 'betolt' | 'hiba' | 'kezdo' | 'kerdes' | 'visszajelzes' | 'elemzes';

/** A kitöltésben szereplő kérdés: a tárolt sorrend indexei a megjelenítés sorrendjében (kitöltésenként új keverés). */
export interface KerdesNezet {
  kerdes: KvizKerdes;
  sorrend: number[];
}

export interface KvizFuggosegek {
  api?: KvizApi;
  /** a `kviz_eredmeny` tracker-esemény továbbítása (`ut` = a forrásjegyzet, `adat` a core kész adata) */
  tracker?: (ut: string, adat: Record<string, unknown>) => void;
  veletlen?: () => number;
  most?: () => number;
  kulcs?: () => string;
}

/** Fisher–Yates keverés a megadott véletlenből: a `0..n-1` permutációja. */
export function keveres(n: number, veletlen: () => number): number[] {
  const p = Array.from({ length: n }, (_, i) => i);
  for (let i = n - 1; i > 0; i--) {
    const j = Math.floor(veletlen() * (i + 1));
    [p[i], p[j]] = [p[j], p[i]];
  }
  return p;
}

function alapKulcs(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  } catch {
    /* nem biztonságos környezet: tartalék */
  }
  return `k${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
}

function uzenet(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export class KvizMenet {
  fazis = $state<Fazis>('betolt');
  hiba = $state<string | null>(null);
  adat = $state<KvizValasz | null>(null);
  mod = $state<KvizMod>('teljes');
  lista = $state<KerdesNezet[]>([]);
  i = $state(0);
  /** a kiválasztott válasz a TÁROLT sorrend indexében; `null`: még nincs választás */
  valasztott = $state<number | null>(null);
  megoldas = $state<Megoldas | null>(null);
  ertekeles = $state<Ertekeles | null>(null);
  kuld = $state(false);
  valaszok = $state<KitoltesValaszEgy[]>([]);

  private readonly api: KvizApi;
  private readonly tracker: (ut: string, adat: Record<string, unknown>) => void;
  private readonly veletlen: () => number;
  private readonly most: () => number;
  private readonly kulcsGen: () => string;
  private kulcs: string | null = null;
  private token: string | null = null;
  private tKezd = 0;
  private tKerdes = 0;

  constructor(
    readonly ut: string,
    f: KvizFuggosegek = {},
  ) {
    this.api = f.api ?? kvizApi;
    this.tracker = f.tracker ?? (() => {});
    this.veletlen = f.veletlen ?? Math.random;
    this.most = f.most ?? Date.now;
    this.kulcsGen = f.kulcs ?? alapKulcs;
  }

  get aktualis(): KerdesNezet | null {
    return this.lista[this.i] ?? null;
  }

  async betolt(): Promise<void> {
    this.fazis = 'betolt';
    this.hiba = null;
    try {
      this.adat = await this.api.kviz(this.ut);
      this.token = this.adat.token;
      this.fazis = 'kezdo';
    } catch (e) {
      this.hiba = uzenet(e);
      this.fazis = 'hiba';
    }
  }

  /** Új kitöltés. `hibasak`: az előző kitöltés hibás és tippelt kérdései (az utolsó értékelésből, különben a betöltött
   *  előzményből); ha nincs ilyen, a teljes kvíz. */
  indit(mod: KvizMod = 'teljes'): void {
    if (!this.adat) return;
    const osszes = this.adat.kviz.kerdesek;
    const ujra = new Set(this.ertekeles?.ujra ?? this.adat.ujra);
    const valogatott = mod === 'hibasak' ? osszes.filter((q) => ujra.has(q.id)) : osszes;
    const kerdesek = valogatott.length ? valogatott : osszes;
    this.mod = mod === 'hibasak' && valogatott.length ? 'hibasak' : 'teljes';
    this.lista = kerdesek.map((kerdes) => ({ kerdes: { ...kerdes }, sorrend: keveres(kerdes.valaszok.length, this.veletlen) }));
    this.valaszok = [];
    this.ertekeles = null;
    this.megoldas = null;
    this.hiba = null;
    this.kulcs = null;
    this.i = 0;
    this.tKezd = this.most();
    this.kerdesKezd();
    this.fazis = 'kerdes';
  }

  private kerdesKezd(): void {
    this.valasztott = null;
    this.megoldas = null;
    this.tKerdes = this.most();
  }

  /** A megjelenített `pozicio`-adik válasz kiválasztása (a visszajelzés előtt). */
  valaszt(pozicio: number): void {
    const q = this.aktualis;
    if (this.fazis !== 'kerdes' || !q || pozicio < 0 || pozicio >= q.sorrend.length) return;
    this.valasztott = q.sorrend[pozicio];
  }

  async nemTudom(): Promise<void> {
    if (this.fazis !== 'kerdes') return;
    this.valasztott = null;
    await this.ellenoriz(true);
  }

  /** A válasz ellenőrzése a core-nál; `tipp`: a kitöltő előzetes bizonytalansága. Hiba esetén a kérdésnél marad. */
  async ellenoriz(tipp: boolean): Promise<void> {
    const q = this.aktualis;
    if (this.fazis !== 'kerdes' || !q || this.kuld) return;
    if (this.valasztott === null && !tipp) return;               // válasz nélkül csak a „nem tudom” (tipp) megy
    if (!this.token) {
      this.hiba = 'A kitöltés lejárt: nyisd meg újra a kvízt.';
      return;
    }
    this.kuld = true;
    this.hiba = null;
    try {
      const valasz: KitoltesValaszEgy = { kerdes: q.kerdes.id, valasz: this.valasztott, tipp: tipp || this.valasztott === null, ms: Math.max(0, this.most() - this.tKerdes) };
      const m = await this.api.megoldas(this.ut, this.token, valasz);
      this.megoldas = m;
      this.valaszok.push(valasz);
      this.fazis = 'visszajelzes';
    } catch (e) {
      this.hiba = uzenet(e);
    } finally {
      this.kuld = false;
    }
  }

  async kovetkezo(): Promise<void> {
    if (this.fazis !== 'visszajelzes') return;
    if (this.i >= this.lista.length - 1) {
      await this.kiertekel();
      return;
    }
    this.i += 1;
    this.kerdesKezd();
    this.fazis = 'kerdes';
  }

  /** A kitöltés elküldése a core-nak (értékelés + mentés). Hibánál a visszajelzésnél marad: az újrapróba ugyanazzal a kulccsal megy. */
  async kiertekel(): Promise<void> {
    if (this.kuld || !this.valaszok.length) return;
    if (!this.token) {
      this.hiba = 'A kitöltés lejárt: nyisd meg újra a kvízt.';
      return;
    }
    this.kuld = true;
    this.hiba = null;
    this.kulcs ??= this.kulcsGen();
    try {
      const v = await this.api.kitoltes(this.ut, this.token, this.kulcs, this.mod, Math.max(0, this.most() - this.tKezd));
      this.ertekeles = v.ertekeles;
      this.token = v.token;
      this.fazis = 'elemzes';
      this.tracker(v.tracker.ut, v.tracker.adat);
    } catch (e) {
      this.hiba = uzenet(e);
    } finally {
      this.kuld = false;
    }
  }

  /** Kilépés: válasz nélkül a kezdőlapra; megválaszolt kérdésekkel a részleges kitöltés kiértékelése. */
  async kilep(): Promise<void> {
    if (this.valaszok.length) {
      await this.kiertekel();
      return;
    }
    this.fazis = 'kezdo';
  }

  /** Vissza a kezdőlapra az elemzés után (az előzmények frissítésével). */
  async vissza(): Promise<void> {
    await this.betolt();
  }

  /** A „hibás a kérdés” jelölés be/ki az aktuális kérdésen. */
  async jelol(): Promise<void> {
    const q = this.aktualis;
    if (!q) return;
    const uj = !q.kerdes.jelolt;
    try {
      if (!this.token) throw new Error('A kitöltés lejárt: nyisd meg újra a kvízt.');
      await this.api.jelol(this.ut, this.token, q.kerdes.id, uj);
      q.kerdes.jelolt = uj;
    } catch (e) {
      this.hiba = uzenet(e);
    }
  }

  /** A billentyű kezelése; igaz, ha a menet felhasználta (a hívó `preventDefault`-ol). */
  billentyu(e: KeyboardEvent): boolean {
    if (e.metaKey || e.ctrlKey || e.altKey) return false;
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if (this.fazis === 'kerdes') {
      const p = '1234'.indexOf(k) >= 0 ? '1234'.indexOf(k) : 'abcd'.indexOf(k);
      if (k.length === 1 && p >= 0) {
        if ((this.aktualis?.sorrend.length ?? 0) <= p) return false;
        this.valaszt(p);
        return true;
      }
      if (k === 'Enter') {
        if (this.valasztott !== null) void this.ellenoriz(false);
        return true;
      }
      if (k === 't' && this.valasztott !== null) {
        void this.ellenoriz(true);
        return true;
      }
      if (k === 'n') {
        void this.nemTudom();
        return true;
      }
      return false;
    }
    if (this.fazis === 'visszajelzes' && (k === 'Enter' || k === 'ArrowRight')) {
      void this.kovetkezo();
      return true;
    }
    return false;
  }
}
