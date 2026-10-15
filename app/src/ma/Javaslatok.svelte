<!--
  A tanulási blokk javaslatai a „Ma” oldalon (C29): csendes kártyák a dolgozat alatt — cím, nap és időablak, indok.
  A „Beírom a naptárba” gomb maga a jóváhagyás (nincs további kérdés), az „Elvetem” lezárja a javaslatot. A döntés
  után a Ma oldal adata frissül; hiba esetén az üzenet a kártyán áll.
-->
<script lang="ts">
  import { javaslatIdo, napKulcs } from './datum';
  import { javaslatKezelo } from './javaslat.svelte';
  import type { Hiba, JavaslatSzakasz } from './tipusok';
  import { hibas } from './tipusok';

  let { szakasz }: { szakasz: JavaslatSzakasz | Hiba | undefined } = $props();

  const lista = $derived(szakasz && !hibas(szakasz) ? szakasz.lista : []);
  const ma = $derived(napKulcs(new Date()));
</script>

{#if szakasz && hibas(szakasz)}
  <!-- a javaslat-forrás hibája nem csendes (C32; NAPLO Ötletek, C29), de nem is riaszt: a dolgozat-szakasz él -->
  <p class="javaslat-hiba" role="status">A tanulásiblokk-javaslatok most nem tölthetők be: {szakasz.hiba}</p>
{:else if lista.length}
  <h3 id="ma-javaslat">Tanulási blokk javaslata</h3>
  {#each lista as j (j.id)}
    {@const foglalt = javaslatKezelo.foglalt.includes(j.id)}
    <div class="javaslat" role="group" aria-label={j.cim}>
      <p class="cim">{j.cim}</p>
      <p class="meta">{javaslatIdo(j, ma)}</p>
      {#if j.indok}<p class="indok">{j.indok}</p>{/if}
      {#if javaslatKezelo.hibak[j.id]}<p class="hiba" role="alert">{javaslatKezelo.hibak[j.id]}</p>{/if}
      <div class="gombok">
        <button type="button" class="m-gomb semleges gomb" disabled={foglalt} onclick={() => void javaslatKezelo.dont(j.id, 'jovahagy')}>Beírom a naptárba</button>
        <button type="button" class="m-gomb semleges gomb" disabled={foglalt} onclick={() => void javaslatKezelo.dont(j.id, 'elvet')}>Elvetem</button>
      </div>
    </div>
  {/each}
{/if}

<style>
  .javaslat-hiba {
    margin: var(--t-2) 0 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
  }

  h3 {
    margin: var(--t-4) 0 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-weight: var(--suly-felkover);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--szoveg-halvany);
  }

  .javaslat {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--t-1);
    margin-top: var(--t-2);
    padding: var(--t-2) var(--t-3);
    border: var(--keret-vastag) solid var(--keret);
    border-radius: var(--kerekites);
  }

  p {
    margin: 0;
  }

  .cim {
    font-weight: var(--suly-felkover);
  }

  .meta {
    color: var(--szoveg-masodlagos);
    font-variant-numeric: tabular-nums;
  }

  .indok {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .hiba {
    color: var(--hiba);
    font-size: var(--betu-kicsi);
  }

  .gombok {
    display: flex;
    gap: var(--t-2);
    margin-top: var(--t-1);
  }

</style>
