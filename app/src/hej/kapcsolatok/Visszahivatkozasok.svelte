<!--
  Visszahivatkozások (C10): forrásonként csoportosítva, a link sorával (a link kiemelve). Kattintásra a forrás
  megnyílik az adott soron (⌘: új fül, ⌘⌥: osztás). A canvas- és a frontmatter-forrás jelölve.
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import { fajlNev, mappa } from '../../lib/vault/fajlok.svelte';
  import { kornyezetReszek, type VisszaForras, type VisszaLink } from '../../lib/vault/kapcsolatok.svelte';
  import { szuroEgyezik, szuroSzavak } from './szuro';

  let {
    forrasok,
    onnyit,
  }: { forrasok: VisszaForras[]; onnyit: (ut: string, sor: number | null, e: MouseEvent) => void } = $props();

  // 02-links-11: szűrőmező — a jegyzet neve/útja vagy a link sora; a találó jegyzetnél minden link marad
  let szuro = $state('');
  const szavak = $derived(szuroSzavak(szuro));
  const latszo = $derived.by(() => {
    if (!szavak.length) return forrasok;
    const ki: VisszaForras[] = [];
    for (const f of forrasok) {
      if (szuroEgyezik(szavak, f.ut)) ki.push(f);
      else {
        const linkek = f.linkek.filter((l) => szuroEgyezik(szavak, f.ut, l.kornyezet, l.alias, l.alcel));
        if (linkek.length) ki.push({ ...f, linkek });
      }
    }
    return ki;
  });
  const darab = $derived(latszo.reduce((n, f) => n + f.linkek.length, 0));

  function jel(l: VisszaLink): string | null {
    if (l.fajta.startsWith('canvas')) return 'canvas';
    return l.tulajdonsag;
  }
</script>

{#if !forrasok.length}
  <p class="ures">{t('Erre a jegyzetre nem mutat link.')}</p>
{:else}
  <input class="szuro" type="search" bind:value={szuro} placeholder={t('Szűrés…')} aria-label={t('Visszahivatkozások szűrése')} spellcheck="false" />
  {#if !latszo.length}
    <p class="ures" aria-live="polite">{t('Nincs találat.')}</p>
  {:else}
  <p class="osszes" aria-live="polite">{t('{darab} link, {forras} jegyzetből', { darab, forras: latszo.length })}</p>
  <ul class="forrasok">
    {#each latszo as f (f.ut)}
      <li class="forras" data-elonezet-ut={f.ut}>
        <button type="button" class="fej" title={f.ut} onclick={(e) => onnyit(f.ut, f.linkek[0]?.sor ?? null, e)} onauxclick={(e) => e.button === 1 && onnyit(f.ut, f.linkek[0]?.sor ?? null, e)}>
          <span class="nev">{fajlNev(f.ut)}</span>
          {#if mappa(f.ut)}<span class="mappa">{mappa(f.ut)}</span>{/if}
          <span class="db">{f.linkek.length}</span>
        </button>
        <ul class="linkek">
          {#each f.linkek as l, i (i)}
            {@const r = l.kornyezet !== null ? kornyezetReszek(l.kornyezet, l.oszlop, l.hossz) : null}
            <li>
              <button type="button" class="link" onclick={(e) => onnyit(f.ut, l.sor, e)} onauxclick={(e) => e.button === 1 && onnyit(f.ut, l.sor, e)}>
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
{/if}

<style>
  .szuro {
    width: 100%;
    height: var(--magassag-gomb);
    margin-bottom: var(--t-2);
    padding: 0 var(--t-2);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: var(--hatter);
    color: var(--szoveg);
    font-size: var(--betu-ui);
  }

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
