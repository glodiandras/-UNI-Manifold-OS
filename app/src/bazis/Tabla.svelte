<!--
  A Bases táblázata (C12): a core választ ablakozva rajzolja (fix sormagasság, csak a látható sorok és a tartalék
  kerülnek a DOM-ba, így a 2000 soros nézet is gyors). A fejléc és az összesítő sor ragad; a csoportfejléc az
  összesítővel együtt áll.
  C12b: a fejléc-kattintás rendez (⇧: több kulcs), az oszlop széle húzással és billentyűvel átméretezhető, a fejléc
  húzással átrendezhető, a menüje (⋯ vagy jobb gomb) az összesítőt, csoportosítást, elrejtést, átnevezést adja; a cella
  dupla kattintásra / ↩ / F2-re szerkeszthető (a jegyzet frontmatterébe, a nyitott dokumentumon át).
-->
<script lang="ts">
  import { onMount, tick } from 'svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { ArrowDown, ArrowUp, Ellipsis } from '../lib/ikon/ikonok';
  import { lebegoMenu, type MenuElem } from '../szerkeszto/notion/menu';
  import { ablak, sorMagassagPx } from './ablak';
  import Cella from './Cella.svelte';
  import { cellaErtesites, cellaIr, cellaOlvas, type CellaEredmeny } from './cellaIr';
  import CellaSzerkeszto from './CellaSzerkeszto.svelte';
  import { osszesitoSzoveg } from './ertek';
  import {
    csoportBeallit,
    OSSZESITOK,
    oszlopAzonok,
    oszlopMozgat,
    osszesitoBeallit,
    rendezesek,
    rendezesIrany,
    rendezesBeallit,
    rendezesValt,
    sorrendBeallit,
    szelessegBeallit,
    szelessegKorlat,
  } from './muveletek';
  import type { Csoport, Muvelet, Oszlop, Sor, Valasz } from './tipusok';

  interface Props {
    valasz: Valasz;
    /** `ez`: a nézetet tartalmazó fájl (a link-cellák ebből nyitnak) */
    ez?: string | null;
    magassag?: number | null;
    /** a nézet beállításai írhatók (a `.base` nem csak olvasható) */
    irhato?: boolean;
    /** a cellák szerkeszthetők (nem az Olvasó) */
    cellaIras?: boolean;
    muvelet?: (m: Muvelet) => void;
    /** az oszlop átnevezése (a megjelenített név): a `megjelenites_beallit` */
    atnevez?: (azon: string, nev: string | null) => void;
  }
  let { valasz, ez = null, magassag = null, irhato = false, cellaIras = false, muvelet, atnevez }: Props = $props();

  type Elem = { k: 'csoport'; cs: Csoport; i: number } | { k: 'sor'; sor: Sor; i: number };

  const nezetIndex = $derived(valasz.nezet?.index ?? 0);
  const sorM = $derived(sorMagassagPx(valasz.nezet?.beallitas?.rowHeight));
  const elemek = $derived.by((): Elem[] => {
    const ki: Elem[] = [];
    if (valasz.csoportok) {
      for (const [ci, cs] of valasz.csoportok.entries()) {
        ki.push({ k: 'csoport', cs, i: ci });
        for (let i = cs.tol; i < cs.tol + cs.db; i++) ki.push({ k: 'sor', sor: valasz.sorok[i], i });
      }
    } else for (const [i, sor] of valasz.sorok.entries()) ki.push({ k: 'sor', sor, i });
    return ki;
  });

  let gorgeto: HTMLDivElement | undefined = $state();
  let gorgetes = $state(0);
  let latoMagassag = $state(0);
  const a = $derived(ablak(gorgetes, latoMagassag || 600, sorM, elemek.length));
  const latszo = $derived(elemek.slice(a.elso, a.utolso));

  function alapSzelesseg(o: Oszlop): number {
    if (o.id === 'file.name') return 260;
    switch (o.tipus) {
      case 'number':
      case 'checkbox':
        return 110;
      case 'date':
      case 'datetime':
        return 150;
      case 'tags':
      case 'multitext':
      case 'aliases':
        return 220;
      default:
        return 180;
    }
  }

  /** húzás közben az oszlop ideiglenes szélessége (a mentés az elengedéskor) */
  let huzottSzel = $state<{ azon: string; px: number } | null>(null);
  const szelessegek = $derived(
    valasz.oszlopok.map((o) => (huzottSzel?.azon === o.id ? huzottSzel.px : (o.szelesseg ?? alapSzelesseg(o)))),
  );
  const sablon = $derived(szelessegek.map((w) => `${w}px`).join(' '));
  const teljesSzelesseg = $derived(szelessegek.reduce((s, w) => s + w, 0));
  const vanOsszesito = $derived(Object.keys(valasz.osszesitok).length > 0);
  /** a legutóbbi kattintás rendezése, amíg az új válasz meg nem érkezik (a gyors második kattintás ebből számol) */
  let helyiRendezes = $state.raw<ReturnType<typeof rendezesek> | null>(null);
  $effect(() => {
    void valasz;
    helyiRendezes = null;
  });
  const rendezes = $derived(helyiRendezes ?? rendezesek(valasz));

  onMount(() => {
    if (!gorgeto) return;
    latoMagassag = gorgeto.clientHeight;
    if (typeof ResizeObserver === 'undefined') return;
    const o = new ResizeObserver(() => {
      if (gorgeto) latoMagassag = gorgeto.clientHeight;
    });
    o.observe(gorgeto);
    return () => o.disconnect();
  });

  // ------------------------------------------------------------------ rendezés

  function fejlecKattint(e: MouseEvent, o: Oszlop) {
    if (!irhato || !muvelet) return;
    const uj = rendezesValt(rendezes, o.id, e.shiftKey);
    helyiRendezes = uj;
    muvelet(rendezesBeallit(nezetIndex, uj));
  }

  function rendezesJel(azon: string): { irany: 'ASC' | 'DESC'; sorszam: number | null } | null {
    const i = rendezes.findIndex((r) => r.property === azon);
    return i < 0 ? null : { irany: rendezes[i].direction, sorszam: rendezes.length > 1 ? i + 1 : null };
  }

  // ------------------------------------------------------------------ átméretezés

  let meretez: { azon: string; x0: number; px0: number } | null = null;

  function meretLe(e: PointerEvent, o: Oszlop, px: number) {
    if (e.button !== 0 || !irhato) return;
    e.preventDefault();
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    meretez = { azon: o.id, x0: e.clientX, px0: px };
    huzottSzel = { azon: o.id, px };
  }

  function meretMozog(e: PointerEvent) {
    if (!meretez) return;
    huzottSzel = { azon: meretez.azon, px: szelessegKorlat(meretez.px0 + e.clientX - meretez.x0) };
  }

  function meretFel() {
    if (!meretez) return;
    const v = huzottSzel;
    meretez = null;
    if (v && v.px !== valasz.oszlopok.find((o) => o.id === v.azon)?.szelesseg) muvelet?.(szelessegBeallit(nezetIndex, v.azon, v.px));
    // a mentett érték a válasszal érkezik; addig a húzott szélesség marad (nincs villanás)
    setTimeout(() => (huzottSzel = null), 400);
  }

  function meretBillentyu(e: KeyboardEvent, o: Oszlop, px: number) {
    if (!irhato) return;
    const lepes = e.shiftKey ? 48 : 16;
    let uj = px;
    if (e.key === 'ArrowRight') uj = px + lepes;
    else if (e.key === 'ArrowLeft') uj = px - lepes;
    else if (e.key === 'Home') uj = 60;
    else return;
    e.preventDefault();
    huzottSzel = { azon: o.id, px: szelessegKorlat(uj) };
    muvelet?.(szelessegBeallit(nezetIndex, o.id, uj));
    setTimeout(() => (huzottSzel = null), 400);
  }

  // ------------------------------------------------------------------ oszlop-átrendezés húzással

  let huzottOszlop = $state<string | null>(null);
  let celOszlop = $state<number | null>(null);

  function oszlopHuzasKezd(e: DragEvent, o: Oszlop) {
    if (!irhato) return e.preventDefault();
    huzottOszlop = o.id;
    e.dataTransfer?.setData('text/plain', o.id);
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
  }

  function oszlopFolott(e: DragEvent, i: number) {
    if (!huzottOszlop) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    celOszlop = e.clientX < r.left + r.width / 2 ? i : i + 1;
  }

  function oszlopEjt(e: DragEvent) {
    e.preventDefault();
    const azon = huzottOszlop;
    const cel = celOszlop;
    oszlopHuzasVege();
    if (!azon || cel === null) return;
    const azonok = oszlopAzonok(valasz);
    const regi = azonok.indexOf(azon);
    const uj = oszlopMozgat(azonok, azon, cel > regi ? cel - 1 : cel);
    if (uj.join('\n') !== azonok.join('\n')) muvelet?.(sorrendBeallit(nezetIndex, uj));
  }

  function oszlopHuzasVege() {
    huzottOszlop = null;
    celOszlop = null;
  }

  // ------------------------------------------------------------------ fejléc-menü

  function oszlopMenu(x: number, y: number, o: Oszlop, i: number, fokusz: () => void) {
    if (!irhato || !muvelet) return;
    const elemek: MenuElem[] = [];
    const akciok = new Map<string, () => void>();
    const hozzaad = (id: string, nev: string, fn: () => void, extra: Partial<MenuElem> = {}) => {
      elemek.push({ id, nev, ...extra });
      akciok.set(id, fn);
    };
    const jel = rendezesJel(o.id);
    hozzaad('novekvo', 'Rendezés növekvő', () => muvelet(rendezesIrany(nezetIndex, o.id, 'ASC')), { kijelolt: jel?.irany === 'ASC' });
    hozzaad('csokkeno', 'Rendezés csökkenő', () => muvelet(rendezesIrany(nezetIndex, o.id, 'DESC')), { kijelolt: jel?.irany === 'DESC' });
    if (jel) hozzaad('rendezes-torol', 'Rendezés törlése', () => muvelet(rendezesBeallit(nezetIndex, rendezes.filter((r) => r.property !== o.id))));
    const cs = valasz.nezet?.beallitas?.groupBy as { property?: string } | undefined;
    if (cs?.property === o.id) hozzaad('csoport-ki', 'Csoportosítás megszüntetése', () => muvelet(csoportBeallit(nezetIndex, null)));
    else hozzaad('csoport', 'Csoportosítás ezzel', () => muvelet(csoportBeallit(nezetIndex, o.id)));
    const aktualis = valasz.osszesitok[o.id]?.nev ?? null;
    const egyedi = valasz.fajl?.osszesitok ?? [];
    hozzaad('osszesito', 'Összesítő', () => {}, {
      almenu: () => [
        { id: 'o-nincs', nev: 'Nincs', kijelolt: aktualis === null },
        ...OSSZESITOK.map((s) => ({ id: `o-${s.nev}`, nev: s.felirat, jelzo: s.nev, kijelolt: aktualis === s.nev })),
        ...egyedi.map((n) => ({ id: `o-${n}`, nev: n, kijelolt: aktualis === n })),
      ],
    });
    for (const s of [...OSSZESITOK.map((x) => x.nev), ...egyedi]) akciok.set(`o-${s}`, () => muvelet(osszesitoBeallit(nezetIndex, o.id, s)));
    akciok.set('o-nincs', () => muvelet(osszesitoBeallit(nezetIndex, o.id, null)));
    hozzaad('atnevez', 'Átnevezés…', () => atnevezKezd(o));
    const azonok = oszlopAzonok(valasz);
    if (i > 0) hozzaad('balra', 'Mozgatás balra', () => muvelet(sorrendBeallit(nezetIndex, oszlopMozgat(azonok, o.id, i - 1))));
    if (i < azonok.length - 1) hozzaad('jobbra', 'Mozgatás jobbra', () => muvelet(sorrendBeallit(nezetIndex, oszlopMozgat(azonok, o.id, i + 1))));
    hozzaad('elrejt', 'Oszlop elrejtése', () => muvelet(sorrendBeallit(nezetIndex, azonok.filter((a) => a !== o.id))), { veszely: false });
    lebegoMenu({ focus: fokusz }, x, y, elemek, akciok, `${o.nev} oszlop`);
  }

  function menuGomb(e: MouseEvent, o: Oszlop, i: number) {
    e.preventDefault();
    e.stopPropagation();
    const el = e.currentTarget as HTMLElement;
    const r = el.getBoundingClientRect();
    oszlopMenu(e.type === 'contextmenu' ? e.clientX : r.left, e.type === 'contextmenu' ? e.clientY : r.bottom + 2, o, i, () => el.focus());
  }

  // ------------------------------------------------------------------ oszlop átnevezése (a megjelenített név)

  let atnevezett = $state<{ azon: string; nev: string } | null>(null);

  function atnevezKezd(o: Oszlop) {
    atnevezett = { azon: o.id, nev: o.nev };
    void tick().then(() => gorgeto?.querySelector<HTMLInputElement>('input.atnevezo')?.select());
  }

  function atnevezKesz(ment: boolean) {
    const v = atnevezett;
    atnevezett = null;
    if (!v || !ment) return;
    const o = valasz.oszlopok.find((x) => x.id === v.azon);
    const nev = v.nev.trim();
    if (!o || nev === o.nev) return;
    atnevez?.(v.azon, nev === '' ? null : nev);
  }

  // ------------------------------------------------------------------ cellák: kijelölés, szerkesztés

  const keyOf = (ut: string, azon: string) => `${ut}\u0000${azon}`;
  /** a roving-tabindex aktív cellája: [sor-elem indexe az `elemek`-ben, oszlop-index] */
  let aktiv = $state<{ sor: number; oszlop: number } | null>(null);
  let szerk = $state<string | null>(null);
  /** az ablak első sor-eleme (ha az aktív cella nincs az ablakban, ez a billentyűzet belépési pontja) */
  const elsoLatszoSor = $derived(elemek.findIndex((x, i) => i >= a.elso && i < a.utolso && x.k === 'sor'));
  const aktivLatszik = $derived(aktiv !== null && aktiv.sor >= a.elso && aktiv.sor < a.utolso);

  function szerkesztheto(o: Oszlop, sor: Sor): boolean {
    return cellaIras && o.szerkesztheto && sor.md;
  }

  function szerkesztKezd(sor: Sor, o: Oszlop) {
    if (!szerkesztheto(o, sor)) return;
    if (o.tipus === 'checkbox') return void jeloloValt(sor, o);
    szerk = keyOf(sor.ut, o.id);
  }

  function kulcsNev(o: Oszlop): string {
    return o.id.replace(/^note\./, '');
  }

  async function jeloloValt(sor: Sor, o: Oszlop) {
    const kulcs = kulcsNev(o);
    const mostani = (await cellaOlvas(sor.ut, kulcs).catch(() => null)) ?? null;
    const r = await cellaIr(sor.ut, mostani?.kulcs ?? kulcs, !(mostani?.ertek === true || mostani?.ertek === 'true'), 'checkbox');
    kesz(r, sor, mostani?.kulcs ?? kulcs);
  }

  function kesz(r: CellaEredmeny, sor: Sor, kulcs: string) {
    szerk = null;
    if (r.ok) {
      cellaErtesites(sor.nev, kulcs, r.pillanat);
    }
    void tick().then(() => gorgeto?.querySelector<HTMLElement>('[data-aktiv="true"]')?.focus());
  }

  function cellaFokusz(sorElem: number, oszlop: number) {
    aktiv = { sor: sorElem, oszlop };
  }

  async function cellaBillentyu(e: KeyboardEvent, sor: Sor, o: Oszlop, ei: number, oi: number) {
    if (szerk !== null) return;
    let uj: { sor: number; oszlop: number } | null = null;
    const utolsoOszlop = valasz.oszlopok.length - 1;
    const kovSor = (d: number): number | null => {
      for (let i = ei + d; i >= 0 && i < elemek.length; i += d) if (elemek[i].k === 'sor') return i;
      return null;
    };
    switch (e.key) {
      case 'ArrowLeft':
        if (oi > 0) uj = { sor: ei, oszlop: oi - 1 };
        break;
      case 'ArrowRight':
        if (oi < utolsoOszlop) uj = { sor: ei, oszlop: oi + 1 };
        break;
      case 'ArrowUp': {
        const s = kovSor(-1);
        if (s !== null) uj = { sor: s, oszlop: oi };
        break;
      }
      case 'ArrowDown': {
        const s = kovSor(1);
        if (s !== null) uj = { sor: s, oszlop: oi };
        break;
      }
      case 'Enter':
      case 'F2':
        if (szerkesztheto(o, sor)) {
          e.preventDefault();
          szerkesztKezd(sor, o);
        }
        return;
      case ' ':
        if (o.tipus === 'checkbox' && szerkesztheto(o, sor)) {
          e.preventDefault();
          szerkesztKezd(sor, o);
        }
        return;
      default:
        return;
    }
    e.preventDefault();
    if (!uj) return;
    aktiv = uj;
    // a cél sor az ablakban legyen (a görgetés az ablakozást is hozza)
    if (gorgeto) {
      const fent = uj.sor * sorM;
      if (fent < gorgeto.scrollTop + 30) gorgeto.scrollTop = Math.max(0, fent - 30);
      else if (fent + sorM > gorgeto.scrollTop + gorgeto.clientHeight - 30) gorgeto.scrollTop = fent + sorM - gorgeto.clientHeight + 30;
    }
    await tick();
    gorgeto?.querySelector<HTMLElement>('[data-aktiv="true"]')?.focus();
  }
</script>

<div
  class="gorgeto"
  bind:this={gorgeto}
  onscroll={(e) => (gorgetes = e.currentTarget.scrollTop)}
  style:max-height={magassag ? `${magassag}px` : null}
  role="table"
  aria-label="Adatbázis-nézet"
  aria-rowcount={elemek.length + 1}
  tabindex="-1"
>
  <div class="szeles" style:min-width="{teljesSzelesseg}px">
    <div class="fejlec" role="row" style:grid-template-columns={sablon}>
      {#each valasz.oszlopok as o, i (o.id)}
        {@const jel = rendezesJel(o.id)}
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
          class="fejlec-cella"
          class:cel-elott={celOszlop === i && huzottOszlop !== null}
          class:cel-utan={celOszlop === i + 1 && i === valasz.oszlopok.length - 1 && huzottOszlop !== null}
          class:huzott={huzottOszlop === o.id}
          role="columnheader"
          tabindex="-1"
          aria-sort={jel ? (jel.irany === 'ASC' ? 'ascending' : 'descending') : 'none'}
          title={o.id}
          draggable={irhato && atnevezett?.azon !== o.id}
          ondragstart={(e) => oszlopHuzasKezd(e, o)}
          ondragover={(e) => oszlopFolott(e, i)}
          ondrop={oszlopEjt}
          ondragend={oszlopHuzasVege}
          oncontextmenu={(e) => menuGomb(e, o, i)}
        >
          {#if atnevezett?.azon === o.id}
            <input
              class="atnevezo"
              type="text"
              aria-label="{o.nev} új neve"
              bind:value={atnevezett.nev}
              onkeydown={(e) => {
                if (e.key === 'Enter') atnevezKesz(true);
                else if (e.key === 'Escape') atnevezKesz(false);
                e.stopPropagation();
              }}
              onblur={() => atnevezKesz(true)}
            />
          {:else}
            <button type="button" class="fejlec-gomb" disabled={!irhato} onclick={(e) => fejlecKattint(e, o)} title="{o.id} — kattintás: rendezés, ⇧: több kulcs">
              <span class="fejlec-nev">{o.nev}</span>
              {#if jel}
                <span class="irany" aria-hidden="true">
                  <Ikon ikon={jel.irany === 'ASC' ? ArrowUp : ArrowDown} meret={14} />{#if jel.sorszam}<sup>{jel.sorszam}</sup>{/if}
                </span>
              {/if}
            </button>
            {#if irhato}
              <button type="button" class="fejlec-menu" aria-label="{o.nev} oszlop menü" onclick={(e) => menuGomb(e, o, i)}>
                <Ikon ikon={Ellipsis} meret={14} />
              </button>
            {/if}
          {/if}
          {#if irhato}
            <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
            <div
              class="atmeret"
              role="separator"
              aria-orientation="vertical"
              aria-label="{o.nev} oszlop szélessége"
              aria-valuenow={szelessegek[i]}
              aria-valuemin={60}
              aria-valuemax={900}
              tabindex="0"
              draggable="false"
              onpointerdown={(e) => meretLe(e, o, szelessegek[i])}
              onpointermove={meretMozog}
              onpointerup={meretFel}
              onpointercancel={meretFel}
              onkeydown={(e) => meretBillentyu(e, o, szelessegek[i])}
            ></div>
          {/if}
        </div>
      {/each}
    </div>
    <div class="torzs">
      <div style:height="{a.fent}px" aria-hidden="true"></div>
      {#each latszo as e, n (e.k === 'sor' ? `s${e.sor.ut}` : `c${e.i}`)}
        {#if e.k === 'csoport'}
          <div class="csoport" role="row" aria-rowindex={a.elso + n + 2} style:grid-template-columns={sablon} style:height="{sorM}px">
            {#each valasz.oszlopok as o, ci (o.id)}
              <div class="cella csoport-cella" role="cell">
                {#if ci === 0}
                  <strong class="csoport-cim">{e.cs.cimke || 'Nincs érték'}</strong>
                  <span class="csoport-db">{e.cs.db}</span>
                {/if}
                {#if e.cs.osszesitok[o.id]}
                  <span class="osszesito" title={e.cs.osszesitok[o.id].nev}>
                    <span class="osszesito-nev">{e.cs.osszesitok[o.id].nev}</span>
                    {osszesitoSzoveg(e.cs.osszesitok[o.id].ertek)}
                  </span>
                {/if}
              </div>
            {/each}
          </div>
        {:else}
          {@const ei = a.elso + n}
          <div class="sor" role="row" aria-rowindex={ei + 2} style:grid-template-columns={sablon} style:height="{sorM}px">
            {#each valasz.oszlopok as o, ci (o.id)}
              {@const ir = szerkesztheto(o, e.sor)}
              {@const ak = aktiv?.sor === ei && aktiv?.oszlop === ci}
              <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_static_element_interactions -->
              <div
                class="cella"
                class:irhato={ir}
                class:szerkesztes={szerk === keyOf(e.sor.ut, o.id)}
                role="cell"
                tabindex={ak || (!aktivLatszik && ei === elsoLatszoSor && ci === 0) ? 0 : -1}
                data-aktiv={ak ? 'true' : undefined}
                onfocus={() => cellaFokusz(ei, ci)}
                onclick={() => cellaFokusz(ei, ci)}
                ondblclick={() => szerkesztKezd(e.sor, o)}
                onkeydown={(ev) => cellaBillentyu(ev, e.sor, o, ei, ci)}
              >
                {#if szerk === keyOf(e.sor.ut, o.id)}
                  <CellaSzerkeszto
                    ut={e.sor.ut}
                    kulcs={kulcsNev(o)}
                    oszlopTipus={o.tipus}
                    kesz={(r, k) => kesz(r, e.sor, k)}
                    megse={() => {
                      szerk = null;
                      void tick().then(() => gorgeto?.querySelector<HTMLElement>('[data-aktiv="true"]')?.focus());
                    }}
                  />
                {:else if ir && o.tipus === 'checkbox'}
                  <button type="button" class="jelolo-gomb" aria-label="{o.nev} váltása" onclick={() => szerkesztKezd(e.sor, o)}>
                    <Cella ertek={e.sor.cellak[ci] ?? null} forras={e.sor.ut} {ez} />
                  </button>
                {:else}
                  <Cella ertek={e.sor.cellak[ci] ?? null} forras={e.sor.ut} {ez} />
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      {/each}
      <div style:height="{a.lent}px" aria-hidden="true"></div>
    </div>
    {#if elemek.length === 0}
      <p class="ures" role="status">Nincs a feltételeknek megfelelő fájl.</p>
    {/if}
    {#if vanOsszesito}
      <div class="lablec" role="row" style:grid-template-columns={sablon}>
        {#each valasz.oszlopok as o (o.id)}
          <div class="cella lablec-cella" role="cell">
            {#if valasz.osszesitok[o.id]}
              <span class="osszesito" title={valasz.osszesitok[o.id].nev}>
                <span class="osszesito-nev">{valasz.osszesitok[o.id].nev}</span>
                {osszesitoSzoveg(valasz.osszesitok[o.id].ertek)}
              </span>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  .gorgeto {
    flex: 1;
    min-height: 0;
    overflow: auto;
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg);
    outline: none;
  }

  .szeles {
    width: max-content;
  }

  .fejlec,
  .sor,
  .csoport,
  .lablec {
    display: grid;
  }

  .fejlec {
    position: sticky;
    top: 0;
    z-index: 2;
    height: 30px;
    background: var(--hatter);
    border-bottom: var(--keret-vastag) solid var(--keret-eros);
  }

  .fejlec-cella {
    position: relative;
    display: flex;
    align-items: center;
    min-width: 0;
    border-right: var(--keret-vastag) solid var(--keret);
    color: var(--szoveg-halvany);
    font-weight: var(--suly-kozepes);
  }

  .fejlec-cella.huzott {
    opacity: var(--atlatszosag-felig);
  }

  .fejlec-cella.cel-elott {
    box-shadow: inset var(--jel-vastag) 0 0 var(--akcent);
  }

  .fejlec-cella.cel-utan {
    box-shadow: inset calc(-1 * var(--jel-vastag)) 0 0 var(--akcent);
  }

  .fejlec-gomb {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: var(--t-1);
    height: 100%;
    padding: 0 var(--t-2);
    border: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .fejlec-gomb:disabled {
    cursor: default;
  }

  .fejlec-gomb:not(:disabled):hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .fejlec-nev {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .irany {
    flex: none;
    display: inline-flex;
    align-items: center;
    color: var(--akcent-szoveg);
  }

  .irany sup {
    font-size: 0.75em;
    line-height: 1;
  }

  .fejlec-menu {
    flex: none;
    display: grid;
    place-items: center;
    width: var(--magassag-suru);
    height: var(--magassag-suru);
    margin-right: 4px;
    border: 0;
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    color: inherit;
    cursor: pointer;
    opacity: 0;
  }

  .fejlec-cella:hover .fejlec-menu,
  .fejlec-menu:focus-visible {
    opacity: 1;
  }

  .fejlec-menu:hover {
    background: var(--hatter-aktiv);
  }

  .atmeret {
    position: absolute;
    top: 0;
    right: -3px;
    bottom: 0;
    width: 7px;
    cursor: col-resize;
    touch-action: none;
    z-index: 1;
  }

  .atmeret:hover,
  .atmeret:focus-visible {
    background: var(--akcent);
    opacity: var(--atlatszosag-felig);
    outline: none;
  }

  .atnevezo {
    flex: 1;
    min-width: 0;
    height: var(--magassag-suru);
    margin: 0 var(--t-1);
    padding: 0 var(--t-1);
    border: 1px solid var(--akcent);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
    outline: none;
  }

  .sor,
  .csoport {
    box-sizing: border-box;
    border-bottom: var(--keret-vastag) solid var(--keret);
  }

  .sor:hover {
    background: var(--hatter-hover);
  }

  .cella {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--t-2);
    min-width: 0;
    padding: 0 var(--t-2);
    overflow: hidden;
    border-right: var(--keret-vastag) solid var(--keret);
    outline: none;
  }

  .cella.szerkesztes {
    overflow: visible;
    padding: 0 2px;
  }

  .cella:focus-visible {
    box-shadow: inset 0 0 0 var(--fokusz-vastag) var(--fokusz-gyuru);
  }

  .jelolo-gomb {
    display: inline-flex;
    padding: 0;
    border: 0;
    background: transparent;
    cursor: pointer;
  }

  .csoport {
    background: var(--hatter-oldalsav);
  }

  .csoport-cim {
    font-weight: var(--suly-felkover);
  }

  .csoport-db {
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  .osszesito {
    color: var(--szoveg-masodlagos);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .osszesito-nev {
    margin-right: var(--t-1);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .lablec {
    position: sticky;
    bottom: 0;
    z-index: 2;
    height: 30px;
    background: var(--hatter-oldalsav);
    border-top: var(--keret-vastag) solid var(--keret-eros);
  }

  .ures {
    margin: var(--t-5) var(--t-4);
    color: var(--szoveg-halvany);
  }
</style>
