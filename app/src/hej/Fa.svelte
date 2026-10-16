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
  import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { ChevronDown, ChevronRight, ChevronsDownUp, FilePlus, Folder, FolderOpen } from '../lib/ikon/ikonok';
  import JegyzetIkon from '../lib/ui/JegyzetIkon.svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import { keresoMegnyit } from '../lib/kereses/kereso';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import { athelyezheto, faEpit, lapit, type FaCsomopont } from '../lib/vault/fa';
  import { lebegoMenu, type MenuElem } from '../szerkeszto/notion/menu';
  import { mediaUt } from '../osszefoglalas/allando';
  import { osszefoglalasFajlbol, osszefoglalasMappabol, tartalmiJegyzet } from '../osszefoglalas/parancsok';
  import { nyitasMod } from '../szerkeszto/linkek/navigacio';
  import { ujJegyzetSablonbol } from '../ma/naplo';
  import { ujJegyzetSablonbolHiv } from '../ma/sablonUj';
  import type { SemaProblema } from '../szerkeszto/tulajdonsagok/tipusok';
  import { beallitasok } from '../lib/beallitasok/allapot.svelte';

  const { felulet, fajlok } = kornyezet();

  const gyoker = $derived(faEpit(fajlok.lista, fajlok.mappak));
  const nyitott = $derived(new Set(felulet.oldalsav.nyitott));
  const sorok = $derived(lapit(gyoker, nyitott));

  let fokuszUt = $state<string | null>(null);
  const tabUt = $derived(sorok.some((s) => s.cs.ut === fokuszUt) ? fokuszUt : (sorok[0]?.cs.ut ?? null));
  const aktivUt = $derived(felulet.munkaterulet.aktivFul?.ut ?? null);

  let fa: HTMLElement | undefined = $state();

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
    untrack(() => (felulet.faUjJegyzet = false));
    void tick().then(() => ujJegyzetNyit());
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

  function billentyu(e: KeyboardEvent) {
    const sor = (e.target as HTMLElement).closest<HTMLElement>('[data-fa-ut]');
    if (!sor || (e.target as HTMLElement).tagName === 'INPUT' || e.isComposing) return;
    const i = sorok.findIndex((s) => s.cs.ut === sor.dataset.faUt);
    if (i < 0) return;
    const cs = sorok[i].cs;
    const k = e.key;
    let kesz = true;
    if (k === 'ArrowDown') void fokuszra(sorok[Math.min(sorok.length - 1, i + 1)].cs.ut);
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
      felulet.munkaterulet.megnyit(d.ut, 'aktiv');
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

  function atnevez(cs: FaCsomopont, mod: 'nev' | 'hely', cel?: string) {
    felulet.atnevezes = { ut: cs.ut, mod, mappa: cs.mappa, ...(cel !== undefined ? { cel } : {}) };
    felulet.atfedes = 'atnevezes';
  }

  function menu(cs: FaCsomopont, x: number, y: number) {
    const elemek: MenuElem[] = [];
    const akciok = new Map<string, () => void>();
    const hozzaad = (id: string, nev: string, fn: () => void, jelzo?: string) => {
      elemek.push({ id, nev, jelzo });
      akciok.set(id, fn);
    };
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
      if (tartalmiJegyzet(cs.ut) || mediaUt(cs.ut)) hozzaad('osszefoglalas', mediaUt(cs.ut) ? t('Összefoglalás az átiratból') : t('Összefoglalás|menu'), () => void osszefoglalasFajlbol(cs.ut));
    }
    hozzaad('nev', cs.mappa ? t('Mappa átnevezése…') : t('Átnevezés…'), () => atnevez(cs, 'nev'), 'F2');
    hozzaad('kuka', t('Áthelyezés a Kukába…'), () => { torlendo = cs.ut; torlesHiba = ''; });
    hozzaad('hely', cs.mappa ? t('Mappa áthelyezése…') : t('Áthelyezés…'), () => atnevez(cs, 'hely'));
    lebegoMenu({ focus: () => sorElem(cs.ut)?.focus() }, x, y, elemek, akciok, t('Fájlfa menü'));
  }

  function sorMenu(e: MouseEvent, cs: FaCsomopont) {
    e.preventDefault();
    fokuszUt = cs.ut;
    menu(cs, e.clientX, e.clientY);
  }

  // ------------------------------------------------------------------ húzás

  let huzott = $state<FaCsomopont | null>(null);
  /** a célmappa (a gyökér: ''), amelyre az egér mutat és ahova a húzott elem mehet; különben null */
  let celUt = $state<string | null>(null);
  let nyitoIdozito: ReturnType<typeof setTimeout> | null = null;

  function celMappaEsemenybol(e: DragEvent): string | null {
    if (!huzott && !e.dataTransfer?.types.includes('Files')) return null;
    const sor = (e.target as HTMLElement).closest<HTMLElement>('[data-fa-ut]');
    const cel = sor ? (sor.dataset.faMappa === 'true' ? sor.dataset.faUt! : szuloUt(sor.dataset.faUt!)) : '';
    return !huzott || athelyezheto(huzott.ut, huzott.mappa, cel) ? cel : null;
  }

  function huzasKezd(e: DragEvent, cs: FaCsomopont) {
    huzott = cs;
    e.dataTransfer?.setData('text/plain', cs.ut);
    if (!cs.mappa) e.dataTransfer?.setData(VAULT_HUZAS, cs.ut);
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
    celUt = null;
    if (nyitoIdozito) clearTimeout(nyitoIdozito);
    nyitoIdozito = null;
  }

  function ejtes(e: DragEvent) {
    const cel = celMappaEsemenybol(e);
    const cs = huzott;
    const kulso = Array.from(e.dataTransfer?.files ?? []);
    huzasVege();
    if (cel !== null && kulso.length) {
      e.preventDefault();
      void importal(kulso, cel);
      return;
    }
    if (cel === null || !cs) return;
    e.preventDefault();
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
  let torlendo = $state<string | null>(null);
  let torlesHiba = $state('');
  let torlesFut = $state(false);
  async function kukaba() {
    const ut = torlendo;
    if (!ut || torlesFut) return;
    torlesFut = true;
    try {
      await szerkesztok.dokumentumok.mindLezar();
      await kerdez('/api/vault/kuka', { metodus: 'POST', torzs: { ut, megerosit: true }, idokorlat: 60000 });
      await fajlok.frissit();
      torlendo = null;
    } catch (e) { torlesHiba = e instanceof Error ? e.message : String(e); }
    finally { torlesFut = false; }
  }

  onDestroy(() => nyitoIdozito && clearTimeout(nyitoIdozito));

  function osszecsuk() {
    felulet.oldalsav.nyitott = [];
  }

  const tipusNev = (cs: FaCsomopont) => (cs.mappa ? `${tp('{n} jegyzet', cs.jegyzetek)} · ${tp('{n} fájl', cs.fajlok)}` : cs.ut);
</script>

<div class="fa-doboz">
  {#if torlendo}
    <Atfedes cimke={t('Áthelyezés a Kukába')} nev="kuka" onbezar={() => { if (!torlesFut) torlendo = null; }}>
      <div class="kuka-kerdes">
        <h2>{t('Áthelyezés a Kukába')}</h2>
        <p>{torlendo}</p>
        <p>{t('A fájl vagy mappa a macOS Kukájából visszahozható. A rá mutató hivatkozások megmaradnak.')}</p>
        {#if torlesHiba}<p role="alert">{torlesHiba}</p>{/if}
        <button class="m-gomb semleges" disabled={torlesFut} onclick={() => torlendo = null}>{t('Mégse')}</button>
        <button class="m-gomb" disabled={torlesFut} onclick={() => void kukaba()}>{t('Áthelyezés a Kukába')}</button>
      </div>
    </Atfedes>
  {/if}
  <div class="eszkoztar">
    <span class="felirat" aria-hidden="true" data-csend-rejt>{tp('{n} fájl', gyoker.fajlok)}</span>
    <IkonGomb ikon={FilePlus} cimke={t('Új jegyzet')} kicsi data-csend-rejt onclick={() => ujJegyzetNyit()} />
    <IkonGomb ikon={Folder} cimke={t('Új mappa')} kicsi data-csend-rejt onclick={() => ujJegyzetNyit(celMappa(), 'mappa')} />
    <IkonGomb ikon={ChevronsDownUp} cimke={t('Összes mappa összecsukása')} kicsi data-csend-rejt onclick={osszecsuk} />
  </div>

  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fa gorgeto"
    class:gyoker-cel={celUt === ''}
    role="tree"
    tabindex="-1"
    aria-label={t('Fájlok')}
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
        role="treeitem"
        tabindex={tabUt === cs.ut ? 0 : -1}
        data-regio-fokusz={tabUt === cs.ut ? '' : undefined}
        data-fa-ut={cs.ut}
        data-fa-mappa={cs.mappa}
        aria-level={s.melyseg + 1}
        aria-posinset={s.hely}
        aria-setsize={s.testverek}
        aria-expanded={cs.mappa ? nyitott.has(cs.ut) : undefined}
        aria-selected={!cs.mappa && cs.ut === aktivUt}
        title={tipusNev(cs)}
        style:padding-left={`${8 + s.melyseg * 16}px`}
        draggable="true"
        onclick={(e) => aktival(cs, e)}
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
        <span class="nev">{cs.nev}</span>
        {#if cs.mappa && cs.fajlok}<span class="db">{cs.fajlok}</span>{/if}
      </div>
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
