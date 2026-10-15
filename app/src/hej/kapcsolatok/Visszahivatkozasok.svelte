<!--
  Visszahivatkozások (C10): forrásonként csoportosítva, a link sorával (a link kiemelve). Kattintásra a forrás
  megnyílik az adott soron (⌘: új fül, ⌘⌥: osztás). A canvas- és a frontmatter-forrás jelölve.
-->
<script lang="ts">
  import { fajlNev, mappa } from '../../lib/vault/fajlok.svelte';
  import { kornyezetReszek, type VisszaForras, type VisszaLink } from '../../lib/vault/kapcsolatok.svelte';

  let {
    forrasok,
    onnyit,
  }: { forrasok: VisszaForras[]; onnyit: (ut: string, sor: number | null, e: MouseEvent) => void } = $props();

  const darab = $derived(forrasok.reduce((n, f) => n + f.linkek.length, 0));

  function jel(l: VisszaLink): string | null {
    if (l.fajta.startsWith('canvas')) return 'canvas';
    return l.tulajdonsag;
  }
</script>

{#if !forrasok.length}
  <p class="ures">Erre a jegyzetre nem mutat link.</p>
{:else}
  <p class="osszes" aria-live="polite">{darab} link, {forrasok.length} jegyzetből</p>
  <ul class="forrasok">
    {#each forrasok as f (f.ut)}
      <li class="forras">
        <button type="button" class="fej" title={f.ut} onclick={(e) => onnyit(f.ut, f.linkek[0]?.sor ?? null, e)}>
          <span class="nev">{fajlNev(f.ut)}</span>
          {#if mappa(f.ut)}<span class="mappa">{mappa(f.ut)}</span>{/if}
          <span class="db">{f.linkek.length}</span>
        </button>
        <ul class="linkek">
          {#each f.linkek as l, i (i)}
            {@const r = l.kornyezet !== null ? kornyezetReszek(l.kornyezet, l.oszlop, l.hossz) : null}
            <li>
              <button type="button" class="link" onclick={(e) => onnyit(f.ut, l.sor, e)}>
                {#if jel(l)}<span class="jel">{jel(l)}</span>{/if}
                {#if r}
                  <span class="szoveg">{r.elotte.trimStart().slice(-60)}<mark>{r.link}</mark>{r.utana.slice(0, 80)}</span>
                {:else}
                  <span class="szoveg halvany">{l.alias ?? (l.alcel ? `#${l.alcel}` : 'link')}</span>
                {/if}
              </button>
            </li>
          {/each}
        </ul>
      </li>
    {/each}
  </ul>
{/if}

<style>
  .ures,
  .osszes {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .osszes {
    margin-bottom: var(--t-2);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .forras + .forras {
    margin-top: var(--t-2);
  }

  .fej,
  .link {
    display: flex;
    align-items: baseline;
    gap: var(--t-2);
    width: 100%;
    padding: 2px var(--t-1);
    border-radius: var(--kerekites-kicsi);
    text-align: left;
  }

  .fej:hover,
  .link:hover {
    background: var(--hatter-hover);
  }

  .fej {
    font-size: var(--betu-ui);
    color: var(--szoveg-masodlagos);
    font-weight: var(--suly-kozepes);
  }

  .nev {
    flex: none;
    max-width: 70%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .mappa {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--szoveg-halvany);
    font-weight: normal;
    font-size: var(--betu-kicsi);
  }

  .db {
    margin-left: auto;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .linkek {
    padding-left: var(--t-3);
    border-left: 1px solid var(--keret);
    margin-left: var(--t-1);
  }

  .link {
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
  }

  .szoveg {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    overflow-wrap: anywhere;
  }

  .halvany {
    font-style: italic;
  }

  mark {
    padding: 0 1px;
    border-radius: var(--kerekites-jel);
    background: var(--jeloles-hatter);
    color: var(--szoveg);
  }

  .jel {
    flex: none;
    padding: 0 var(--t-1);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter-aktiv);
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-kicsi);
  }
</style>
