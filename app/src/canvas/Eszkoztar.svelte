<!--
  A canvas eszköztárai (C14): a vászon alsó sávja (új kártyák, rács, nagyítás, visszavonás) és a kijelölés fölötti
  lebegő sáv (szín, szerkesztés/megnyitás, csoport köré, törlés; élnél az irány és a címke). A gombok a vászon
  parancsait hívják; minden gombnak magyar címkéje és tooltipje van.
-->
<script lang="ts">
  import { t, tk } from '../lib/i18n';
  import {
    ArrowLeftRight,
    ExternalLink,
    FilePlus,
    Grid3x3,
    Link,
    Maximize,
    Minus,
    MoveLeft,
    MoveRight,
    Palette,
    Pencil,
    Redo2,
    SquareDashed,
    Trash2,
    Type,
    Undo2,
    ZoomIn,
    ZoomOut,
  } from '../lib/ikon/ikonok';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import type { CanvasParancs } from './aktiv.svelte';
  import { SZIN_NEV, szinCss, type Csomopont, type El } from './modell';
  import { elIranya, type ElIrany } from './muveletek';

  type Kozos = {
    szin?: string | null;
    onszin?: (szin: string | null) => void;
    ontorol?: () => void;
    onszerkeszt?: () => void;
  };

  let p:
    | ({ fajta: 'vaszon'; irhato: boolean; racs: boolean; z: number; vanVissza: boolean; vanElore: boolean; onparancs: (p: CanvasParancs) => void } & Kozos)
    | ({
        fajta: 'kijeloles';
        egyedul: Csomopont | null;
        onmegnyit: (e: MouseEvent) => void;
        oncsoport: () => void;
      } & Kozos)
    | ({ fajta: 'el'; el: El; onirany: (i: ElIrany) => void } & Kozos) = $props();

  let paletta = $state(false);

  const IRANYOK: { irany: ElIrany; cimke: string; ikon: typeof MoveRight }[] = [
    { irany: 'elore', cimke: tk('Irány: előre (→)'), ikon: MoveRight },
    { irany: 'vissza', cimke: tk('Irány: vissza (←)'), ikon: MoveLeft },
    { irany: 'mindketto', cimke: tk('Irány: mindkét irányba (↔)'), ikon: ArrowLeftRight },
    { irany: 'nincs', cimke: tk('Irány nélkül (—)'), ikon: Minus },
  ];
</script>

{#snippet szinek()}
  <div class="paletta" role="group" aria-label={t('Szín')}>
    <button
      type="button"
      class="szin-minta nincs"
      class:valasztott={!p.szin}
      aria-label={t('Nincs szín')}
      title={t('Nincs szín')}
      onclick={() => {
        p.onszin?.(null);
        paletta = false;
      }}
    ></button>
    {#each Object.entries(SZIN_NEV) as [kod, nev] (kod)}
      <button
        type="button"
        class="szin-minta"
        class:valasztott={p.szin === kod}
        style:--minta={szinCss(kod)}
        aria-label={t('Szín: {nev}', { nev: t(nev) })}
        title={t(nev)}
        onclick={() => {
          p.onszin?.(kod);
          paletta = false;
        }}
      ></button>
    {/each}
    {#if p.szin && !SZIN_NEV[p.szin]}
      <span class="szin-minta egyedi valasztott" style:--minta={szinCss(p.szin)} title={t('Egyedi szín: {szin}', { szin: p.szin })}></span>
    {/if}
  </div>
{/snippet}

{#if p.fajta === 'vaszon'}
  <div class="eszkoztar" role="toolbar" aria-label={t('Canvas eszköztár')}>
    {#if p.irhato}
      <IkonGomb ikon={Type} cimke={t('Új szövegkártya')} onclick={() => p.onparancs('uj-szoveg')} />
      <IkonGomb ikon={FilePlus} cimke={t('Jegyzet vagy fájl hozzáadása')} onclick={() => p.onparancs('uj-fajl')} />
      <IkonGomb ikon={Link} cimke={t('Új link-kártya')} onclick={() => p.onparancs('uj-link')} />
      <IkonGomb ikon={SquareDashed} cimke={t('Új csoport (a kijelölés köré)')} onclick={() => p.onparancs('uj-csoport')} />
      <span class="valaszto" aria-hidden="true"></span>
      <IkonGomb ikon={Undo2} cimke={t('Visszavonás')} billentyu="Mod+Z" disabled={!p.vanVissza} onclick={() => p.onparancs('visszavon')} />
      <IkonGomb ikon={Redo2} cimke={t('Újra|szerkesztes')} billentyu="Mod+Shift+Z" disabled={!p.vanElore} onclick={() => p.onparancs('ujra')} />
      <span class="valaszto" aria-hidden="true"></span>
      <IkonGomb ikon={Grid3x3} cimke={t('Rácsra igazítás')} lenyomva={p.racs} onclick={() => p.onparancs('racs')} />
    {:else}
      <span class="csak-olvashato">{t('Csak olvasható')}</span>
    {/if}
    <span class="valaszto" aria-hidden="true"></span>
    <IkonGomb ikon={ZoomOut} cimke={t('Kicsinyítés')} onclick={() => p.onparancs('kicsinyit')} />
    <button type="button" class="szazalek" title={t('Nagyítás 100%-ra')} onclick={() => p.onparancs('nagyitas-100')}>
      {Math.round(p.z * 100)}%
    </button>
    <IkonGomb ikon={ZoomIn} cimke={t('Nagyítás|gomb')} onclick={() => p.onparancs('nagyit')} />
    <IkonGomb ikon={Maximize} cimke={t('Mindent mutat')} billentyu="Shift+1" onclick={() => p.onparancs('mindent-mutat')} />
  </div>
{:else}
  <div class="eszkoztar lebego">
    <IkonGomb ikon={Palette} cimke={t('Szín')} kicsi lenyomva={paletta} onclick={() => (paletta = !paletta)} />
    {#if p.fajta === 'kijeloles'}
      {#if p.egyedul?.type === 'file' || p.egyedul?.type === 'link'}
        <IkonGomb ikon={ExternalLink} cimke={t('Megnyitás')} kicsi onclick={(e) => p.onmegnyit(e)} />
      {/if}
      {#if p.egyedul?.type === 'text' || p.egyedul?.type === 'link' || p.egyedul?.type === 'group'}
        <IkonGomb ikon={Pencil} cimke={p.egyedul.type === 'link' ? t('A link szerkesztése') : p.egyedul.type === 'group' ? t('Címke szerkesztése') : t('Szerkesztés')} kicsi onclick={() => p.onszerkeszt?.()} />
      {/if}
      <IkonGomb ikon={SquareDashed} cimke={t('Csoport a kijelölés köré')} kicsi onclick={() => p.oncsoport()} />
    {:else}
      {#each IRANYOK as i (i.irany)}
        <IkonGomb ikon={i.ikon} cimke={t(i.cimke)} kicsi lenyomva={elIranya(p.el) === i.irany} onclick={() => p.onirany(i.irany)} />
      {/each}
      <IkonGomb ikon={Pencil} cimke={t('Címke szerkesztése')} kicsi onclick={() => p.onszerkeszt?.()} />
    {/if}
    <IkonGomb ikon={Trash2} cimke={t('Törlés')} billentyu="Delete" kicsi onclick={() => p.ontorol?.()} />
    {#if paletta}{@render szinek()}{/if}
  </div>
{/if}
