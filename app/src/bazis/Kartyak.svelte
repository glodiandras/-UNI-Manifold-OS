<!--
  A Bases kártyanézete (C12b): rács a `cardSize` (px) szerint; a borítókép a nézet `image` tulajdonsága
  (`imageFit`, `imageAspectRatio`). A csoportosított nézet csoportfejlécekkel; 100-as adagokban rajzol („További N”),
  a képek lustán töltődnek, így az ezres lista sem fagyaszt.
-->
<script lang="ts">
  import Kartya from './Kartya.svelte';
  import type { Csoport, Sor, Valasz } from './tipusok';

  let { valasz, ez = null }: { valasz: Valasz; ez?: string | null } = $props();

  const ADAG = 100;
  type Elem = { k: 'csoport'; cs: Csoport } | { k: 'sor'; sor: Sor };

  const beall = $derived(valasz.nezet?.beallitas ?? {});
  const meret = $derived(typeof beall.cardSize === 'number' ? Math.min(800, Math.max(120, beall.cardSize)) : 200);
  const arany = $derived(typeof beall.imageAspectRatio === 'number' && beall.imageAspectRatio > 0 ? beall.imageAspectRatio : null);
  const illesztes = $derived(String(beall.imageFit ?? 'cover'));

  const elemek = $derived.by((): Elem[] => {
    const ki: Elem[] = [];
    if (valasz.csoportok) {
      for (const cs of valasz.csoportok) {
        ki.push({ k: 'csoport', cs });
        for (let i = cs.tol; i < cs.tol + cs.db; i++) ki.push({ k: 'sor', sor: valasz.sorok[i] });
      }
    } else for (const sor of valasz.sorok) ki.push({ k: 'sor', sor });
    return ki;
  });

  let darab = $state(ADAG);
  // új nézet vagy más sorhalmaz: az adag újrakezdődik
  $effect(() => {
    void valasz.nezet?.index;
    darab = ADAG;
  });
  const lathato = $derived(elemek.slice(0, darab));
  const hatra = $derived(valasz.sorok.length - lathato.filter((e) => e.k === 'sor').length);
</script>

<div class="gorgeto" role="list" aria-label="Kártyák">
  <div class="racs" style:--kartya-meret="{meret}px">
    {#each lathato as e (e.k === 'sor' ? `s${e.sor.ut}` : `c${e.cs.tol}`)}
      {#if e.k === 'csoport'}
        <h3 class="csoport">
          <span>{e.cs.cimke || 'Nincs érték'}</span>
          <span class="db">{e.cs.db}</span>
        </h3>
      {:else}
        <div role="listitem" class="elem">
          <Kartya sor={e.sor} oszlopok={valasz.oszlopok} {ez} kepSzel={Math.round(meret * 2)} {illesztes} {arany} />
        </div>
      {/if}
    {/each}
  </div>
  {#if hatra > 0}
    <button type="button" class="tovabb" onclick={() => (darab += ADAG)}>További {Math.min(hatra, ADAG)} a(z) {hatra} közül</button>
  {/if}
  {#if elemek.length === 0}
    <p class="ures" role="status">Nincs a feltételeknek megfelelő fájl.</p>
  {/if}
</div>

<style>
  .gorgeto {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: var(--t-3);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg);
  }

  .racs {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(var(--kartya-meret), 1fr));
    gap: var(--t-3);
    align-items: start;
  }

  .elem {
    min-width: 0;
  }

  .csoport {
    grid-column: 1 / -1;
    display: flex;
    align-items: baseline;
    gap: var(--t-2);
    margin: var(--t-2) 0 0;
    font-size: var(--betu-ui);
    font-weight: var(--suly-felkover);
  }

  .db {
    color: var(--szoveg-halvany);
    font-weight: var(--suly-normal);
    font-variant-numeric: tabular-nums;
  }

  .tovabb {
    display: block;
    margin: var(--t-4) auto 0;
    height: var(--magassag-gomb);
    padding: 0 var(--t-3);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    color: var(--szoveg-masodlagos);
    font: inherit;
    cursor: pointer;
  }

  .tovabb:hover {
    background: var(--hatter-hover);
  }

  .ures {
    margin: var(--t-5) var(--t-4);
    color: var(--szoveg-halvany);
  }
</style>
