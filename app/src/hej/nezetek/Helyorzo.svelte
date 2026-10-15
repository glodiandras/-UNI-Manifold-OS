<!--
  Helyőrző nézet egy fájlhoz, amíg a típusának nincs saját nézete (a `.md` a C08 szerkesztőjében nyílik).
  A cím és az adatok az olvasótörzs tipográfiáját mutatják (16 px, 44rem).
-->
<script lang="ts">
  import { TIPUS_NEV } from '../../lib/ikon/fajlIkon';
  import type { NezetProps } from '../../lib/elrendezes/nezetek.svelte';
  import { kornyezet } from '../../lib/kornyezet';
  import { fajlNev, mappa } from '../../lib/vault/fajlok.svelte';

  let { ful, info }: NezetProps = $props();
  const { fajlok } = kornyezet();
  const ut = $derived(ful.ut ?? '');
  const szam = new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 1 });
  const datum = new Intl.DateTimeFormat('hu-HU', { dateStyle: 'long', timeStyle: 'short' });

  function meret(b: number): string {
    if (b < 1024) return `${b} bájt`;
    if (b < 1024 * 1024) return `${szam.format(b / 1024)} KB`;
    return `${szam.format(b / 1024 / 1024)} MB`;
  }
</script>

<article class="helyorzo tipo olvasas">
  {#if mappa(ut)}<p class="morzsa">{mappa(ut).replaceAll('/', ' / ')}</p>{/if}
  <h1>{fajlNev(ut)}</h1>
  {#if info}
    <dl class="adatok">
      <dt>Típus</dt>
      <dd>{TIPUS_NEV[info.tipus]}</dd>
      <dt>Méret</dt>
      <dd>{meret(info.meret)}</dd>
      {#if info.mtime}
        <dt>Módosítva</dt>
        <dd>{datum.format(info.mtime * 1000)}</dd>
      {/if}
    </dl>
  {:else if fajlok.betoltve}
    <p class="megjegyzes">A fájl nincs az indexben (törölték vagy átnevezték).</p>
  {:else}
    <div class="adatok-hely" aria-hidden="true"></div>
  {/if}
  <p class="megjegyzes">Ehhez a fájltípushoz még nincs nézet; addig az adatai látszanak.</p>
</article>

<style>
  .helyorzo {
    padding: var(--t-7) var(--t-6) var(--t-8);
  }

  .morzsa {
    margin: 0 0 var(--t-2);
    color: var(--szoveg-halvany);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
  }

  .helyorzo h1 {
    margin-top: 0;
  }

  .adatok {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: var(--t-1) var(--t-5);
    margin: var(--t-4) 0 var(--t-5);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
  }

  /* a betöltés alatt ugyanannyi hely, hogy az adatok megjelenése ne tolja el a szöveget */
  .adatok-hely {
    height: calc(3 * var(--sor-ui) + 2 * var(--t-1));
    margin: var(--t-4) 0 var(--t-5);
  }

  dt {
    color: var(--szoveg-halvany);
  }

  dd {
    margin: 0;
    color: var(--szoveg-masodlagos);
    font-variant-numeric: tabular-nums;
  }

  .megjegyzes {
    color: var(--szoveg-halvany);
  }
</style>
