<!--
  A vezérlő „Statisztika” szakasza (C27): a mai aktív idő és egy 7 napos mini-oszlopdiagram; a részletek a Statisztika
  nézet-fülben. Csak nyitott szakasznál és látszó ablakban frissül.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { regiszter } from '../../lib/parancsok/regiszter';
  import { statisztikaVezerlo as modell } from '../../lib/tracker/adat.svelte';
  import Oszlopok from '../../lib/tracker/grafikon/Oszlopok.svelte';
  import { trackerKliens } from '../../lib/tracker/kliens.svelte';
  import { idoSzoveg, maiNap, napCimke, napSzoveg } from '../../lib/tracker/megjelenites';
  import { vezerloKapcsolok } from '../../lib/vezerlo/kapcsolok.svelte';

  onMount(() => {
    modell.bontas = 'nap';
    modell.lap = 0;
    return modell.megjelenik();
  });

  const adat = $derived(modell.adat);
  const ma = $derived(adat?.napok.find((n) => n.nap === maiNap()));
  const oszlopok = $derived(
    (adat?.napok ?? []).map((n) => ({
      cimke: napCimke(n.nap, 'nap'),
      ertek: n.aktiv_mp,
      terv: n.terv_mp || undefined,
      cim: `${napSzoveg(n.nap)}: ${idoSzoveg(n.aktiv_mp)} aktív`,
    })),
  );

  function reszletek() {
    regiszter.futtat('manifold.statisztika', 'gomb');
  }
</script>

{#if modell.hiba && !adat}
  <p class="hiba" role="alert">A statisztika nem érhető el: {modell.hiba}</p>
{:else if !adat}
  <p class="halvany" role="status">Betöltés…</p>
{:else}
  {#if modell.hiba}<p class="hiba" role="alert">A frissítés nem sikerült ({modell.hiba}): a korábban betöltött adat látszik.</p>{/if}
  {#if !vezerloKapcsolok.ertek.tracker}<p class="halvany">A Tracker ki van kapcsolva: új adat nem gyűlik.</p>{/if}
  {#if vezerloKapcsolok.ertek.tracker && trackerKliens.nemFogad}
    <p class="hiba" role="alert">A Tracker nem tud írni: {trackerKliens.nemFogad}. Új adat addig nem gyűlik.</p>
  {/if}
  <p class="ma"><b>{idoSzoveg(ma?.aktiv_mp ?? 0)}</b> <span class="halvany">aktív ma · {idoSzoveg(adat.osszes.aktiv_mp)} a héten</span></p>
  <Oszlopok {oszlopok} kompakt leiras="Az aktív idő az utolsó 7 napban" />
  {#if adat.tantargyak.length}
    <ul class="tantargyak" aria-label="Tanulási idő tantárgyanként">
      {#each adat.tantargyak as t (t.tantargy)}<li><span>{t.tantargy || 'Besorolatlan'}</span><b>{idoSzoveg(t.aktiv_mp)}</b></li>{/each}
    </ul>
  {/if}
  <button type="button" class="m-gomb semleges gomb" onclick={reszletek}>Részletek</button>
{/if}

<style>
  .tantargyak { list-style: none; padding: 0; margin: var(--t-3) 0; }
  .tantargyak li { display: flex; justify-content: space-between; gap: var(--t-3); padding: var(--t-1) 0; }

  .ma {
    margin: 0 0 var(--t-2);
  }

  .halvany {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .hiba {
    margin: 0;
    padding: var(--t-2);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
  }

  .gomb {
    margin-top: var(--t-2);
  }

</style>
