<!--
  Egy kártya (C12b): borítókép (a nézet `image` tulajdonsága), a fájl neve linkként, és a nézet többi oszlopa
  (a nem üres értékek, felirattal). A Kártyák és a Kanban közös eleme. A kép a megjelenített szélességnek megfelelő
  kicsinyített változatban jön (`?w=`); a külső URL a CSP miatt nem tölthető be (halvány jelzés).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { linkMegnyit, nyitasMod } from '../szerkeszto/linkek/navigacio';
  import { linkek } from '../lib/vault/linkek.svelte';
  import Cella from './Cella.svelte';
  import type { Ertek, Oszlop, Sor } from './tipusok';

  interface Props {
    sor: Sor;
    oszlopok: Oszlop[];
    ez?: string | null;
    /** a kép szélessége px-ben (a kicsinyítéshez) */
    kepSzel?: number;
    illesztes?: string;
    /** képarány: szélesség / magasság */
    arany?: number | null;
    /** a kártya jobb felső sarkában álló elem (pl. a Kanban áthelyezés-menüje) */
    muvelet?: Snippet;
  }
  let { sor, oszlopok, ez = null, kepSzel = 400, illesztes = 'cover', arany = null, muvelet }: Props = $props();

  const nevIdx = $derived(oszlopok.findIndex((o) => o.id === 'file.name'));
  const nevCella = $derived<Ertek>(nevIdx >= 0 ? (sor.cellak[nevIdx] ?? null) : null);
  const tobbi = $derived(
    oszlopok
      .map((o, i) => ({ o, e: sor.cellak[i] ?? null }))
      .filter(({ o, e }) => o.id !== 'file.name' && !ures(e)),
  );

  function ures(e: Ertek): boolean {
    return e === null || e === '' || (typeof e === 'object' && e.t === 'lista' && e.e.length === 0);
  }

  let src = $state<string | null>(null);
  $effect(() => {
    const k = sor.kep;
    let el = true;
    if (k?.t === 'ut') void linkek.mediaUrl(k.ut, kepSzel).then((u) => el && (src = u));
    else src = null;
    return () => {
      el = false;
    };
  });

  function nyit(e: MouseEvent) {
    void linkMegnyit({ forras: ez ?? sor.ut, cel: sor.ut, alcel: null }, nyitasMod(e));
  }
</script>

<article class="kartya" data-ut={sor.ut}>
  {#if sor.kep}
    <div class="kep" style:aspect-ratio={arany ?? undefined} class:fix={arany !== null} style:background={sor.kep.t === 'szin' ? sor.kep.v : undefined}>
      {#if sor.kep.t === 'ut' && src}
        <img {src} alt="" decoding="async" loading="lazy" style:object-fit={illesztes === 'contain' ? 'contain' : 'cover'} />
      {:else if sor.kep.t === 'kulso'}
        <span class="kulso" title={sor.kep.url}>külső kép — nem tölthető be</span>
      {/if}
    </div>
  {/if}
  <div class="torzs">
    <div class="cim">
      {#if nevIdx >= 0 && typeof nevCella === 'object' && nevCella?.t === 'link'}
        <Cella ertek={nevCella} forras={sor.ut} {ez} />
      {:else}
        <button type="button" class="nev" onclick={nyit}>{sor.nev}</button>
      {/if}
      {#if muvelet}<span class="muvelet">{@render muvelet()}</span>{/if}
    </div>
    {#each tobbi as t (t.o.id)}
      <div class="tul">
        <span class="felirat">{t.o.nev}</span>
        <span class="ertek"><Cella ertek={t.e} forras={sor.ut} {ez} /></span>
      </div>
    {/each}
  </div>
</article>

<style>
  .kartya {
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
    border: var(--keret-vastag) solid var(--keret-eros);
    border-radius: var(--kerekites);
    background: var(--hatter);
  }

  .kep {
    flex: none;
    height: 140px;
    overflow: hidden;
    background: var(--hatter-oldalsav);
  }

  .kep.fix {
    height: auto;
  }

  .kep img {
    display: block;
    width: 100%;
    height: 100%;
  }

  .kulso {
    display: block;
    padding: var(--t-2);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .torzs {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--t-2) var(--t-3);
  }

  .cim {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--t-1);
    font-weight: var(--suly-kozepes);
  }

  .nev {
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--akcent-szoveg);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .nev:hover {
    text-decoration: underline;
  }

  .tul {
    display: flex;
    gap: var(--t-2);
    min-width: 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .felirat {
    flex: none;
    max-width: 40%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--szoveg-halvany);
  }

  .ertek {
    display: flex;
    min-width: 0;
    flex: 1;
    overflow: hidden;
    color: var(--szoveg-masodlagos);
  }

  .muvelet {
    flex: none;
  }
</style>
