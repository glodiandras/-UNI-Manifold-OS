<!--
  A fájlfa (C11a): mappák elöl, magyar ábécérenddel, számlálókkal; új jegyzet (soron belüli névmező), átnevezés és
  áthelyezés (a C10 útján: terv-lista, egy pillanatkép, visszavonás), húzással is. ARIA `tree` (gördülő tabindex:
  ↑↓ lépés, → kinyit / belép, ← becsuk / szülőre lép, Home, End, ↩ megnyit, F2 átnevez, ⇧F10 helyi menü).
  A fa a core listáját mutatja (`/api/vault/fa`): a felület nem old fel linket és nem olvas fájlrendszert.
  A húzás sosem ír közvetlenül: az ejtés a terv-átfedést nyitja, a megerősítés után megy a core-hoz.
-->
<script lang="ts">
  import { t, tp, tk } from '../lib/i18n';
  import { onDestroy, tick, untrack } from 'svelte';
  import { ApiHiba, kerdez } from '../lib/core/api';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import { fajlImport, VAULT_HUZAS } from '../szerkeszto/csatolmany';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { ArrowUpDown, ChevronDown, ChevronRight, ChevronsDownUp, CircleAlert, FilePlus, Folder, FolderOpen, ListTree } from '../lib/ikon/ikonok';
  import JegyzetIkon from '../lib/ui/JegyzetIkon.svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import { keresoMegnyit } from '../lib/kereses/kereso';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import { athelyezettUt, athelyezheto, faEpit, faIdoMezo, kijelolesTartomany, lapit, lathatoFajlok, legfelsoUtak, mappakatKinyit, osMappak, type FaCsomopont, type FaRendezes } from '../lib/vault/fa';
  import { finderMegmutat, kukabaTesz, masolatKeszit } from '../lib/vault/faMuveletek';
  import { atnevezesErtesites, atnevezesTerv, atnevezesVegrehajt, type Terv } from '../szerkeszto/linkek/atnevezes';
  import { lebegoMenu, type MenuElem } from '../szerkeszto/notion/menu';
  import { mediaUt } from '../osszefoglalas/allando';
  import { osszefoglalasFajlbol, osszefoglalasMappabol, tartalmiJegyzet } from '../osszefoglalas/parancsok';
  import { nyitasMod } from '../szerkeszto/linkek/navigacio';
  import { elonezetUtakra } from '../szerkeszto/linkek/elonezet';
  import { ujJegyzetSablonbol } from '../ma/naplo';
  import { ujJegyzetSablonbolHiv } from '../ma/sablonUj';
  import type { SemaProblema } from '../szerkeszto/tulajdonsagok/tipusok';
  import { MAX_NYITOTT_MAPPA } from '../lib/elrendezes/felulet.svelte';
  import { beallitasok } from '../lib/beallitasok/allapot.svelte';

  const { felulet, fajlok } = kornyezet();

  // 07-explorer-12: a nem támogatott kiterjesztések rejtve, ha sem a vault (`showUnsupportedFiles`), sem a felület beállítása nem kéri
  const mindenFajl = $derived(felulet.oldalsav.mindenFajl || fajlok.mindenKiterjesztes);
  const gyoker = $derived(faEpit(lathatoFajlok(fajlok.lista, mindenFajl), fajlok.mappak, felulet.oldalsav.rendezes));
  const nyitott = $derived(new Set(felulet.oldalsav.nyitott));
  const sorok = $derived(lapit(gyoker, nyitott));
  const vanNyitott = $derived(sorok.some(s => s.cs.mappa && nyitott.has(s.cs.ut)));
  const RENDEZES: { id: FaRendezes; nev: string }[] = [
    { id: 'nev', nev: tk('Fájlnév (A–Z)') },
    { id: 'nev-forditva', nev: tk('Fájlnév (Z–A)') },
    { id: 'modositva', nev: tk('Módosítás: legújabb elöl') },
    { id: 'modositva-regi', nev: tk('Módosítás: legrégebbi elöl') },
    { id: 'letrehozva', nev: tk('Létrehozás: legújabb elöl') },
    { id: 'letrehozva-regi', nev: tk('Létrehozás: legrégebbi elöl') },
  ];
  const rendezesCim = $derived(t('Rendezés: {mod}', { mod: t(RENDEZES.find(r => r.id === felulet.oldalsav.rendezes)?.nev ?? RENDEZES[0].nev) }));

  $effect(() => {
    if (faIdoMezo(felulet.oldalsav.rendezes)) return fajlok.idobelyegeketFigyel();
  });

  function rendezesMenu(e: MouseEvent) {
    const gomb = e.currentTarget as HTMLElement, r = gomb.getBoundingClientRect();
    const akciok = new Map(RENDEZES.map(m => [m.id, () => { felulet.oldalsav.rendezes = m.id; }]));
    lebegoMenu({ focus: () => gomb.focus() }, r.left, r.bottom,
      RENDEZES.map(m => ({ id: m.id, nev: t(m.nev), kijelolt: m.id === felulet.oldalsav.rendezes })), akciok, t('Fájlok rendezése'));
  }


  let fokuszUt = $state<string | null>(null);
  const tabUt = $derived(sorok.some((s) => s.cs.ut === fokuszUt) ? fokuszUt : (sorok[0]?.cs.ut ?? null));
  const aktivUt = $derived(felulet.munkaterulet.aktivFul?.ut ?? null);

  let fa: HTMLElement | undefined = $state();
  // 02-links-09: ⌘-hover előnézet a fájl-soron (a mappának nincs)
  $effect(() => (fa ? elonezetUtakra(fa, { valaszto: '[data-fa-ut]', ut: (e) => (e.dataset.faMappa === 'true' ? null : (e.dataset.faUt ?? null)) }) : undefined));

  // ------------------------------------------------------------------ nyitás, fókusz

  function valt(ut: string, nyit?: boolean) {
    const be = new Set(felulet.oldalsav.nyitott);
    const cel = nyit ?? !be.has(ut);
    if (cel) be.add(ut);
    else be.delete(ut);
    felulet.oldalsav.nyitott = [...be];
  }

  function sorElem(ut: string): HTMLElement | null {
    return fa ? ([...fa.querySelectorAll<HTMLElement>('[data-fa-ut]')].find((e) => e.dataset.faUt === ut) ?? null) : null;
  }

  async function fokuszra(ut: string) {
    fokuszUt = ut;
    await tick();
    const e = sorElem(ut);
    e?.focus();
    e?.scrollIntoView({ block: 'nearest' });
  }

  // „Megmutatás a fában”: az ősmappák már nyitottak (Felulet.megmutatFaban), a sor látható és fókuszált lesz
  $effect(() => {
    const k = felulet.faMegmutat;
    if (k) void tick().then(() => fokuszra(k.ut));
  });

  // „Új jegyzet a fájlfában” (C38, ⌘P): a fa eszköztára csendben rejtett, a parancs ugyanazt nyitja
  $effect(() => {
    if (!felulet.faUjJegyzet) return;
    const cel = untrack(() => {
      felulet.faUjJegyzet = false;
      const c = felulet.faUjNev;
      felulet.faUjNev = null;
      return c;
    });
    void atfedesVegere().then(async () => {
      await ujJegyzetNyit(cel?.mappa ?? alapMappa());
      if (cel && ujJegyzet) {
        ujJegyzet = { ...ujJegyzet, nev: cel.nev, mod: cel.mod };
        await ujJegyzetLetrehoz();
      }
    });
  });

  // „Új jegyzet sablonból” (C32b): a sablon-választó után a névmező nyílik, a létrehozás a `/api/sablon/uj` úton megy
  $effect(() => {
    const k = felulet.faUjSablon;
    if (!k) return;
    untrack(() => (felulet.faUjSablon = null));
    // a záró átfedés a fókuszt a megnyitóra viszi vissza: a névmező csak utána kaphatja meg, különben a blur azonnal lezárná
    void atfedesVegere().then(() => ujJegyzetNyit(k.mappa ?? celMappa(), 'md', k.sablon));
  });

  /** Megvárja, amíg az átfedés (a záró animációjával) eltűnik a DOM-ból; legfeljebb ~0,6 s. */
  async function atfedesVegere(): Promise<void> {
    await tick();
    for (let i = 0; i < 36 && document.querySelector('.fatyol'); i++) await new Promise((r) => setTimeout(r, 20));
  }

  function aktival(cs: FaCsomopont, e: MouseEvent | KeyboardEvent) {
    fokuszUt = cs.ut;
    if (cs.mappa) valt(cs.ut);
    else felulet.munkaterulet.megnyit(cs.ut, nyitasMod(e));
  }

  function szuloUt(ut: string): string {
    return ut.includes('/') ? ut.slice(0, ut.lastIndexOf('/')) : '';
  }

  // ------------------------------------------------------------------ többes kijelölés (07-explorer-04)

  let kijelolt = $state<string[]>([]);
  let horgony = $state<string | null>(null);
  const kijeloltSet = $derived(new Set(kijelolt));
  const mappaE = (ut: string) => sorok.find((s) => s.cs.ut === ut)?.cs.mappa ?? fajlok.mappak.includes(ut);
  /** A tömeges művelet tárgya: a kijelölés legfelső elemei (mappa + részfája együtt csak a mappa). */
  const celUtak = (cs: FaCsomopont) => (kijeloltSet.has(cs.ut) && kijelolt.length > 1 ? legfelsoUtak(kijelolt) : [cs.ut]);

  /** Kattintás a sorra: Shift = tartomány a horgonytól, ⌘/⌃ = hozzáad / elvesz (nem nyit), egyszerű = a kijelölés megszűnik és nyit. */
  function sorKattint(cs: FaCsomopont, e: MouseEvent) {
    if (e.shiftKey && !e.metaKey && !e.ctrlKey) {
      fokuszUt = cs.ut;
      kijelolt = kijelolesTartomany(sorok, horgony ?? fokuszUt, cs.ut);
      horgony ??= cs.ut;
      return;
    }
    if ((e.metaKey || e.ctrlKey) && !e.altKey) {
      fokuszUt = cs.ut;
      kijelolt = kijeloltSet.has(cs.ut) ? kijelolt.filter((u) => u !== cs.ut) : [...kijelolt, cs.ut];
      horgony = cs.ut;
      return;
    }
    kijelolt = [];
    horgony = cs.ut;
    aktival(cs, e);
  }

  // az eltűnt (törölt, átnevezett) elemek kikerülnek a kijelölésből
  $effect(() => {
    const van = new Set(sorok.map((s) => s.cs.ut));
    const marad = untrack(() => kijelolt).filter((u) => van.has(u));
    if (marad.length !== untrack(() => kijelolt).length) kijelolt = marad;
  });

  function billentyu(e: KeyboardEvent) {
    const sor = (e.target as HTMLElement).closest<HTMLElement>('[data-fa-ut]');
    if (!sor || (e.target as HTMLElement).tagName === 'INPUT' || e.isComposing) return;
    const i = sorok.findIndex((s) => s.cs.ut === sor.dataset.faUt);
    if (i < 0) return;
    const cs = sorok[i].cs;
    const k = e.key;
    let kesz = true;
    if ((k === 'ArrowDown' || k === 'ArrowUp') && e.shiftKey) {
      // Shift+nyíl: a kijelölés a horgonytól a fókuszig terjed
      const j = k === 'ArrowDown' ? Math.min(sorok.length - 1, i + 1) : Math.max(0, i - 1);
      horgony ??= cs.ut;
      kijelolt = kijelolesTartomany(sorok, horgony, sorok[j].cs.ut);
      void fokuszra(sorok[j].cs.ut);
    } else if (k === 'F2') atnevezesInditas(cs);
    else if (k === 'Delete' || (k === 'Backspace' && e.metaKey)) kukaKerdes(celUtak(cs));
    else if (k === 'Escape' && kijelolt.length) kijelolt = [];
    else if (k === 'ArrowDown') void fokuszra(sorok[Math.min(sorok.length - 1, i + 1)].cs.ut);
    else if (k === 'ArrowUp') void fokuszra(sorok[Math.max(0, i - 1)].cs.ut);
    else if (k === 'Home') void fokuszra(sorok[0].cs.ut);
    else if (k === 'End') void fokuszra(sorok[sorok.length - 1].cs.ut);
    else if (k === 'ArrowRight') {
      if (cs.mappa && !nyitott.has(cs.ut)) valt(cs.ut, true);
      else if (cs.mappa && cs.gyerekek.length) void fokuszra(sorok[i + 1].cs.ut);
    } else if (k === 'ArrowLeft') {
      if (cs.mappa && nyitott.has(cs.ut)) valt(cs.ut, false);
      else {
        const szulo = szuloUt(cs.ut);
        if (szulo) void fokuszra(szulo);
      }
    } else if (k === 'Enter' || k === ' ') aktival(cs, e);
    else if (k === 'ContextMenu' || (k === 'F10' && e.shiftKey)) {
      const r = sor.getBoundingClientRect();
      menu(cs, r.left + 24, r.bottom);
    } else kesz = false;
    if (kesz) e.preventDefault();
  }

  // ------------------------------------------------------------------ új jegyzet

  // `problemak`: a sablon frontmatterjének séma-sértései (Javító 7); `megerosit`: megerősítéssel létrehozható („Mégis létrehozom”)
  let ujJegyzet = $state<{
    mappa: string;
    nev: string;
    hiba: string | null;
    folyamat: boolean;
    tipus: UjTipus;
    mod?: 'aktiv' | 'ujful' | 'osztas';
    sablon?: string;
    problemak?: SemaProblema[];
    megerosit?: boolean;
  } | null>(null);
  let ujMezo: HTMLInputElement | undefined = $state();
  /** Az új fájl fajtája: jegyzet, adatbázis-nézet (C12), canvas (C14); a felirat és a kiterjesztés. */
  type UjTipus = 'md' | 'base' | 'canvas' | 'mappa';
  const UJ_NEV_ARIA: Record<UjTipus, string> = { md: tk('Az új jegyzet neve'), base: tk('Az új adatbázis-nézet neve'), canvas: tk('Az új canvas neve'), mappa: tk('Az új mappa neve') };
  const UJ_NEV_HELYORZO: Record<UjTipus, string> = { md: tk('Új jegyzet neve'), base: tk('Új adatbázis-nézet neve'), canvas: tk('Új canvas neve'), mappa: tk('Új mappa neve') };

  /** A fókuszált sor mappája (mappa: önmaga; fájl: a szülője), vagy a gyökér. */
  function celMappa(): string {
    const cs = sorok.find((s) => s.cs.ut === fokuszUt)?.cs;
    return cs ? (cs.mappa ? cs.ut : szuloUt(cs.ut)) : '';
  }

  function alapMappa(): string {
    if (!beallitasok.adat) return celMappa();
    const m = beallitasok.ertek.fajlok.uj_mappa;
    return m === '.' ? szuloUt(aktivUt ?? '') : m;
  }

  async function ujJegyzetNyit(mappa = alapMappa(), tipus: UjTipus = 'md', sablon?: string) {
    for (let p = mappa; p; p = szuloUt(p)) valt(p, true);
    ujJegyzet = { mappa, nev: '', hiba: null, folyamat: false, tipus, ...(sablon ? { sablon } : {}) };
    await tick();
    ujMezo?.focus();
  }

  async function ujJegyzetLetrehoz(megerosit = false) {
    const u = ujJegyzet;
    if (!u || u.folyamat) return;
    const nev = u.nev.trim().replace(new RegExp(`\\.${u.tipus}$`, 'i'), '');
    if (!nev) {
      ujJegyzet = null;
      return;
    }
    ujJegyzet = { ...u, folyamat: true, hiba: null, problemak: [], megerosit: false };
    try {
      let d: { ut: string; kurzor?: number | null };
      if (u.tipus === 'mappa') {
        d = await kerdez('/api/vault/mappa', { metodus: 'POST', torzs: { mappa: u.mappa, nev } });
      } else if (u.sablon) {
        // séma-sértő sablon-frontmatter: a core nem hozza létre, a sértések látszanak, és csak a „Mégis létrehozom” után megy újra
        const e = await ujJegyzetSablonbolHiv(u.mappa, nev, u.sablon, megerosit);
        if (e.allapot !== 'kesz') {
          ujJegyzet = { ...u, folyamat: false, hiba: e.uzenet, problemak: e.problemak, megerosit: e.allapot === 'megerosit' };
          await tick();
          ujMezo?.focus();
          return;
        }
        d = e.valasz;
      } else {
        d = await kerdez<{ ut: string; kurzor?: number | null }>('/api/vault/uj', { metodus: 'POST', torzs: { mappa: u.mappa, nev, ...(u.mappa && !fajlok.mappak.includes(u.mappa) ? { mappa_keszit: true } : {}), ...(u.tipus !== 'md' ? { tipus: u.tipus } : {}) }, idokorlat: 10000 });
      }
      ujJegyzet = null;
      if (u.tipus === 'mappa') { await fajlok.frissit(); valt(d.ut, true); fokuszUt = d.ut; return; }
      felulet.munkaterulet.megnyit(d.ut, u.mod ?? 'aktiv');
      const ful = felulet.munkaterulet.aktivFul;
      if (d.kurzor != null && ful && ful.ut === d.ut && !ful.nezet) ful.nezet = { kurzor: d.kurzor };
      felulet.megmutatFaban(d.ut);
    } catch (e) {
      ujJegyzet = { ...u, folyamat: false, hiba: e instanceof ApiHiba ? e.message : String(e) };
      await tick();
      ujMezo?.focus();
    }
  }

  function ujBillentyu(e: KeyboardEvent) {
    if (e.isComposing) return;
    if (e.key === 'Enter') {
      e.preventDefault();
      void ujJegyzetLetrehoz();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      const hely = ujJegyzet?.mappa;
      ujJegyzet = null;
      void fokuszra(hely ?? sorok[0]?.cs.ut ?? '');
    }
  }

  // ------------------------------------------------------------------ átnevezés, áthelyezés, helyi menü

  function atnevez(cs: FaCsomopont, mod: 'nev' | 'hely', cel?: string, nev?: string) {
    felulet.atnevezes = { ut: cs.ut, mod, mappa: cs.mappa, ...(cel !== undefined ? { cel } : {}), ...(nev !== undefined ? { nev } : {}) };
    felulet.atfedes = 'atnevezes';
  }

  // ---- soron belüli átnevezés (07-explorer-03): ↩ terv; ha nincs link-változás, azonnal megy (Visszavonás értesítéssel),
  //      különben a terv-átfedés nyílik az új névvel; Esc és a fókusz elhagyása elvet. A név sosem ír terv nélkül.
  let atnevezesSor = $state<{ ut: string; mappa: boolean; nev: string; hiba: string | null; folyamat: boolean } | null>(null);
  let atnevezesMezo: HTMLInputElement | undefined = $state();

  async function atnevezesInditas(cs: FaCsomopont) {
    kijelolt = [];
    atnevezesSor = { ut: cs.ut, mappa: cs.mappa, nev: cs.nev, hiba: null, folyamat: false };
    await tick();
    atnevezesMezo?.focus();
    atnevezesMezo?.select();
  }

  /** A mezőbe írt névből az új út: a fájl kiterjesztése megmarad (a jegyzeté rejtett), mint az átfedésben. */
  function ujAtnevezettUt(ut: string, mappa: boolean, nev: string): string {
    const kit = mappa ? '' : (/\.[^./]+$/.exec(ut)?.[0] ?? '');
    let n = nev.trim();
    if (kit && n.toLowerCase().endsWith(kit.toLowerCase())) n = n.slice(0, -kit.length).trimEnd();
    const szulo = szuloUt(ut);
    return `${szulo ? szulo + '/' : ''}${n}${kit}`;
  }

  function atnevezesBezar(fokusz = true) {
    const ut = atnevezesSor?.ut;
    atnevezesSor = null;
    if (fokusz && ut) void fokuszra(ut);
  }

  async function atnevezesVeglegesit() {
    const sor = atnevezesSor;
    if (!sor || sor.folyamat) return;
    if (!sor.nev.trim()) return atnevezesBezar();
    const uj = ujAtnevezettUt(sor.ut, sor.mappa, sor.nev);
    if (uj === sor.ut) return atnevezesBezar();
    atnevezesSor = { ...sor, folyamat: true, hiba: null };
    try {
      const terv = await atnevezesTerv(sor.ut, uj);
      if (!terv.ok || terv.blokkolok.length) {
        atnevezesSor = { ...sor, folyamat: false, hiba: terv.blokkolok.join(' ') || t('Az átnevezés nem lehetséges.') };
        await tick();
        atnevezesMezo?.focus();
        return;
      }
      if (terv.fajlok.length === 0 && !terv.figyelmeztetesek?.length) {
        const r = await atnevezesVegrehajt(terv.regi, terv.uj, terv.terv_hash);
        atnevezesSor = null;
        atnevezesErtesites(r, felulet);
        return;
      }
      // link-változás vagy átnézendő kifejezés: a terv látszik, a megerősítés a meglévő átfedésben történik
      atnevezesSor = null;
      felulet.atnevezes = { ut: sor.ut, mod: 'nev', mappa: sor.mappa, nev: sor.nev };
      felulet.atfedes = 'atnevezes';
    } catch (e) {
      atnevezesSor = { ...sor, folyamat: false, hiba: e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e) };
      await tick();
      atnevezesMezo?.focus();
    }
  }

  function atnevezesBillentyu(e: KeyboardEvent) {
    if (e.isComposing) return;
    if (e.key === 'Enter') {
      e.preventDefault();
      e.stopPropagation();
      void atnevezesVeglegesit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      atnevezesBezar();
    }
  }

  // az F2 (a regiszter-parancsból) és a közvetlen kérés a fa során
  $effect(() => {
    const k = felulet.faAtnevezKer;
    if (!k) return;
    untrack(() => {
      const cs = sorok.find((s) => s.cs.ut === k.ut)?.cs;
      if (cs) void atnevezesInditas(cs);
    });
  });

  // „Összes mappa kinyitása” a ⌘P-ből
  let utolsoKinyit = 0;
  $effect(() => {
    const n = felulet.faKinyitKer;
    if (n === utolsoKinyit) return;
    utolsoKinyit = n;
    untrack(() => kinyitMind());
  });

  function kinyitMind() {
    const nyitas = mappakatKinyit(gyoker, felulet.oldalsav.nyitott, MAX_NYITOTT_MAPPA);
    felulet.oldalsav.nyitott = nyitas.utak;
    if (nyitas.kimaradt) ertesitesek.ertesit({ szint: 'info', cim: t('A mappák egy része kinyílt'), szoveg: t('Legfeljebb {n} mappa marad nyitva egyszerre. A többit külön nyithatod ki.', { n: MAX_NYITOTT_MAPPA }), idotartam: 6000 });
  }

  // az aktív fájl automatikus követése (07-explorer-11): az ősmappák kinyílnak, a sor látható lesz — a fókuszt nem veszi el
  $effect(() => {
    if (!felulet.oldalsav.autoMegmutat) return;
    const ut = aktivUt;
    if (!ut) return;
    untrack(() => {
      const nyitva = new Set(felulet.oldalsav.nyitott);
      const hianyzo = osMappak(ut).filter((m) => !nyitva.has(m));
      if (hianyzo.length) felulet.oldalsav.nyitott = [...felulet.oldalsav.nyitott, ...hianyzo];
      void tick().then(() => sorElem(ut)?.scrollIntoView?.({ block: 'nearest' }));
    });
  });

  function menu(cs: FaCsomopont, x: number, y: number) {
    const elemek: MenuElem[] = [];
    const akciok = new Map<string, () => void>();
    const hozzaad = (id: string, nev: string, fn: () => void, jelzo?: string) => {
      elemek.push({ id, nev, jelzo });
      akciok.set(id, fn);
    };
    const utak = celUtak(cs);
    if (utak.length > 1) {
      // tömeges menü (07-explorer-04): csak a biztonságos, megerősített műveletek
      hozzaad('tomeg-hely', t('Áthelyezés ({n} elem)…', { n: utak.length }), () => tomegesAthelyezesNyit(utak, null));
      hozzaad('tomeg-kuka', t('Áthelyezés a Kukába ({n} elem)…', { n: utak.length }), () => kukaKerdes(utak));
      lebegoMenu({ focus: () => sorElem(cs.ut)?.focus() }, x, y, elemek, akciok, t('Fájlfa menü'));
      return;
    }
    if (cs.mappa) {
      hozzaad('uj-mappa', t('Új mappa itt'), () => void ujJegyzetNyit(cs.ut, 'mappa'));
      hozzaad('uj', t('Új jegyzet itt'), () => void ujJegyzetNyit(cs.ut));
      hozzaad('uj-sablon', t('Új jegyzet sablonból…'), () => ujJegyzetSablonbol(felulet, cs.ut));
      hozzaad('uj-base', t('Új adatbázis-nézet itt'), () => void ujJegyzetNyit(cs.ut, 'base'));
      hozzaad('uj-canvas', t('Új canvas itt'), () => void ujJegyzetNyit(cs.ut, 'canvas'));
      hozzaad('ossz-mappa', t('Összefoglalás a mappából|menu'), () => void osszefoglalasMappabol(cs.ut));
      hozzaad('kereses', t('Keresés ebben a mappában'), () => {
        keresoMegnyit(felulet, `path:"${cs.ut}/" `);
      });
    } else {
      hozzaad('megnyit', t('Megnyitás'), () => felulet.munkaterulet.megnyit(cs.ut, 'aktiv'));
      hozzaad('ujful', t('Megnyitás új fülben'), () => felulet.munkaterulet.megnyit(cs.ut, 'ujful'));
      hozzaad('osztas', t('Megnyitás osztásban'), () => felulet.munkaterulet.megnyit(cs.ut, 'osztas'));
      hozzaad('masolat', t('Másolat készítése'), () => void masolatKeszit(felulet, cs.ut, fajlok));
      if (tartalmiJegyzet(cs.ut) || mediaUt(cs.ut)) hozzaad('osszefoglalas', mediaUt(cs.ut) ? t('Összefoglalás az átiratból') : t('Összefoglalás|menu'), () => void osszefoglalasFajlbol(cs.ut));
    }
    hozzaad('nev', cs.mappa ? t('Mappa átnevezése…') : t('Átnevezés…'), () => void atnevezesInditas(cs), 'F2');
    hozzaad('kuka', t('Áthelyezés a Kukába…'), () => kukaKerdes([cs.ut]));
    hozzaad('hely', cs.mappa ? t('Mappa áthelyezése…') : t('Áthelyezés…'), () => atnevez(cs, 'hely'));
    hozzaad('finder', t('Megmutatás a Finderben'), () => void finderMegmutat(cs.ut));
    lebegoMenu({ focus: () => sorElem(cs.ut)?.focus() }, x, y, elemek, akciok, t('Fájlfa menü'));
  }

  function sorMenu(e: MouseEvent, cs: FaCsomopont) {
    e.preventDefault();
    e.stopPropagation();
    fokuszUt = cs.ut;
    if (!kijeloltSet.has(cs.ut)) kijelolt = []; // jobb klikk a kijelölésen kívül: egyetlen elem menüje
    menu(cs, e.clientX, e.clientY);
  }

  /** Jobb klikk az üres területen (07-explorer-19): a gyökér menüje és a fa beállításai. */
  function gyokerMenu(e: MouseEvent) {
    if ((e.target as HTMLElement).closest('[data-fa-ut]')) return;
    e.preventDefault();
    const elemek: MenuElem[] = [], akciok = new Map<string, () => void>();
    const hozzaad = (id: string, nev: string, fn: () => void, kijeloltE?: boolean) => { elemek.push({ id, nev, ...(kijeloltE !== undefined ? { kijelolt: kijeloltE } : {}) }); akciok.set(id, fn); };
    hozzaad('uj', t('Új jegyzet'), () => void ujJegyzetNyit(''));
    hozzaad('uj-mappa', t('Új mappa'), () => void ujJegyzetNyit('', 'mappa'));
    hozzaad('minden', t('Minden fájltípus mutatása'), () => { felulet.oldalsav.mindenFajl = !felulet.oldalsav.mindenFajl; }, mindenFajl);
    hozzaad('auto', t('Az aktív fájl automatikus megmutatása'), () => { felulet.oldalsav.autoMegmutat = !felulet.oldalsav.autoMegmutat; }, felulet.oldalsav.autoMegmutat);
    lebegoMenu({ focus: () => fa?.focus() }, e.clientX, e.clientY, elemek, akciok, t('Fájlfa menü'));
  }

  // ------------------------------------------------------------------ húzás

  let huzott = $state<FaCsomopont | null>(null);
  /** a húzott elemek: a kijelölés legfelső elemei, ha a húzott sor a kijelölés tagja (07-explorer-04), különben csak ő */
  let huzottUtak = $state<string[]>([]);
  /** a célmappa (a gyökér: ''), amelyre az egér mutat és ahova a húzott elem mehet; különben null */
  let celUt = $state<string | null>(null);
  let nyitoIdozito: ReturnType<typeof setTimeout> | null = null;

  const mozgathatoUtak = (cel: string) => huzottUtak.filter((u) => athelyezheto(u, mappaE(u), cel));

  function celMappaEsemenybol(e: DragEvent): string | null {
    if (!huzott && !e.dataTransfer?.types.includes('Files')) return null;
    const sor = (e.target as HTMLElement).closest<HTMLElement>('[data-fa-ut]');
    const cel = sor ? (sor.dataset.faMappa === 'true' ? sor.dataset.faUt! : szuloUt(sor.dataset.faUt!)) : '';
    return !huzott || mozgathatoUtak(cel).length ? cel : null;
  }

  function huzasKezd(e: DragEvent, cs: FaCsomopont) {
    huzott = cs;
    huzottUtak = celUtak(cs);
    e.dataTransfer?.setData('text/plain', huzottUtak.join('\n'));
    if (!cs.mappa && huzottUtak.length === 1) e.dataTransfer?.setData(VAULT_HUZAS, cs.ut);
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copyMove';
  }

  function huzasFolott(e: DragEvent) {
    const cel = celMappaEsemenybol(e);
    if (cel === null) {
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'none';
      celUt = null;
      return;
    }
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    if (cel !== celUt) {
      celUt = cel;
      if (nyitoIdozito) clearTimeout(nyitoIdozito);
      nyitoIdozito = cel && !nyitott.has(cel) ? setTimeout(() => valt(cel, true), 700) : null; // a zárt mappa kinyílik
    }
  }

  function huzasVege() {
    huzott = null;
    huzottUtak = [];
    celUt = null;
    if (nyitoIdozito) clearTimeout(nyitoIdozito);
    nyitoIdozito = null;
  }

  function ejtes(e: DragEvent) {
    const cel = celMappaEsemenybol(e);
    const cs = huzott;
    const utak = cel === null ? [] : mozgathatoUtak(cel);
    const kulso = Array.from(e.dataTransfer?.files ?? []);
    huzasVege();
    if (cel !== null && kulso.length) {
      e.preventDefault();
      void importal(kulso, cel);
      return;
    }
    if (cel === null || !cs) return;
    e.preventDefault();
    if (utak.length > 1) tomegesAthelyezesNyit(utak, cel); // tömeges áthelyezés: mindig megerősítéssel
    else void azonnaliAthelyezes(cs, cel);
  }

  let athelyezesFolyik = false;
  /** Húzásos áthelyezés (07-explorer-15): a core terve előbb; ha nincs link-változás és figyelmeztetés, azonnal megy
   *  (a „Visszavonás” értesítés megmarad), különben — vagy bármilyen hibánál — a terv-átfedés nyílik, mint eddig. */
  async function azonnaliAthelyezes(cs: FaCsomopont, cel: string) {
    if (athelyezesFolyik) return;
    athelyezesFolyik = true;
    try {
      const terv = await atnevezesTerv(cs.ut, athelyezettUt(cs.ut, cel));
      if (terv.ok && !terv.blokkolok.length && terv.fajlok.length === 0 && !terv.figyelmeztetesek?.length) {
        const r = await atnevezesVegrehajt(terv.regi, terv.uj, terv.terv_hash);
        atnevezesErtesites(r, felulet);
        return;
      }
    } catch {
      // a terv vagy a végrehajtás nem ment át: az átfedés újratervez és megmutatja az okot
    } finally {
      athelyezesFolyik = false;
    }
    atnevez(cs, 'hely', cel); // a terv-átfedés nyílik: megerősítés nélkül semmi nem ír
  }

  async function importal(lista: File[], mappa: string) {
    try {
      for (const f of lista) await fajlImport(f, { mappa });
      await fajlok.frissit();
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: t('A fájlimport megállt'), szoveg: e instanceof Error ? e.message : String(e) });
    }
  }

  // ------------------------------------------------------------------ Kuka (egy vagy több elem)

  let torlendo = $state<string[] | null>(null);
  let torlesHiba = $state('');
  let torlesFut = $state(false);
  function kukaKerdes(utak: string[]) {
    if (!utak.length) return;
    torlendo = utak;
    torlesHiba = '';
  }
  async function kukaba() {
    const utak = torlendo;
    if (!utak || torlesFut) return;
    torlesFut = true;
    const r = await kukabaTesz(utak);
    await fajlok.frissit();
    torlesFut = false;
    if (r.hiba) {
      // az első hibánál a sor megáll; ami már a Kukában van, az ott marad (visszahozható), a többi érintetlen
      torlendo = utak.filter((u) => !r.kesz.includes(u));
      kijelolt = kijelolt.filter((u) => !r.kesz.includes(u));
      torlesHiba = r.kesz.length ? t('{kesz} elem a Kukába került, a hátralévők nem: {hiba}', { kesz: r.kesz.length, hiba: r.hiba }) : r.hiba;
      return;
    }
    kijelolt = [];
    torlendo = null;
  }

  // ------------------------------------------------------------------ tömeges áthelyezés (07-explorer-04)

  let tomeges = $state<{ utak: string[]; cel: string | null; szuro: string; tervek: Terv[] | null; folyamat: 'terv' | 'vegrehajtas' | ''; hiba: string | null } | null>(null);
  const tomegesMappak = $derived.by(() => {
    if (!tomeges) return [];
    const q = tomeges.szuro.trim().toLowerCase();
    return ['', ...fajlok.mappak]
      .filter((m) => tomeges!.utak.some((u) => athelyezheto(u, mappaE(u), m)))
      .filter((m) => !q || m.toLowerCase().includes(q))
      .slice(0, 40);
  });

  function tomegesAthelyezesNyit(utak: string[], cel: string | null) {
    tomeges = { utak, cel, szuro: '', tervek: null, folyamat: '', hiba: null };
    if (cel !== null) void tomegesTerv(cel);
  }

  async function tomegesTerv(cel: string) {
    const t0 = tomeges;
    if (!t0) return;
    const mozgo = t0.utak.filter((u) => athelyezheto(u, mappaE(u), cel));
    tomeges = { ...t0, cel, folyamat: 'terv', hiba: null, tervek: null, utak: mozgo };
    try {
      const tervek: Terv[] = [];
      for (const u of mozgo) tervek.push(await atnevezesTerv(u, athelyezettUt(u, cel)));
      tomeges = tomeges && { ...tomeges, tervek, folyamat: '' };
    } catch (e) {
      tomeges = tomeges && { ...tomeges, folyamat: '', hiba: e instanceof Error ? e.message : String(e) };
    }
  }

  async function tomegesVegrehajt() {
    const m = tomeges;
    if (!m?.tervek || m.folyamat || m.tervek.some((x) => !x.ok)) return;
    tomeges = { ...m, folyamat: 'vegrehajtas', hiba: null };
    const kesz: { regi: string; uj: string }[] = [];
    try {
      for (const terv of m.tervek) {
        const r = await atnevezesVegrehajt(terv.regi, terv.uj, terv.terv_hash);
        kesz.push({ regi: r.regi, uj: r.uj });
        atnevezesErtesites(r, felulet);
      }
      kijelolt = [];
      tomeges = null;
    } catch (e) {
      // ami már átkerült, az a saját „Visszavonás” értesítésével elérhető; a hátralévők érintetlenek
      const hatra = m.tervek.filter((x) => !kesz.some((k) => k.regi === x.regi));
      tomeges = { ...m, folyamat: '', tervek: null, utak: hatra.map((x) => x.regi), hiba: (kesz.length ? t('{n} elem már átkerült, a hátralévők nem: ', { n: kesz.length }) : '') + (e instanceof Error ? e.message : String(e)) };
      if (m.cel !== null && hatra.length) void tomegesTerv(m.cel);
    }
  }

  onDestroy(() => nyitoIdozito && clearTimeout(nyitoIdozito));

  function mappakValt() {
    if (vanNyitott) { felulet.oldalsav.nyitott = []; return; }
    kinyitMind();
  }

  const tipusNev = (cs: FaCsomopont) => (cs.mappa ? `${tp('{n} jegyzet', cs.jegyzetek)} · ${tp('{n} fájl', cs.fajlok)}` : cs.ut);
</script>

<div class="fa-doboz">
  {#if torlendo}
    <Atfedes cimke={t('Áthelyezés a Kukába')} nev="kuka" onbezar={() => { if (!torlesFut) torlendo = null; }}>
      <div class="kuka-kerdes">
        <h2>{t('Áthelyezés a Kukába')}</h2>
        {#if torlendo.length === 1}
          <p>{torlendo[0]}</p>
        {:else}
          <p>{tp('{n} kijelölt elem', torlendo.length)}</p>
          <ul class="kuka-lista">
            {#each torlendo.slice(0, 8) as u (u)}<li>{u}</li>{/each}
            {#if torlendo.length > 8}<li>{t('… és még {n}', { n: torlendo.length - 8 })}</li>{/if}
          </ul>
        {/if}
        <p>{t('A fájl vagy mappa a macOS Kukájából visszahozható. A rá mutató hivatkozások megmaradnak.')}</p>
        {#if torlesHiba}<p role="alert" class="dialog-hiba"><Ikon ikon={CircleAlert} meret={14} /> {torlesHiba}</p>{/if}
        <button class="m-gomb semleges" disabled={torlesFut} onclick={() => torlendo = null}>{t('Mégse')}</button>
        <button class="m-gomb" disabled={torlesFut} onclick={() => void kukaba()}>{t('Áthelyezés a Kukába')}</button>
      </div>
    </Atfedes>
  {/if}
  {#if tomeges}
    <Atfedes cimke={t('Elemek áthelyezése')} nev="tomeges-athelyezes" onbezar={() => { if (!tomeges?.folyamat) tomeges = null; }}>
      <div class="kuka-kerdes tomeges">
        <h2>{t('Áthelyezés ({n} elem)…', { n: tomeges.utak.length })}</h2>
        {#if tomeges.cel === null || (!tomeges.tervek && !tomeges.folyamat)}
          <label class="tomeges-szuro">
            <span>{t('Célmappa')}</span>
            <input value={tomeges.szuro} oninput={(e) => { if (tomeges) tomeges.szuro = e.currentTarget.value; }} placeholder={t('Mappa keresése…')} spellcheck="false" autocomplete="off" />
          </label>
          <ul class="tomeges-mappak" aria-label={t('Mappák')}>
            {#each tomegesMappak as m (m)}
              <li><button type="button" onclick={() => void tomegesTerv(m)}>{m || t('(a vault gyökere)')}</button></li>
            {:else}
              <li class="ures">{t('Nincs ilyen mappa.')}</li>
            {/each}
          </ul>
        {:else}
          <p>→ <strong>{tomeges.cel || t('(a vault gyökere)')}</strong></p>
          {#if tomeges.folyamat === 'terv'}
            <p>{t('Tervezés…')}</p>
          {:else if tomeges.tervek}
            {@const blokkolt = tomeges.tervek.filter((x) => !x.ok)}
            {@const linkek = tomeges.tervek.reduce((n, x) => n + x.modositott_linkek, 0)}
            {@const fajlokDb = tomeges.tervek.reduce((n, x) => n + x.fajlok.length, 0)}
            <p aria-live="polite">
              {#if linkek}<strong>{t('{n} fájlban {db} link', { n: fajlokDb, db: linkek })}</strong> {t('módosul. Elemenként egy pillanatkép készül, mindegyik külön visszavonható.')}
              {:else}{t('Nincs link, amely átírást igényelne.')}{/if}
            </p>
            {#if blokkolt.length}
              <ul class="kuka-lista" role="alert">
                {#each blokkolt as b (b.regi)}<li><Ikon ikon={CircleAlert} meret={14} /> {b.regi}: {b.blokkolok.join(' ')}</li>{/each}
              </ul>
            {/if}
          {/if}
        {/if}
        {#if tomeges.hiba}<p role="alert" class="dialog-hiba"><Ikon ikon={CircleAlert} meret={14} /> {tomeges.hiba}</p>{/if}
        <button class="m-gomb semleges" disabled={tomeges.folyamat === 'vegrehajtas'} onclick={() => (tomeges = null)}>{t('Mégse')}</button>
        <button class="m-gomb" disabled={!tomeges.tervek || !!tomeges.folyamat || tomeges.tervek.some((x) => !x.ok)} onclick={() => void tomegesVegrehajt()}>
          {tomeges.folyamat === 'vegrehajtas' ? t('Áthelyezés…|folyamat') : t('Áthelyezés')}
        </button>
      </div>
    </Atfedes>
  {/if}
  <div class="eszkoztar">
    <span class="felirat" aria-hidden="true" data-csend-rejt>{tp('{n} fájl', gyoker.fajlok)}</span>
    <IkonGomb ikon={FilePlus} cimke={t('Új jegyzet')} kicsi data-csend-rejt onclick={() => ujJegyzetNyit()} />
    <IkonGomb ikon={Folder} cimke={t('Új mappa')} kicsi data-csend-rejt onclick={() => ujJegyzetNyit(celMappa(), 'mappa')} />
    <IkonGomb ikon={ArrowUpDown} cimke={rendezesCim} aria-haspopup="listbox" kicsi data-csend-rejt onclick={rendezesMenu} />
    <IkonGomb ikon={vanNyitott ? ChevronsDownUp : ListTree} cimke={vanNyitott ? t('Összes mappa összecsukása') : t('Összes mappa kinyitása')} kicsi data-csend-rejt onclick={mappakValt} />
  </div>

  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fa gorgeto"
    class:gyoker-cel={celUt === ''}
    role="tree"
    tabindex="-1"
    aria-multiselectable="true"
    aria-label={t('Fájlok')}
    oncontextmenu={gyokerMenu}
    bind:this={fa}
    onkeydown={billentyu}
    ondragover={huzasFolott}
    ondrop={ejtes}
    ondragend={huzasVege}
    ondragleave={(e) => {
      if (!fa?.contains(e.relatedTarget as Node | null)) celUt = null;
    }}
  >
    {#if ujJegyzet && (ujJegyzet.mappa === '' || !sorok.some(s => s.cs.mappa && s.cs.ut === ujJegyzet?.mappa))}
      {@render ujSor(0)}
    {/if}
    {#each sorok as s (s.cs.ut)}
      {@const cs = s.cs}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div
        class="sor"
        class:mappa={cs.mappa}
        class:aktiv={!cs.mappa && cs.ut === aktivUt}
        class:cel={cs.mappa && celUt === cs.ut}
        class:huzott={huzott?.ut === cs.ut}
        class:kijelolt={kijeloltSet.has(cs.ut)}
        class:kizart={!cs.mappa && fajlok.info(cs.ut)?.kizart === true}
        role="treeitem"
        tabindex={tabUt === cs.ut ? 0 : -1}
        data-regio-fokusz={tabUt === cs.ut ? '' : undefined}
        data-fa-ut={cs.ut}
        data-fa-mappa={cs.mappa}
        aria-level={s.melyseg + 1}
        aria-posinset={s.hely}
        aria-setsize={s.testverek}
        aria-expanded={cs.mappa ? nyitott.has(cs.ut) : undefined}
        aria-selected={(!cs.mappa && cs.ut === aktivUt) || kijeloltSet.has(cs.ut)}
        title={!cs.mappa && fajlok.info(cs.ut)?.kizart === true ? `${tipusNev(cs)} · ${t('beallitasok.kizart_fa')}` : tipusNev(cs)}
        style:padding-left={`${8 + s.melyseg * 16}px`}
        draggable={atnevezesSor?.ut === cs.ut ? 'false' : 'true'}
        onclick={(e) => sorKattint(cs, e)}
        onauxclick={(e) => { if (e.button === 1 && !cs.mappa) { e.preventDefault(); felulet.munkaterulet.megnyit(cs.ut, 'ujful'); } }}
        onfocus={() => (fokuszUt = cs.ut)}
        oncontextmenu={(e) => sorMenu(e, cs)}
        ondragstart={(e) => huzasKezd(e, cs)}
      >
        {#if cs.mappa}
          <span class="nyil"><Ikon ikon={nyitott.has(cs.ut) ? ChevronDown : ChevronRight} meret={14} /></span>
          <Ikon ikon={nyitott.has(cs.ut) ? FolderOpen : Folder} meret={16} />
        {:else}
          <span class="nyil"></span>
          <JegyzetIkon ut={cs.ut} tipus={cs.tipus} meret={16} />
        {/if}
        {#if atnevezesSor?.ut === cs.ut}
          <input
            bind:this={atnevezesMezo}
            class="uj-mezo"
            aria-label={cs.mappa ? t('A mappa új neve') : t('A fájl új neve')}
            spellcheck="false"
            autocomplete="off"
            disabled={atnevezesSor.folyamat}
            value={atnevezesSor.nev}
            oninput={(e) => { if (atnevezesSor) { atnevezesSor.nev = e.currentTarget.value; atnevezesSor.hiba = null; } }}
            onkeydown={atnevezesBillentyu}
            onclick={(e) => e.stopPropagation()}
            onblur={() => { if (atnevezesSor && !atnevezesSor.folyamat) atnevezesBezar(false); }}
          />
        {:else}
          <span class="nev">{cs.nev}</span>
        {/if}
        {#if cs.mappa && cs.fajlok}<span class="db">{cs.fajlok}</span>{/if}
      </div>
      {#if atnevezesSor?.ut === cs.ut && atnevezesSor.hiba}
        <p class="uj-hiba" role="alert" style:padding-left={`${8 + s.melyseg * 16 + 36}px`}><Ikon ikon={CircleAlert} meret={14} /> {atnevezesSor.hiba}</p>
      {/if}
      {#if ujJegyzet && ujJegyzet.mappa === cs.ut && cs.mappa && nyitott.has(cs.ut)}
        {@render ujSor(s.melyseg + 1)}
      {/if}
    {:else}
      <p class="ures">{fajlok.betoltve ? t('A vault üres.') : t('A fájllista töltődik…')}</p>
    {/each}
  </div>
</div>

{#snippet ujSor(melyseg: number)}
  <div class="sor uj" style:padding-left={`${8 + melyseg * 16}px`}>
    <span class="nyil"></span>
    <Ikon ikon={FilePlus} meret={16} />
    <input
      bind:this={ujMezo}
      class="uj-mezo"
      aria-label={t(UJ_NEV_ARIA[ujJegyzet?.tipus ?? 'md'])}
      placeholder={t(UJ_NEV_HELYORZO[ujJegyzet?.tipus ?? 'md'])}
      title={ujJegyzet?.mappa || '/'}
      spellcheck="false"
      autocomplete="off"
      disabled={ujJegyzet?.folyamat}
      value={ujJegyzet?.nev ?? ''}
      oninput={(e) => {
        if (ujJegyzet) {
          ujJegyzet.nev = e.currentTarget.value;
          if (ujJegyzet.megerosit) {
            // más név, más út: a megerősítés a korábbi sértéslistára szólt
            ujJegyzet.megerosit = false;
            ujJegyzet.problemak = [];
            ujJegyzet.hiba = null;
          }
        }
      }}
      onkeydown={ujBillentyu}
      onblur={() => {
        if (ujJegyzet && !ujJegyzet.folyamat && !ujJegyzet.hiba && !ujJegyzet.nev.trim()) ujJegyzet = null;
      }}
    />
  </div>
  {#if ujJegyzet?.hiba}
    <p class="uj-hiba" role="alert" style:padding-left={`${8 + melyseg * 16 + 36}px`}>{ujJegyzet.hiba}</p>
    {#if ujJegyzet.problemak?.length}
      <ul class="uj-sertesek" style:padding-left={`${8 + melyseg * 16 + 36 + 14}px`} aria-label={t('A sablon séma-sértései')}>
        {#each ujJegyzet.problemak as p, i (i)}
          <li class:hiba-szint={p.szint === 'hiba'}>{p.uzenet}</li>
        {/each}
      </ul>
    {/if}
    {#if ujJegyzet.megerosit}
      <div class="uj-megerosit" style:padding-left={`${8 + melyseg * 16 + 36}px`}>
        <button type="button" class="m-gomb semleges gomb" onclick={() => void ujJegyzetLetrehoz(true)}>{t('Mégis létrehozom')}</button>
      </div>
    {/if}
  {/if}
{/snippet}

<style>
  .fa-doboz {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }

  .eszkoztar {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--magassag-sor);
    padding: 0 var(--t-2) 0 var(--t-4);
  }

  .felirat {
    flex: 1;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  .fa {
    flex: 1;
    min-height: 0;
    padding: var(--t-1) var(--t-1) var(--t-3);
  }

  .fa.gyoker-cel {
    outline: var(--jel-vastag) solid var(--akcent);
    outline-offset: var(--fokusz-tav-befele);
    border-radius: var(--kerekites);
  }

  .sor {
    display: flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--magassag-sor);
    padding-right: var(--t-2);
    border-radius: var(--kerekites);
    color: var(--szoveg-masodlagos);
    cursor: default;
    user-select: none;
    -webkit-user-select: none;
  }

  .sor:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .sor:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav-befele);
  }

  .sor.mappa {
    color: var(--szoveg);
  }

  .sor.aktiv {
    background: var(--hatter-kijelolt);
    color: var(--szoveg);
  }

  .sor.cel {
    background: var(--hatter-kijelolt);
    outline: var(--jel-vastag) solid var(--akcent);
    outline-offset: var(--fokusz-tav-befele);
  }

  .sor.huzott {
    opacity: var(--atlatszosag-felig);
  }

  /* Excluded files (14-appearance-06): a fán halványan látszik (a fájl nem tűnik el), a keresésből, gráfból és gyorsváltóból kimarad */
  .sor.kizart .nev {
    opacity: var(--atlatszosag-felig);
  }

  .nyil {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 14px;
    color: var(--szoveg-halvany);
  }

  .nev {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .db {
    flex: none;
    font-size: var(--betu-kicsi);
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  .ures {
    margin: var(--t-2) var(--t-3);
    color: var(--szoveg-halvany);
  }

  .sor.kijelolt {
    background: var(--hatter-kijelolt);
  }

  .kuka-lista,
  .tomeges-mappak {
    margin: 0 0 var(--t-2);
    padding: 0;
    list-style: none;
    overflow-wrap: anywhere;
  }

  .tomeges-mappak {
    max-height: 16rem;
    overflow-y: auto;
    border: 1px solid var(--keret);
    border-radius: var(--kerekites);
  }

  .tomeges-mappak button {
    display: block;
    width: 100%;
    padding: var(--t-1) var(--t-3);
    text-align: left;
  }

  .tomeges-szuro {
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
  }

  .dialog-hiba {
    color: var(--hiba);
  }

  .uj-mezo {
    flex: 1;
    min-width: 0;
    height: var(--magassag-suru);
    padding: 0 var(--t-1);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter);
    color: var(--szoveg);
  }

  .uj-mezo:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: 0;
  }

  .uj-sertesek {
    margin: 0 var(--t-2) var(--t-1) 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
    overflow-wrap: anywhere;
  }

  .uj-sertesek .hiba-szint {
    color: var(--hiba);
  }

  .uj-megerosit {
    margin: 0 var(--t-2) var(--t-1) 0;
  }

  .uj-hiba {
    margin: 0 var(--t-2) var(--t-1) 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--hiba);
    overflow-wrap: anywhere;
  }
</style>
