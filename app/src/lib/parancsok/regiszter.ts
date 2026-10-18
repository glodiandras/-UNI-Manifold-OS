// A parancsregiszter (C07): minden funkció ide regisztrál, és innen fut — a ⌘P palettából, a
// gyorsbillentyűről és a gombokról egyaránt. A későbbi modulok (C08–C30) ugyanezt az API-t használják:
//
//   const le = regiszter.regisztral({ id: 'kartya.ebbol', nev: 'Kártyák ebből', kategoria: 'Tanulás',
//                                     futtat: () => … });
//   …
//   le(); // leiratkozás (pl. a nézet bezárásakor)
//
// A `nev` és a `kategoria` a magyar KULCS (stabil, az azonosítók mellett ez a szótár kulcsa): a felület nyelvére a megjelenítés helyén
// fordítódik (`parancsNev(p)` / `parancsKategoria(p)`: a paletta, a helyi menü), nem a regisztrációkor — így nyelvváltáskor frissül.
// Az `id` változatlan (a tracker és a legutóbbiak ezt tárolják). Fordítandó szöveg jelölése a regisztrációban: `nev: tk('Kártyák ebből')`.
// Dinamikus név (`3. fül`, `X bekapcsolása`) getterrel adható, amely maga hív `t()`-t (a regisztráció megőrzi a gettert):
//   { id: 'ful.3', get nev() { return t('{n}. fül', { n: 3 }); }, … }

import { parancsEngedelyezett } from '../beallitasok/modulok';
import type { IconNode } from 'lucide';
import { hibaUzenet } from '../core/api';
import { ertesitesek } from '../ertesites/ertesites.svelte';
import { t } from '../i18n';
import { elemez, fenntartott, normalizalLeiras } from './billentyuk';

export interface Parancs {
  /** Egyedi, pontokkal tagolt azonosító: `<modul>.<művelet>`. */
  id: string;
  /** A palettában megjelenő név: a magyar kulcs (igével vagy főnévvel kezdve); megjelenítéskor `parancsNev(p)` fordítja. */
  nev: string;
  /** A paletta kategória-felirata: a magyar kulcs; megjelenítéskor `parancsKategoria(p)` fordítja. */
  kategoria?: string;
  /** Pl. „Mod+Shift+M”; ütközés esetén a regisztráció hibát dob. */
  billentyu?: string;
  ikon?: IconNode;
  /** Ha hamisat ad, a parancs nem látszik a palettában és a billentyűje sem fut. */
  elerheto?: () => boolean;
  /** Megjelenjen-e a palettában (alap: igen). */
  palettaban?: boolean;
  /** Nyitott modális átfedés (paletta, váltó) alatt is fusson-e a billentyűje. */
  atfedesben?: boolean;
  /** A billentyűje a szerkesztőben (CodeMirror) nem fut: ott a CM azonos akkordja nyer (pl. ⌥⌘↓ = kurzor lefelé); a
   *  palettából és a szerkesztőn kívül a parancs fut. */
  szerkesztoNyer?: boolean;
  futtat: () => void | Promise<void>;
}

/** A parancs neve az aktív nyelven (a kulcs `t()`-je; a getteres, már fordított név változatlan marad). */
export function parancsNev(p: Pick<Parancs, 'nev'>): string {
  return Object.getOwnPropertyDescriptor(p, 'nev')?.get ? p.nev : t(p.nev);
}

/** A parancs kategóriája az aktív nyelven; üres, ha nincs. */
export function parancsKategoria(p: Pick<Parancs, 'kategoria'>): string {
  return p.kategoria ? t(p.kategoria) : '';
}

type Figyelo = () => void;

/** Honnan indult a parancs (a tracker használati mérése, C27): a mérés csak az azonosítót és ezt a forrást látja. */
export type ParancsForras = 'billentyu' | 'paletta' | 'menu' | 'gomb' | 'hej' | 'egyeb';
type Megfigyelo = (id: string, forras: ParancsForras) => void;

export class Regiszter {
  private readonly parancsok = new Map<string, Parancs>();
  private readonly akkordok = new Map<string, string>();
  private readonly alapBillentyuk = new Map<string, string>();
  private felulirasok: Record<string, string> = {};
  private readonly figyelok = new Set<Figyelo>();
  /** Minden sikeres futás után (a legutóbbiak listájához). */
  futasUtan: ((id: string) => void) | null = null;
  private readonly megfigyelok = new Set<Megfigyelo>();

  /** Megfigyelő minden sikeres futásra (az azonosítóval és a forrással); a `futasUtan` mellett él. */
  megfigyel(f: Megfigyelo): () => void {
    this.megfigyelok.add(f);
    return () => this.megfigyelok.delete(f);
  }

  regisztral(p: Parancs): () => void {
    // i18n-ignore: programozói hiba (a fejlesztőnek szól, a felhasználó nem látja)
    if (!/^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(p.id)) throw new Error(`hibás parancsazonosító: ${p.id}`);
    // i18n-ignore: programozói hiba (a fejlesztőnek szól, a felhasználó nem látja)
    if (this.parancsok.has(p.id)) throw new Error(`már regisztrált parancs: ${p.id}`);
    let akkord: string | undefined;
    if (p.billentyu) this.alapBillentyuk.set(p.id, normalizalLeiras(p.billentyu));
    const kert = Object.hasOwn(this.felulirasok, p.id) ? this.felulirasok[p.id] : p.billentyu;
    if (kert) {
      akkord = normalizalLeiras(kert);
      const masik = this.akkordok.get(akkord);
      // i18n-ignore: programozói hiba (a fejlesztőnek szól, a felhasználó nem látja)
      if (masik) throw new Error(`a(z) ${p.billentyu} billentyű már foglalt: ${masik}`);
    }
    // a getterek (dinamikus, `t()`-vel számolt név) megmaradnak: a leíró-másolat nem értékeli ki őket a regisztrációkor
    const leirok = Object.getOwnPropertyDescriptors(p);
    for (const l of Object.values(leirok)) if ('value' in l) l.writable = l.configurable = true; // mint a korábbi `{ ...p }`: módosítható másolat
    leirok.billentyu = { value: akkord, enumerable: true, writable: true, configurable: true };
    const tarolt = Object.defineProperties({}, leirok) as Parancs;
    this.parancsok.set(p.id, tarolt);
    if (akkord) this.akkordok.set(akkord, p.id);
    this.jelez();
    return () => {
      if (this.parancsok.get(p.id) !== tarolt) return;
      this.parancsok.delete(p.id);
      this.alapBillentyuk.delete(p.id);
      for (const [a, id] of this.akkordok) if (id === p.id) this.akkordok.delete(a);
      this.jelez();
    };
  }

  /** Több parancs egyszerre; egy leiratkozó mindegyikre. */
  regisztralMind(lista: Parancs[]): () => void {
    const le = lista.map((p) => this.regisztral(p));
    return () => le.forEach((f) => f());
  }

  kap(id: string): Parancs | undefined {
    return this.parancsok.get(id);
  }

  elerheto(p: Parancs): boolean {
    try {
      return parancsEngedelyezett(p.id) && (p.elerheto ? p.elerheto() : true);
    } catch {
      return false;
    }
  }

  /** A beállítások a rejtett és épp nem elérhető parancsokat is felsorolják. */
  mind(): Parancs[] { return [...this.parancsok.values()]; }
  alapBillentyu(id: string): string { return this.alapBillentyuk.get(id) ?? ''; }
  /** Egy kötés önmagában (az többi parancstól függetlenül) elfogadható-e: alak, módosító, fenntartott (natív menü) akkord. */
  private akkordEllenoriz(id: string, kert: string): string {
    let a: ReturnType<typeof elemez>;
    try { a = elemez(kert); } catch { throw new Error(t('beallitasok.hibas_billentyu')); }
    if (!a.mod && !a.ctrl && !a.alt && !/^F\d+$/.test(a.kulcs)) throw new Error(t('beallitasok.modosito_kell'));
    const kanonikus = normalizalLeiras(kert);
    // a natív menü akkordjai (⌘C/V/X/Z/A/H/M/Q, ⇧⌘Z, ⌥⌘H, ⌃⌘F, ⌘, és ⇧⌘O): a lista a shell menüjéből generált (RESERVED_CHORDS)
    if (fenntartott(kanonikus, id) || (id === 'beallitasok.megnyit' && kanonikus !== 'Mod+,')) throw new Error(t('beallitasok.foglalt_billentyu'));
    return kanonikus;
  }
  /** Teljes csere: előbb ellenőriz, ütközésnél a működő kiosztás érintetlen. */
  billentyuketEllenoriz(feluliras: Record<string, string>): void {
    const latott = new Map<string, string>();
    for (const [id, kert] of Object.entries(feluliras)) {
      if (!kert) continue;
      this.akkordEllenoriz(id, kert);
    }
    for (const p of this.parancsok.values()) {
      const kert = Object.hasOwn(feluliras, p.id) ? feluliras[p.id] : this.alapBillentyu(p.id);
      if (p.id === 'beallitasok.megnyit' && kert !== 'Mod+,') throw new Error(t('beallitasok.foglalt_billentyu'));
      if (!kert) continue;
      const a = normalizalLeiras(kert);
      if (Object.hasOwn(feluliras, p.id) && fenntartott(a, p.id)) throw new Error(t('beallitasok.foglalt_billentyu'));
      if (latott.has(a)) throw new Error(t('A gyorsbillentyű már foglalt: {nev}', { nev: parancsNev(this.parancsok.get(latott.get(a)!)!) }));
      latott.set(a, p.id);
    }
  }
  /** Türelmes betöltés (tárolt vagy importált kiosztás): az érvénytelen, fenntartott vagy ütköző bejegyzést kihagyja és visszaadja,
   *  a többit alkalmazza — egy rossz kötés nem dobja el az egész kiosztást. Az ütközést a KIALAKULÓ kiosztáson ítéli meg (két akkord
   *  cseréje elfogadott); ha egy bejegyzés egy változatlanul maradó alapértelmezéssel vagy egy korábbi bejegyzéssel ütközik, az marad ki. */
  billentyuketAlkalmazTurelmesen(feluliras: Record<string, string>): { id: string; akkord: string; ok: string }[] {
    const elfogadott: Record<string, string> = {};
    const kihagyott: { id: string; akkord: string; ok: string }[] = [];
    for (const [id, kert] of Object.entries(feluliras)) {
      if (!kert) {
        if (id === 'beallitasok.megnyit') kihagyott.push({ id, akkord: kert, ok: t('beallitasok.foglalt_billentyu') });
        else elfogadott[id] = kert;
        continue;
      }
      try { this.akkordEllenoriz(id, kert); elfogadott[id] = kert; }
      catch (e) { kihagyott.push({ id, akkord: kert, ok: e instanceof Error ? e.message : String(e) }); }
    }
    for (;;) {
      const csoport = new Map<string, string[]>();
      for (const p of this.parancsok.values()) {
        const kert = Object.hasOwn(elfogadott, p.id) ? elfogadott[p.id] : this.alapBillentyu(p.id);
        if (!kert) continue;
        const a = normalizalLeiras(kert);
        csoport.set(a, [...(csoport.get(a) ?? []), p.id]);
      }
      const kiesik = new Map<string, string>();
      for (const idk of csoport.values()) {
        if (idk.length < 2) continue;
        const sajat = idk.filter((id) => Object.hasOwn(elfogadott, id));
        const marad = idk.filter((id) => !Object.hasOwn(elfogadott, id));
        for (const id of marad.length ? sajat : sajat.slice(1)) kiesik.set(id, idk.find((x) => x !== id)!);
      }
      if (!kiesik.size) break;
      for (const [id, masik] of kiesik) {
        kihagyott.push({ id, akkord: elfogadott[id], ok: t('A gyorsbillentyű már foglalt: {nev}', { nev: parancsNev(this.parancsok.get(masik)!) }) });
        delete elfogadott[id];
      }
    }
    this.billentyuketAlkalmaz(elfogadott);
    return kihagyott;
  }
  billentyuketAlkalmaz(feluliras: Record<string, string>): void {
    this.billentyuketEllenoriz(feluliras);
    this.felulirasok = { ...feluliras };
    this.akkordok.clear();
    for (const p of this.parancsok.values()) {
      const kert = Object.hasOwn(feluliras, p.id) ? feluliras[p.id] : this.alapBillentyu(p.id);
      p.billentyu = kert ? normalizalLeiras(kert) : undefined;
      if (p.billentyu) this.akkordok.set(p.billentyu, p.id);
    }
    this.jelez();
  }

  /** A palettában látható, épp elérhető parancsok. */
  lista(): Parancs[] {
    return [...this.parancsok.values()].filter((p) => p.palettaban !== false && this.elerheto(p));
  }

  akkordhoz(kanonikusAkkord: string): Parancs | undefined {
    const id = this.akkordok.get(kanonikusAkkord);
    return id ? this.parancsok.get(id) : undefined;
  }

  /** Futtatás azonosító szerint; hamis, ha nincs ilyen vagy nem elérhető. */
  futtat(id: string, forras: ParancsForras = 'egyeb'): boolean {
    const p = this.parancsok.get(id);
    if (!p || !this.elerheto(p)) return false;
    // a parancs hibája (szinkron vagy aszinkron) a felhasználónak is látszik, nem csak a konzolon
    const hibaJelez = (e: unknown) => {
      console.error(`parancs hiba: ${id}`, e); // i18n-ignore: fejlesztői konzol-napló
      ertesitesek.ertesit({ szint: 'hiba', cim: t('A parancs nem sikerült: {nev}', { nev: parancsNev(p) }), szoveg: hibaUzenet(e) });
    };
    try {
      const r = p.futtat();
      if (r instanceof Promise) r.catch(hibaJelez);
    } catch (e) {
      hibaJelez(e);
    }
    this.futasUtan?.(id);
    for (const f of this.megfigyelok) {
      try {
        f(id, forras);
      } catch (e) {
        console.error('parancs-megfigyelő hiba', e); // a megfigyelő hibája nem akasztja a parancsot — i18n-ignore: fejlesztői konzol-napló
      }
    }
    return true;
  }

  feliratkoz(f: Figyelo): () => void {
    this.figyelok.add(f);
    return () => this.figyelok.delete(f);
  }

  private jelez() {
    for (const f of this.figyelok) f();
  }
}

export const regiszter = new Regiszter();
