<!--
  A Bases-nézet eszköztára (C12b): nézetfülek (átnevezés, típus, sorrend, törlés a menüjükben; „+” új nézet) és a
  panelek: Rendezés, Csoportok, Oszlopok, Szűrők és képletek, Nézet-beállítások, és a teljes YAML-forrás. A találatszám `title`-je a core és a
  rajz idejét mutatja. Csak írható `.base`-nél jelennek meg a szerkesztő elemek.
-->
<script lang="ts">
  import { t, tp } from '../lib/i18n';
  import { tick } from 'svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { ArrowDown, CodeXml, Columns3, Copy, Funnel, Plus, Rows2, SlidersHorizontal, TriangleAlert } from '../lib/ikon/ikonok';
  import { lebegoMenu, type MenuElem } from '../szerkeszto/notion/menu';
  import { vagolapra } from '../szerkeszto/vagolap';
  import BeallitasPanel from './BeallitasPanel.svelte';
  import CsoportPanel from './CsoportPanel.svelte';
  import { kimenetSzoveg, type Kimenet } from './csv';
  import type { BazisModell } from './modell.svelte';
  import OszlopPanel from './OszlopPanel.svelte';
  import Popover from './Popover.svelte';
  import RendezesPanel from './RendezesPanel.svelte';
  import SzuroPanel from './SzuroPanel.svelte';
  import UjJegyzet from './UjJegyzet.svelte';
  import { NEZET_TIPUSOK, TIPUS_FELIRAT } from './nevek';
  import { rendezesek } from './muveletek';
  import type { Valasz } from './tipusok';

  interface Props {
    modell: BazisModell;
    v: Valasz;
    irhato: boolean;
    cellaIras: boolean;
    idoSzoveg: string;
    nezetValtott?: (index: number) => void;
    forrasGomb?: () => void;
  }
  let { modell, v, irhato, cellaIras, idoSzoveg, nezetValtott, forrasGomb }: Props = $props();

  const aktiv = $derived(v.nezet?.index ?? 0);
  const szuroDb = $derived((v.fajl?.szuro.trim() ? 1 : 0) + (v.fajl?.szuro_nezet.trim() ? 1 : 0));
  const rendezesDb = $derived(rendezesek(v).length);

  function valt(i: number) {
    modell.nezetValt(i);
    nezetValtott?.(i);
  }

  async function muvelet(m: Parameters<BazisModell['alkalmaz']>[0], ujNezet?: number) {
    const r = await modell.alkalmaz(m, ujNezet);
    if (r.irva && ujNezet !== undefined) nezetValtott?.(ujNezet);
    return r;
  }

  // ------------------------------------------------------------------ új nézet

  function ujNezetMenu(e: MouseEvent) {
    const el = e.currentTarget as HTMLElement;
    const r = el.getBoundingClientRect();
    const elemek: MenuElem[] = NEZET_TIPUSOK.map((ty) => ({ id: ty, nev: t('Új nézet: {tipus}', { tipus: t(TIPUS_FELIRAT[ty]) }) }));
    const akciok = new Map<string, () => void>();
    for (const ty of NEZET_TIPUSOK)
      akciok.set(ty, () => void muvelet({ fajta: 'nezet_uj', tipus: ty }, v.nezetek.length));
    lebegoMenu({ focus: () => el.focus() }, r.left, r.bottom + 2, elemek, akciok, t('Új nézet'));
  }

  // ------------------------------------------------------------------ fül menü és átnevezés

  let atnevezett = $state<{ index: number; nev: string } | null>(null);

  function atnevezKezd(i: number) {
    atnevezett = { index: i, nev: v.nezetek[i].nev };
    void tick().then(() => document.querySelector<HTMLInputElement>('input.fulatnevezo')?.select());
  }

  function atnevezKesz(ment: boolean) {
    const a = atnevezett;
    atnevezett = null;
    if (!a || !ment) return;
    const nev = a.nev.trim();
    if (nev && nev !== v.nezetek[a.index].nev) void muvelet({ fajta: 'nezet_beallit', nezet: a.index, kulcs: 'name', ertek: nev });
  }

  function fulMenu(e: MouseEvent, i: number) {
    if (!irhato) return;
    e.preventDefault();
    const el = e.currentTarget as HTMLElement;
    const elemek: MenuElem[] = [];
    const akciok = new Map<string, () => void>();
    const hozzaad = (id: string, nev: string, fn: () => void, extra: Partial<MenuElem> = {}) => {
      elemek.push({ id, nev, ...extra });
      akciok.set(id, fn);
    };
    hozzaad('atnevez', t('Átnevezés…'), () => atnevezKezd(i));
    hozzaad('tipus', t('Típus'), () => {}, {
      almenu: () => NEZET_TIPUSOK.map((ty) => ({ id: `t-${ty}`, nev: t(TIPUS_FELIRAT[ty]), kijelolt: v.nezetek[i].tipus === ty })),
    });
    for (const ty of NEZET_TIPUSOK)
      akciok.set(`t-${ty}`, () => void muvelet({ fajta: 'nezet_beallit', nezet: i, kulcs: 'type', ertek: ty }));
    if (i > 0) hozzaad('balra', t('Mozgatás balra'), () => void muvelet({ fajta: 'nezet_mozgat', nezet: i, ujindex: i - 1 }, aktiv === i ? i - 1 : undefined));
    if (i < v.nezetek.length - 1)
      hozzaad('jobbra', t('Mozgatás jobbra'), () => void muvelet({ fajta: 'nezet_mozgat', nezet: i, ujindex: i + 1 }, aktiv === i ? i + 1 : undefined));
    if (v.nezetek.length > 1)
      hozzaad('torol', t('Nézet törlése'), () => void muvelet({ fajta: 'nezet_torol', nezet: i }, Math.min(aktiv > i ? aktiv - 1 : aktiv === i ? Math.max(0, i - 1) : aktiv, v.nezetek.length - 2)), { veszely: true });
    lebegoMenu({ focus: () => el.focus() }, e.clientX, e.clientY, elemek, akciok, t('{nev} nézet', { nev: v.nezetek[i].nev }));
  }

  // A másolás a lekérdezett nézetet adja ki: a szűrés, csoportosítás és a CSV-injekció elleni védelem megmarad.
  let masolasAllapot = $state<'kesz' | 'hiba' | null>(null);

  async function masol(fajta: Kimenet) {
    masolasAllapot = null;
    masolasAllapot = (await vagolapra(kimenetSzoveg(v, fajta))) ? 'kesz' : 'hiba';
  }

  function masolasMenu(e: MouseEvent) {
    const el = e.currentTarget as HTMLElement;
    const r = el.getBoundingClientRect();
    const elemek: MenuElem[] = [
      { id: 'tsv', nev: t('Másolás táblázatként') },
      { id: 'markdown', nev: t('Másolás Markdown-táblázatként') },
      { id: 'csv', nev: t('CSV másolása') },
    ];
    const akciok = new Map<string, () => void>();
    for (const fajta of ['tsv', 'markdown', 'csv'] as const) akciok.set(fajta, () => void masol(fajta));
    lebegoMenu({ focus: () => el.focus() }, r.left, r.bottom + 2, elemek, akciok, t('Másolás'));
  }
</script>

<div class="eszkoztar">
  {#if v.ok}
    <div class="nezetek" role="tablist" aria-label={t('Nézetek')}>
      {#each v.nezetek as n, i (i)}
        {#if atnevezett?.index === i}
          <input
            class="fulatnevezo"
            type="text"
            aria-label={t('{nev} új neve', { nev: n.nev })}
            bind:value={atnevezett.nev}
            onkeydown={(e) => {
              if (e.key === 'Enter') atnevezKesz(true);
              else if (e.key === 'Escape') atnevezKesz(false);
              e.stopPropagation();
            }}
            onblur={() => atnevezKesz(true)}
          />
        {:else}
          <button
            type="button"
            role="tab"
            class="nezet-gomb"
            aria-selected={aktiv === i}
            title={irhato ? t('Dupla kattintás: átnevezés · jobb gomb: menü') : undefined}
            onclick={() => valt(i)}
            ondblclick={() => irhato && atnevezKezd(i)}
            oncontextmenu={(e) => fulMenu(e, i)}>{n.nev}</button
          >
        {/if}
      {/each}
      {#if irhato}
        <button type="button" class="nezet-gomb ikon" aria-label={t('Új nézet')} title={t('Új nézet')} onclick={ujNezetMenu}>
          <Ikon ikon={Plus} meret={14} />
        </button>
      {/if}
    </div>
    <span class="talalat" title={idoSzoveg}>
      {tp('{n} találat', v.osszes)}{v.levagva ? ` ${t('(a lista levágva)')}` : ''}
    </span>
    {#if irhato}
      <div class="panelek">
        <Popover felirat={t('Rendezés')} ikon={ArrowDown} jelzo={rendezesDb ? String(rendezesDb) : null} cimke={t('Rendezési szabályok')}>
          <RendezesPanel {modell} {v} />
        </Popover>
        <Popover felirat={t('Csoportok')} ikon={Rows2} cimke={t('Csoportok')}>
          <CsoportPanel {modell} {v} />
        </Popover>
        <Popover felirat={t('Oszlopok')} ikon={Columns3} cimke={t('Oszlopok kijelölése és sorrendje')}>
          <OszlopPanel {modell} {v} />
        </Popover>
        <Popover felirat={t('Szűrők')} ikon={Funnel} jelzo={szuroDb ? String(szuroDb) : null} cimke={t('Szűrők és képletek')} szeles>
          <SzuroPanel {modell} {v} />
        </Popover>
        <Popover felirat={t('Nézet')} ikon={SlidersHorizontal} cimke={t('A nézet beállításai')}>
          <BeallitasPanel {modell} {v} />
        </Popover>
      </div>
    {/if}
    {#if irhato && cellaIras}
      <UjJegyzet
        {v}
        ez={modell.forras.ez}
        letrehozasTiltva={() => modell.forras.csakOlvashato() ?? (modell.forras.cellaIras?.() === false ? t('A jegyzet csak olvasható.') : null)}
      />
    {/if}
    <button type="button" class="nezet-gomb" aria-haspopup="menu" onclick={masolasMenu}><Ikon ikon={Copy} meret={14} />{t('Másolás')}</button>
  {:else}
    <span class="nezet-nev">{t('A fájl nem értelmezhető')}</span>
  {/if}
  {#if irhato}
    <button
      type="button"
      class="nezet-gomb forras"
      class:bekapcsolva={modell.forrasMod}
      aria-pressed={modell.forrasMod}
      title={t('A teljes .base fájl YAML-forrása')}
      onclick={() => (modell.forrasMod = !modell.forrasMod)}
    >
      <Ikon ikon={CodeXml} meret={14} /> YAML
    </button>
  {/if}
  {#if forrasGomb}
    <button type="button" class="nezet-gomb forras forras-gomb" onclick={forrasGomb} title={t('A blokk forrásának szerkesztése')}>{t('Forrás')}</button>
  {/if}
</div>
{#if masolasAllapot === 'hiba'}
  <p class="masolas-allapot hiba" role="alert"><Ikon ikon={TriangleAlert} meret={14} />{t('A vágólapra másolás nem sikerült')}</p>
{:else if masolasAllapot === 'kesz'}
  <p class="masolas-allapot" role="status">{t('Másolva')}</p>
{/if}

<style>
  .eszkoztar {
    flex: none;
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0 var(--t-3);
    min-height: var(--magassag-lista-sor);
    padding: 2px var(--t-3);
    border-bottom: var(--keret-vastag) solid var(--keret);
  }

  .nezetek {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--t-1);
    min-width: 0;
  }

  .nezet-gomb {
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--magassag-gomb);
    padding: 0 var(--t-2);
    border: 0;
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    color: var(--szoveg-masodlagos);
    font: inherit;
    white-space: nowrap;
    cursor: pointer;
  }

  .nezet-gomb:hover {
    background: var(--hatter-hover);
  }

  .nezet-gomb[aria-selected='true'] {
    background: var(--hatter-aktiv);
    color: var(--szoveg);
    font-weight: var(--suly-kozepes);
  }

  .nezet-gomb.ikon {
    padding: 0 var(--t-1);
    color: var(--szoveg-halvany);
  }

  .nezet-gomb.forras {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .nezet-gomb.bekapcsolva {
    background: var(--hatter-aktiv);
    color: var(--szoveg);
  }

  .fulatnevezo {
    height: var(--magassag-suru);
    width: 140px;
    padding: 0 var(--t-1);
    border: 1px solid var(--akcent);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
    outline: none;
  }

  .nezet-nev {
    font-weight: var(--suly-kozepes);
    color: var(--szoveg-masodlagos);
  }

  .talalat {
    margin-left: auto;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .panelek {
    display: flex;
    align-items: center;
    gap: var(--t-1);
  }

  .masolas-allapot {
    display: flex;
    align-items: center;
    gap: var(--t-1);
    margin: 0;
    padding: var(--t-1) var(--t-3);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .masolas-allapot.hiba {
    color: var(--hiba);
  }
</style>
