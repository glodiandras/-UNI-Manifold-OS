<!--
  Hasonló jegyzetek (C25c): a vektortárból, modell nélkül számolt legközelebbi jegyzetek. A sorra kattintva a jegyzet nyílik
  (⌘: új fül). A már linkelt jegyzet halvány jelet kap. Ha a jegyzetnek még nincs vektora, ezt mondja ki (modellt nem tölt).
  Az adatot a `JobbPanel` kéri (`lib/kereses/hasonlo.svelte.ts`), ez a komponens csak megjeleníti.
-->
<script lang="ts">
  import Ikon from '../../lib/ikon/Ikon.svelte';
  import { ArrowRight, Link2 } from '../../lib/ikon/ikonok';
  import { allapotSzoveg, pontSzazalek, type HasonloValasz } from '../../lib/kereses/hasonlo.svelte';
  import { fajlNev, mappa } from '../../lib/vault/fajlok.svelte';

  let {
    valasz,
    betolt = false,
    hiba = null,
    onnyit,
  }: { valasz: HasonloValasz | null; betolt?: boolean; hiba?: string | null; onnyit: (ut: string, e: MouseEvent) => void } = $props();
</script>

{#if hiba}
  <p class="hiba" role="alert">{hiba}</p>
{:else if !valasz}
  <p class="ures" role="status">{betolt ? 'Betöltés…' : ''}</p>
{:else if valasz.allapot !== 'ok'}
  <p class="ures" role="status">{allapotSzoveg(valasz.allapot)}</p>
{:else if !valasz.talalatok.length}
  <p class="ures" role="status">Nincs hasonló jegyzet.</p>
{:else}
  {#if valasz.elavult}<p class="ures">A jegyzet vektora egy korábbi változatáé — a vektorindex hamarosan frissíti.</p>{/if}
  <ul class="lista" aria-label="Hasonló jegyzetek">
    {#each valasz.talalatok as t (t.ut)}
      <li>
        <button type="button" class="elem" title={t.ut} onclick={(e) => onnyit(t.ut, e)}>
          <span class="szoveg">
            <span class="nev">{fajlNev(t.ut).replace(/\.md$/i, '')}</span>
            {#if mappa(t.ut)}<span class="mappa">{mappa(t.ut)}</span>{/if}
          </span>
          {#if t.kimeno || t.bejovo}
            <span class="jel" title={t.kimeno ? 'A megnyitott jegyzet már linkeli' : 'Ez linkeli a megnyitott jegyzetet'}>
              <Ikon ikon={t.kimeno ? ArrowRight : Link2} meret={14} />
            </span>
          {/if}
          <span class="pont" title="hasonlóság">{pontSzazalek(t.pont)}</span>
        </button>
      </li>
    {/each}
  </ul>
{/if}

<style>
  .ures,
  .hiba {
    margin: 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
  }

  .hiba {
    color: var(--hiba);
  }

  .lista {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .elem {
    display: flex;
    align-items: baseline;
    gap: var(--t-2);
    width: 100%;
    padding: var(--t-1) var(--t-2);
    border-radius: var(--kerekites-kicsi);
    text-align: left;
    color: var(--szoveg);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .elem:hover {
    background: var(--hatter-hover);
  }

  .szoveg {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  .nev,
  .mappa {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .mappa,
  .jel,
  .pont {
    color: var(--szoveg-halvany);
  }

  .jel {
    flex: none;
    align-self: center;
  }

  .pont {
    flex: none;
    font-variant-numeric: tabular-nums;
  }
</style>
