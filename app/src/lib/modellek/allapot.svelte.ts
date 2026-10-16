// A Model Manager állapota: a modellek listája és telepítettsége (a lemezről, a core számolja), a letöltés- és mérés-feladatok
// követése a feladatsor WS-eseményein, a törlés, a mérés riportja és a saját aranyhalmazok. Hálózatot csak a felhasználó
// kattintására indít (D3): a betöltés semmit sem tölt le, a letöltés/mérés külön hívás.
import { ApiHiba, hibaUzenet, kodUzenet } from '../core/api';
import { t } from '../i18n';
import { vezerloApi } from '../vezerlo/api';
import { feladatsor as alapFeladatsor, type Feladatsor } from '../vezerlo/feladatsor.svelte';
import { LEZART, type Feladat, type FeladatAllapot } from '../vezerlo/tipusok';
import { modellApi } from './api';
import { letoltheto, merheto } from './megjelenites';
import type { FeladatKivonat, Halmazok, Modell, ModellLista, SajatOsszegzes, SajatTetel, TesztRiport, TorlesEredmeny } from './tipusok';

export type Fajta = 'letoltes' | 'teszt';
/** Egy modellhez írt utolsó eredmény: mindig szöveggel (a hiba ikonját a nézet adja, a szín nem hordoz jelentést). */
export interface Uzenet { fajta: 'hiba' | 'siker' | 'info'; szoveg: string; reszletek?: string[] }
interface Kovetett { modell: string; fajta: Fajta; feladat?: string }

/** Egy mérés-előfeltétel (és más `okok` listák) soraiból olvasható mondatok. */
export function okokSzoveg(okok: { kod: string; param?: Record<string, unknown> }[] | undefined): string[] {
  return (okok ?? []).map((o) => kodUzenet({ kod: o.kod, param: o.param }, t('modellek.teszt.ok_ismeretlen')));
}

export class ModellTar {
  lista = $state.raw<ModellLista | null>(null);
  hiba = $state<string | null>(null);
  betoltes = $state(false);
  halmazok = $state.raw<Halmazok | null>(null);
  halmazHiba = $state<string | null>(null);
  uzenetek = $state<Record<string, Uzenet>>({});
  riportok = $state.raw<Record<string, TesztRiport>>({});
  /** A modellen éppen folyó (rövid) művelet: a gombok tiltásához. */
  foglalt = $state<Record<string, boolean>>({});
  private kovetett = $state.raw<Record<string, Kovetett>>({});
  private sorszam = 0;
  private feldolgozva = new Set<string>();

  constructor(
    readonly feladatsor: Feladatsor = alapFeladatsor,
    private readonly api = modellApi,
  ) {}

  readonly modellek = $derived(this.lista?.modellek ?? []);
  /** Az ajánlott, még nem telepített modellek, amelyeknek nem fut a letöltése. */
  readonly ajanlottHianyzik = $derived(this.modellek.filter((m) => m.ajanlott && letoltheto(m) && !this.aktiv(m, 'letoltes')));
  readonly ajanlottGb = $derived(this.ajanlottHianyzik.reduce((o, m) => o + (m.meret_gb ?? 0), 0));
  readonly ajanlottKesz = $derived(this.modellek.filter((m) => m.ajanlott && merheto(m)).length);
  readonly ajanlottOsszes = $derived(this.modellek.filter((m) => m.ajanlott).length);
  /** Fut-e követett letöltés vagy mérés (a nézet ekkor frissíti a feladatsort). */
  readonly dolgozik = $derived(Object.keys(this.kovetett).length > 0);

  /** A követett feladatok (a nézet effektje ezt is figyeli, hogy a már lezárult feladat se maradjon le). */
  get kovetes() { return this.kovetett; }

  feladatCim = (f: string): string => this.lista?.feladatok[f]?.cim ?? f;
  funkcioCim = (f: string | null): string | null => (f ? (this.lista?.funkciok[f]?.cim ?? null) : null);
  cimek = $derived(Object.fromEntries(Object.entries(this.lista?.feladatok ?? {}).map(([k, v]) => [k, v.cim])) as Record<string, string>);

  // ---------------------------------------------------------------- betöltés
  async betolt(): Promise<void> {
    const n = ++this.sorszam;
    this.betoltes = true;
    try {
      const l = await this.api.lista();
      if (n !== this.sorszam) return;
      this.lista = l;
      this.hiba = null;
      for (const m of l.modellek) this.adoptal(m);
    } catch (e) {
      if (n === this.sorszam) this.hiba = hibaUzenet(e);
    } finally {
      if (n === this.sorszam) this.betoltes = false;
    }
  }

  /** Egy modell újraolvasása (letöltés/törlés/mérés után). */
  async frissit(id: string): Promise<void> {
    try {
      const m = await this.api.egy(id);
      if (this.lista) this.lista = { ...this.lista, modellek: this.lista.modellek.map((x) => (x.id === id ? m : x)) };
      this.adoptal(m);
    } catch (e) {
      this.uzenet(id, 'hiba', hibaUzenet(e));
    }
  }

  private adoptal(m: Modell): void {
    for (const [fajta, k] of [['letoltes', m.letoltes], ['teszt', m.teszt]] as [Fajta, FeladatKivonat | null][])
      if (k && !LEZART.has(k.allapot as FeladatAllapot)) this.kovet(k.feladat_id, { modell: m.id, fajta, feladat: k.feladat });
  }

  private kovet(feladatId: string, k: Kovetett): void {
    if (this.kovetett[feladatId] || this.feldolgozva.has(feladatId)) return;
    this.kovetett = { ...this.kovetett, [feladatId]: k };
  }

  private elenged(feladatId: string): void {
    const { [feladatId]: _, ...marad } = this.kovetett;
    this.kovetett = marad;
    this.feldolgozva.add(feladatId);
  }

  private uzenet(id: string, fajta: Uzenet['fajta'], szoveg: string, reszletek?: string[]): void {
    this.uzenetek = { ...this.uzenetek, [id]: { fajta, szoveg, reszletek } };
  }

  torolUzenet(id: string): void {
    const { [id]: _, ...marad } = this.uzenetek;
    this.uzenetek = marad;
  }

  private async foglalja<T>(id: string, fn: () => Promise<T>): Promise<T | undefined> {
    if (this.foglalt[id]) return undefined;
    this.foglalt = { ...this.foglalt, [id]: true };
    try {
      return await fn();
    } finally {
      this.foglalt = { ...this.foglalt, [id]: false };
    }
  }

  // ---------------------------------------------------------------- követés
  /** A modell futó letöltése/mérése: a feladatsor friss állapotából, ennek hiányában a kivonatból. */
  aktiv(m: Modell, fajta: Fajta): { feladat_id: string; allapot: string; szazalek: number; feladat?: string } | null {
    for (const [fid, k] of Object.entries(this.kovetett)) {
      if (k.modell !== m.id || k.fajta !== fajta) continue;
      const f = this.feladatsor.kap(fid);
      if (f && LEZART.has(f.allapot)) continue;
      const kivonat = (fajta === 'letoltes' ? m.letoltes : m.teszt)?.feladat_id === fid ? (fajta === 'letoltes' ? m.letoltes : m.teszt) : null;
      return { feladat_id: fid, allapot: f?.allapot ?? kivonat?.allapot ?? 'sorban', szazalek: Math.max(0, Math.min(100, f?.szazalek ?? kivonat?.szazalek ?? 0)), feladat: k.feladat };
    }
    return null;
  }

  /** A feladatsor friss listájából a befejezett feladatok lezárása (üzenet, újraolvasás, riport). */
  async szinkron(lista: Feladat[]): Promise<void> {
    for (const [fid, k] of Object.entries(this.kovetett)) {
      const f = lista.find((x) => x.id === fid);
      if (!f) {
        // a feladatsor már betöltött, de a feladat nincs benne: elévült → a modell állapotát a lemezről olvassuk újra
        if (this.feladatsor.betoltve) { this.elenged(fid); await this.frissit(k.modell); }
        continue;
      }
      await this.lezarHaKesz(f);
    }
  }

  /** Egyetlen feladat lezárása, ha követjük és véget ért (a megszakítás válasza is így zár). */
  private async lezarHaKesz(f: Feladat): Promise<void> {
    const k = this.kovetett[f.id];
    if (!k || !LEZART.has(f.allapot)) return;
    this.elenged(f.id);
    await this.lezar(k, f);
  }

  private async lezar(k: Kovetett, f: Feladat): Promise<void> {
    const hibaSzoveg = () => kodUzenet({ hiba: f.hiba, kod: f.kod, param: f.param }, t('modellek.feladat_hiba'));
    if (k.fajta === 'letoltes') {
      if (f.allapot === 'kesz') this.uzenet(k.modell, 'siker', t('modellek.letoltes.kesz'));
      else if (f.allapot === 'hiba' || f.allapot === 'megszakadt') this.uzenet(k.modell, 'hiba', t('A letöltés nem sikerült: {ok}', { ok: hibaSzoveg() }));
      else this.uzenet(k.modell, 'info', t('modellek.letoltes.megszakitva'));
    } else if (f.allapot === 'hiba' || f.allapot === 'megszakadt') {
      this.uzenet(k.modell, 'hiba', t('A mérés nem fejeződött be: {ok}', { ok: hibaSzoveg() }));
    } else if (f.allapot !== 'kesz') {
      this.uzenet(k.modell, 'info', t('modellek.teszt.megszakitva'));
    }
    await this.frissit(k.modell);
    if (k.fajta === 'teszt' && k.feladat && f.allapot !== 'torolve') await this.riportBetolt(k.modell, k.feladat);
  }

  // ---------------------------------------------------------------- letöltés, törlés
  async letoltes(m: Modell): Promise<boolean> {
    return (await this.foglalja(m.id, async () => {
      this.torolUzenet(m.id);
      try {
        const r = await this.api.letoltes(m.id);
        this.feladatsor.upsert(r.feladat);
        this.kovet(r.feladat.id, { modell: m.id, fajta: 'letoltes' });
        await this.frissit(m.id);
        return true;
      } catch (e) {
        if (e instanceof ApiHiba && e.kod === 'modell.letoltes_fut') { await this.frissit(m.id); return true; }
        this.uzenet(m.id, 'hiba', hibaUzenet(e));
        return false;
      }
    })) ?? false;
  }

  async megszakit(m: Modell): Promise<void> {
    await this.foglalja(m.id, async () => {
      try {
        const r = await this.api.megszakit(m.id);
        this.feladatsor.upsert(r.feladat);
        await this.lezarHaKesz(r.feladat);
      } catch (e) {
        this.uzenet(m.id, 'hiba', hibaUzenet(e));
      }
    });
  }

  async torol(m: Modell): Promise<TorlesEredmeny | undefined> {
    return this.foglalja(m.id, async () => {
      try {
        const r = await this.api.torol(m.id);
        this.uzenet(m.id, 'siker', t('modellek.torles.kesz'), r.kalibracio_levett.length ? [t('A kalibrált jel levéve ezekről: {feladatok}.', { feladatok: r.kalibracio_levett.map(this.feladatCim).join(', ') })] : undefined);
        await this.frissit(m.id);
        return r;
      } catch (e) {
        this.uzenet(m.id, 'hiba', hibaUzenet(e));
        return undefined;
      }
    });
  }

  /** „Install recommended models”: az ajánlott, még hiányzó modellek letöltése egymás után (a felhasználó kattintására). */
  async ajanlottTelepit(): Promise<number> {
    let indult = 0;
    for (const m of [...this.ajanlottHianyzik]) if (await this.letoltes(m)) indult++;
    return indult;
  }

  // ---------------------------------------------------------------- mérés
  /** A mérés indítása; az előfeltétel hiánya (400) soronként olvasható szöveggel kerül az üzenetbe. */
  async tesztInditas(m: Modell, feladat: string, halmaz: 'szallitott' | 'sajat'): Promise<boolean> {
    return (await this.foglalja(m.id, async () => {
      this.torolUzenet(m.id);
      try {
        const r = await this.api.teszt(m.id, feladat, halmaz);
        this.feladatsor.upsert(r.feladat);
        this.kovet(r.feladat.id, { modell: m.id, fajta: 'teszt', feladat });
        await this.frissit(m.id);
        return true;
      } catch (e) {
        const okok = e instanceof ApiHiba && Array.isArray(e.adat.okok) ? (e.adat.okok as { kod: string; param?: Record<string, unknown> }[]) : [];
        this.uzenet(m.id, 'hiba', okok.length ? t('modellek.teszt.nem_indithato') : hibaUzenet(e), okok.length ? okokSzoveg(okok) : undefined);
        return false;
      }
    })) ?? false;
  }

  async tesztLeallit(m: Modell): Promise<void> {
    const a = this.aktiv(m, 'teszt');
    if (!a) return;
    try {
      await vezerloApi.leallit(a.feladat_id, false);
    } catch (e) {
      this.uzenet(m.id, 'hiba', hibaUzenet(e));
    }
  }

  async riportBetolt(id: string, feladat: string): Promise<TesztRiport | null> {
    try {
      const r = await this.api.riport(id, feladat);
      this.riportok = { ...this.riportok, [`${id}:${feladat}`]: r };
      return r;
    } catch (e) {
      // nincs még riport (404): nem hiba
      if (!(e instanceof ApiHiba && e.kod === 'modell.nincs_teszt')) this.uzenet(id, 'hiba', hibaUzenet(e));
      return null;
    }
  }

  // ---------------------------------------------------------------- saját aranyhalmaz
  async halmazokBetolt(): Promise<void> {
    try {
      this.halmazok = await this.api.halmazok();
      this.halmazHiba = null;
    } catch (e) {
      this.halmazHiba = hibaUzenet(e);
    }
  }

  private frissitSajat(o: SajatOsszegzes): void {
    if (this.halmazok) this.halmazok = { ...this.halmazok, sajat: { ...this.halmazok.sajat, [o.feladat]: o } };
  }

  async halmazLetrehoz(feladat: string, tetelek: SajatTetel[], nyelv: string): Promise<SajatOsszegzes> {
    const o = await this.api.halmazLetrehoz(feladat, tetelek, nyelv);
    this.frissitSajat(o);
    return o;
  }

  async halmazJovahagy(feladat: string, tartott: string[]): Promise<SajatOsszegzes> {
    const o = await this.api.halmazJovahagy(feladat, tartott);
    this.frissitSajat(o);
    return o;
  }

  async halmazValaszt(feladat: string, halmaz: 'sajat' | 'szallitott'): Promise<SajatOsszegzes> {
    const o = await this.api.halmazValaszt(feladat, halmaz);
    this.frissitSajat(o);
    return o;
  }

  async halmazTorol(feladat: string): Promise<void> {
    await this.api.halmazTorol(feladat);
    await this.halmazokBetolt();
  }
}

export const modellek = new ModellTar();
