// A keresőpanel állapota és kérései (C11a, ⌘⇧F): a core keresőnyelvének (szó, "kifejezés", OR, -tagadás, zárójel,
// path:, file:, tag:, line:, /regex/) egyetlen kliense. A lekérdezés késleltetve megy (250 ms), az elavult válasz
// eldobódik; a core 400-as magyar hibaüzenete (hibás zárójel, hibás regex, a 2 s-os regex-időtúllépés) szó szerint
// jelenik meg. A panel állapota az oldalsáv nézetváltásán át megmarad (nem a komponensben él).

import { t } from '../i18n';

import type { CoreKapcsolat } from '../core/ws.svelte';
import { modulEngedelyezett } from '../beallitasok/allapot.svelte';
import { ApiHiba, kerdez } from '../core/api';

export interface KeresesHely {
  /** 1-től */
  sor: number;
  /** 0-tól, kódpontban (Python); a felület alakítja UTF-16-ra */
  oszlop: number;
  hossz: number;
  szoveg: string;
  elotte?: string[];
  utana?: string[];
  /** PDF-találat (C25c): a sor oldala (1-től) */
  oldal?: number;
  /** felirat-találat (C25c): a mondat kezdete másodpercben */
  mp?: number;
}

export interface KeresesFajl {
  ut: string;
  pont: number;
  talalatok: KeresesHely[];
  /** C25c: a PDF lapjainak, ill. a VTT-felirat mondatainak találata (a jegyzeté nem hordozza) */
  tipus?: 'pdf' | 'felirat';
  /** felirat-találat: a hozzá tartozó videó vagy hang útja (a melléklet-szabály szerint), ha van */
  media?: string | null;
  /** jelentés szerinti keresésben (C25b) a jegyzet legjobb darabja: ide nyit, ha nincs szó szerinti sor-találat */
  darab?: { sor_kezd: number; sor_veg: number; fejezet: string[]; szoveg: string };
}

export interface KeresesValasz {
  q: string;
  osszes: number;
  /** korai leállás vagy lejárt időkeret: az `osszes` alsó korlát („legalább N”) */
  legalabb?: boolean;
  talalatok: KeresesFajl[];
  /** a hibrid végpont (C25b): `hibrid` | `lexikai`, és ha lexikai, miért */
  mod?: 'hibrid' | 'lexikai';
  ok?: string | null;
}

/** A jelentés szerinti keresés (C25b) a modellek betöltése alatt ennyi időnként kérdez újra (a core a háttérben dolgozik). */
export const BETOLTES_UJRA_MS = 2000;

/** Egy találati sor: az azonos sor több egyezése egy sorba vonva (a core egyezésenként ad találatot). */
export interface SorTalalat {
  sor: number;
  /** az első egyezés oszlopa (kódpont): ide ugrik a szerkesztő */
  oszlop: number;
  szoveg: string;
  elotte?: string[];
  utana?: string[];
  oldal?: number;
  mp?: number;
  /** az egyezések (kódpont-oszlop és hossz), oszlop szerint */
  jelek: { oszlop: number; hossz: number }[];
}

/** A fájl találatai sorokra egyesítve: az ugyanazon sorban álló egyezések egy sor, több kiemeléssel. */
export function sorokraEgyesit(f: KeresesFajl): SorTalalat[] {
  const ki = new Map<number, SorTalalat>();
  for (const h of f.talalatok) {
    const mar = ki.get(h.sor);
    if (mar) mar.jelek.push({ oszlop: h.oszlop, hossz: h.hossz });
    else
      ki.set(h.sor, { sor: h.sor, oszlop: h.oszlop, szoveg: h.szoveg, elotte: h.elotte, utana: h.utana, oldal: h.oldal, mp: h.mp, jelek: [{ oszlop: h.oszlop, hossz: h.hossz }] });
  }
  for (const s of ki.values()) {
    s.jelek.sort((a, b) => a.oszlop - b.oszlop);
    s.oszlop = s.jelek[0].oszlop;
  }
  return [...ki.values()];
}

/** A sor kiemelésre szabdalt darabjai (az első egyezés körüli ablak; a kódpont-oszlopokkal). */
export function darabok(h: SorTalalat, elotte = 36, utana = 90): { t: string; jelolt: boolean }[] {
  const cp = Array.from(h.szoveg);
  const elso = h.jelek[0];
  const kezd = Math.max(0, elso.oszlop - elotte);
  const veg = Math.min(cp.length, elso.oszlop + elso.hossz + utana);
  const ki: { t: string; jelolt: boolean }[] = [];
  let p = kezd;
  for (const j of h.jelek) {
    if (j.oszlop < p || j.oszlop >= veg) continue;
    if (j.oszlop > p) ki.push({ t: cp.slice(p, j.oszlop).join(''), jelolt: false });
    const e = Math.min(veg, j.oszlop + j.hossz);
    ki.push({ t: cp.slice(j.oszlop, e).join(''), jelolt: true });
    p = e;
  }
  if (p < veg) ki.push({ t: cp.slice(p, veg).join(''), jelolt: false });
  if (kezd > 0 && ki.length) ki[0] = { ...ki[0], t: '… ' + ki[0].t.trimStart() };
  return ki;
}

/** Időkód olvasható alakja (`m:ss`, egy óra fölött `ó:mm:ss`). */
export function idokod(mp: number): string {
  const s = Math.max(0, Math.floor(mp));
  const o = Math.floor(s / 3600);
  const p = Math.floor((s % 3600) / 60);
  const m = String(s % 60).padStart(2, '0');
  return o ? `${o}:${String(p).padStart(2, '0')}:${m}` : `${p}:${m}`;
}

/** A találati sor helyének címkéje: PDF-nél az oldal, feliratnál az időkód, máshol a sorszám (C25c). */
export function helyCimke(h: { sor: number; oldal?: number; mp?: number }): string {
  if (h.oldal !== undefined) return `${h.oldal}. o.`;
  if (h.mp !== undefined) return idokod(h.mp);
  return String(h.sor);
}

/** Hova nyit a találat (C25c): a PDF az oldalára (`page=N`), a felirat a médiája másodpercére (`t=N`); a jegyzet a sorára
 *  (`horgony: null`, a szerkesztő ugrik). A média nélküli felirat maga a VTT-fájl. */
export function talalatCel(f: KeresesFajl, h?: { sor: number; oldal?: number; mp?: number }): { ut: string; horgony: string | null } {
  if (f.tipus === 'pdf') return { ut: f.ut, horgony: h?.oldal ? `page=${h.oldal}` : null };
  if (f.tipus === 'felirat' && f.media) return { ut: f.media, horgony: h?.mp !== undefined ? `t=${Math.floor(h.mp)}` : null };
  return { ut: f.ut, horgony: null };
}

/** A PDF-szöveg kinyerésének állapota (C25c; a core `index` állapotának `pdf_szoveg` része és a `pdf_szoveg` esemény). */
export interface PdfSzovegAllapot {
  osszes: number;
  kesz: number;
  varakozik?: number;
  kinyero?: boolean;
  hiba?: string | null;
}

/** A PDF-szöveg kinyerése még tart (a kinyerő fut, és nincs minden PDF kész): ilyenkor a panel kimondja. */
export function pdfFolyamatban(a: PdfSzovegAllapot | null | undefined): PdfSzovegAllapot | null {
  return a && a.kinyero && a.kesz < a.osszes ? a : null;
}

export const KERESES_LIMIT = 200;
export const KESLELTETES_MS = 250;
/** Ennél rövidebb lekérdezés (kódpontban) nem indít keresést: az egybetűs szó a teljes indexet végigmérné (T152). */
export const MIN_HOSSZ = 2;

/** A kódpont-oszlop UTF-16 eltolássá (a szerkesztő `ugras`-ához). */
export function utf16Oszlop(sor: string, oszlop: number): number {
  return Array.from(sor).slice(0, oszlop).join('').length;
}

export class VaultKereses {
  q = $state('');
  eredmeny = $state.raw<KeresesValasz | null>(null);
  /** a core magyar hibaüzenete vagy a kapcsolati hiba */
  hiba = $state<string | null>(null);
  /** az index még épül (503): az `index` esemény után újrapróbáljuk */
  indexEpul = $state(false);
  folyamat = $state(false);
  /** Növelve a keresőmezőre fókuszál és kijelöli a szöveget (⌘⇧F). */
  fokuszKer = $state(0);
  /** a keresés előtölthető (pl. „Keresés ebben a mappában”) */
  private sorszam = 0;
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private vezerlo: AbortController | null = null;
  private readonly figyelok = new Map<CoreKapcsolat, { db: number; le: () => void }>();
  private igenylok = 0;
  private frissitesIdozito: ReturnType<typeof setTimeout> | null = null;

  /** Az overlay és a dokkolt lista egy keresést és egy WS-előfizetést használ; az utolsó fogyasztó leállítja a háttérmunkát. */
  igenyel(k: CoreKapcsolat): () => void {
    const meglevo = this.figyelok.get(k);
    if (meglevo) meglevo.db++;
    else {
      const le = [k.figyel('index', () => {
        if (this.indexEpul) this.indexKesz(); else this.valtozasra();
      }), k.figyel('pdf_szoveg', e => { this.pdfSzoveg = e as unknown as PdfSzovegAllapot; this.valtozasra(); }),
      k.figyel('vault_valtozas', () => this.valtozasra())];
      this.figyelok.set(k, { db: 1, le: () => le.forEach(f => f()) });
    }
    if (++this.igenylok === 1 && this.q.trim() && !this.folyamat && modulEngedelyezett('kereses')) this.utemez(true);
    let el = true;
    return () => {
      if (!el) return;
      el = false;
      const figyelo = this.figyelok.get(k);
      if (figyelo && --figyelo.db === 0) { figyelo.le(); this.figyelok.delete(k); }
      if (--this.igenylok === 0) {
        if (this.frissitesIdozito) clearTimeout(this.frissitesIdozito);
        if (this.idozito) clearTimeout(this.idozito);
        this.frissitesIdozito = this.idozito = null;
        this.sorszam++;
        this.vezerlo?.abort(); this.vezerlo = null; this.folyamat = false;
      }
    };
  }

  private valtozasra(): void {
    if (!this.igenylok || !modulEngedelyezett('kereses') || !this.q.trim()) return;
    if (this.frissitesIdozito) clearTimeout(this.frissitesIdozito);
    this.frissitesIdozito = setTimeout(() => {
      this.frissitesIdozito = null;
      if (this.igenylok && modulEngedelyezett('kereses')) this.utemez(true);
    }, 600);
  }
  /** a lekérdezés a minimális hossz alatt van (a panel tippet mutat) */
  rovid = $state(false);
  /** „Jelentés szerint” (C25b): a hibrid végpont (szó szerinti + vektoros, rerankerrel); alapból a szó szerinti keresés */
  jelentes = $state(false);
  /** a jelentés szerinti rész modelljei töltődnek: addig a szó szerinti találatok látszanak, és a kérés megismétlődik */
  betoltes = $state(false);

  /** A „Jelentés szerint” kapcsoló: a mostani lekérdezés azonnal újrafut. */
  jelentesValt(be = !this.jelentes): void {
    this.jelentes = be;
    this.utemez(true);
  }

  /** A lekérdezés beállítása; `azonnal`: nincs késleltetés (előtöltés, Enter). */
  beallit(q: string, azonnal = false): void {
    this.q = q;
    this.utemez(azonnal);
  }

  /** A mezőre fókusz, opcionálisan előtöltött lekérdezéssel. */
  fokuszal(elotolt?: string): void {
    if (elotolt !== undefined) this.beallit(elotolt, true);
    this.fokuszKer += 1;
  }

  utemez(azonnal = false): void {
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = null;
    const hossz = Array.from(this.q.trim()).length;
    this.rovid = hossz > 0 && hossz < MIN_HOSSZ;
    if (hossz < MIN_HOSSZ) {
      this.sorszam += 1; // a függő válasz elavul
      this.vezerlo?.abort();
      this.vezerlo = null;
      this.eredmeny = null;
      this.hiba = null;
      this.indexEpul = false;
      this.folyamat = false;
      return;
    }
    this.idozito = setTimeout(() => void this.keres(), azonnal ? 0 : KESLELTETES_MS);
  }

  async keres(): Promise<void> {
    const q = this.q.trim();
    if (Array.from(q).length < MIN_HOSSZ) return;
    const sorszam = ++this.sorszam;
    this.vezerlo?.abort(); // az elavult kérés megszakad (a kapcsolat is, nem csak a válasza dobódik el)
    const vezerlo = (this.vezerlo = new AbortController());
    this.folyamat = true;
    try {
      const ut = this.jelentes
        ? `/api/kereses/hibrid?q=${encodeURIComponent(q)}&limit=${KERESES_LIMIT}&mod=hibrid`
        : `/api/vault/kereses?q=${encodeURIComponent(q)}&limit=${KERESES_LIMIT}&kornyezet=1`;
      const v = await kerdez<KeresesValasz>(ut, { idokorlat: 15000, jel: vezerlo.signal });
      if (sorszam !== this.sorszam || q !== this.q.trim()) return;
      this.eredmeny = v;
      this.hiba = null;
      this.indexEpul = false;
      this.betoltes = this.jelentes && v.ok === 'modell_betoltes_alatt';
      if (this.betoltes) {
        // a core a háttérben a modellekkel lefuttatja ugyanezt; az ismételt kérés a kész hibrid választ kapja
        this.idozito = setTimeout(() => {
          if (sorszam === this.sorszam) void this.keres();
        }, BETOLTES_UJRA_MS);
      }
    } catch (e) {
      if (sorszam !== this.sorszam || q !== this.q.trim()) return;
      this.eredmeny = null;
      if (e instanceof ApiHiba && e.statusz === 503) {
        this.indexEpul = true;
        this.hiba = null;
      } else {
        this.indexEpul = false;
        this.hiba = e instanceof ApiHiba && e.statusz === 0 ? t('A core nem válaszol — a keresés most nem elérhető.') : e instanceof Error ? e.message : String(e);
      }
    } finally {
      if (sorszam === this.sorszam) {
        this.folyamat = false;
        this.vezerlo = null;
      }
    }
  }

  /** Az index elkészült: a függőben álló (503) keresés újrafut. */
  indexKesz(): void {
    if (this.indexEpul && this.q.trim()) void this.keres();
  }

  /** C25c: a PDF-ek szövegének indexelése a `pdf_szoveg` eseményből (a kezdő állapot a fájllista indexállapotából jön) —
   *  amíg nem kész, a panel kimondja (a fel nem dolgozott PDF csak név szerint kereshető). */
  pdfSzoveg = $state<PdfSzovegAllapot | null>(null);
}

export const vaultKereses = new VaultKereses();
