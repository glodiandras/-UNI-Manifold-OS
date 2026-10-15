<!--
  A canvas eszköztárai (C14): a vászon alsó sávja (új kártyák, rács, nagyítás, visszavonás) és a kijelölés fölötti
  lebegő sáv (szín, szerkesztés/megnyitás, csoport köré, törlés; élnél az irány és a címke). A gombok a vászon
  parancsait hívják; minden gombnak magyar címkéje és tooltipje van.
-->
<script lang="ts">
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
    { irany: 'elore', cimke: 'Irány: előre (→)', ikon: MoveRight },
    { irany: 'vissza', cimke: 'Irány: vissza (←)', ikon: MoveLeft },
    { irany: 'mindketto', cimke: 'Irány: mindkét irányba (↔)', ikon: ArrowLeftRight },
    { irany: 'nincs', cimke: 'Irány nélkül (—)', ikon: Minus },
  ];
</script>

{#snippet szinek()}
  <div class="paletta" role="group" aria-label="Szín">
    <button
      type="button"
      class="szin-minta nincs"
      class:valasztott={!p.szin}
      aria-label="Nincs szín"
      title="Nincs szín"
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
        aria-label="Szín: {nev}"
        title={nev}
        onclick={() => {
          p.onszin?.(kod);
          paletta = false;
        }}
      ></button>
    {/each}
    {#if p.szin && !SZIN_NEV[p.szin]}
      <span class="szin-minta egyedi valasztott" style:--minta={szinCss(p.szin)} title="Egyedi szín: {p.szin}"></span>
    {/if}
  </div>
{/snippet}

{#if p.fajta === 'vaszon'}
  <div class="eszkoztar" role="toolbar" aria-label="Canvas eszköztár">
    {#if p.irhato}
      <IkonGomb ikon={Type} cimke="Új szövegkártya" onclick={() => p.onparancs('uj-szoveg')} />
      <IkonGomb ikon={FilePlus} cimke="Jegyzet vagy fájl hozzáadása" onclick={() => p.onparancs('uj-fajl')} />
      <IkonGomb ikon={Link} cimke="Új link-kártya" onclick={() => p.onparancs('uj-link')} />
      <IkonGomb ikon={SquareDashed} cimke="Új csoport (a kijelölés köré)" onclick={() => p.onparancs('uj-csoport')} />
      <span class="valaszto" aria-hidden="true"></span>
      <IkonGomb ikon={Undo2} cimke="Visszavonás" billentyu="Mod+Z" disabled={!p.vanVissza} onclick={() => p.onparancs('visszavon')} />
      <IkonGomb ikon={Redo2} cimke="Újra" billentyu="Mod+Shift+Z" disabled={!p.vanElore} onclick={() => p.onparancs('ujra')} />
      <span class="valaszto" aria-hidden="true"></span>
      <IkonGomb ikon={Grid3x3} cimke="Rácsra igazítás" lenyomva={p.racs} onclick={() => p.onparancs('racs')} />
    {:else}
      <span class="csak-olvashato">Csak olvasható</span>
    {/if}
    <span class="valaszto" aria-hidden="true"></span>
    <IkonGomb ikon={ZoomOut} cimke="Kicsinyítés" onclick={() => p.onparancs('kicsinyit')} />
    <button type="button" class="szazalek" title="Nagyítás 100%-ra" onclick={() => p.onparancs('nagyitas-100')}>
      {Math.round(p.z * 100)}%
    </button>
    <IkonGomb ikon={ZoomIn} cimke="Nagyítás" onclick={() => p.onparancs('nagyit')} />
    <IkonGomb ikon={Maximize} cimke="Mindent mutat" billentyu="Shift+1" onclick={() => p.onparancs('mindent-mutat')} />
  </div>
{:else}
  <div class="eszkoztar lebego">
    <IkonGomb ikon={Palette} cimke="Szín" kicsi lenyomva={paletta} onclick={() => (paletta = !paletta)} />
    {#if p.fajta === 'kijeloles'}
      {#if p.egyedul?.type === 'file' || p.egyedul?.type === 'link'}
        <IkonGomb ikon={ExternalLink} cimke="Megnyitás" kicsi onclick={(e) => p.onmegnyit(e)} />
      {/if}
      {#if p.egyedul?.type === 'text' || p.egyedul?.type === 'link' || p.egyedul?.type === 'group'}
        <IkonGomb ikon={Pencil} cimke={p.egyedul.type === 'link' ? 'A link szerkesztése' : p.egyedul.type === 'group' ? 'Címke szerkesztése' : 'Szerkesztés'} kicsi onclick={() => p.onszerkeszt?.()} />
      {/if}
      <IkonGomb ikon={SquareDashed} cimke="Csoport a kijelölés köré" kicsi onclick={() => p.oncsoport()} />
    {:else}
      {#each IRANYOK as i (i.irany)}
        <IkonGomb ikon={i.ikon} cimke={i.cimke} kicsi lenyomva={elIranya(p.el) === i.irany} onclick={() => p.onirany(i.irany)} />
      {/each}
      <IkonGomb ikon={Pencil} cimke="Címke szerkesztése" kicsi onclick={() => p.onszerkeszt?.()} />
    {/if}
    <IkonGomb ikon={Trash2} cimke="Törlés" billentyu="Delete" kicsi onclick={() => p.ontorol?.()} />
    {#if paletta}{@render szinek()}{/if}
  </div>
{/if}
