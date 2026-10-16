<!--
  A vezérlő „Statisztika” szakasza (C27): a mai aktív idő és egy 7 napos mini-oszlopdiagram; a részletek a Statisztika
  nézet-fülben. Csak nyitott szakasznál és látszó ablakban frissül.
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
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
      cim: t('{nap}: {ido} aktív', { nap: napSzoveg(n.nap), ido: idoSzoveg(n.aktiv_mp) }),
    })),
  );

  function reszletek() {
    regiszter.futtat('manifold.statisztika', 'gomb');
  }
</script>

{#if modell.hiba && !adat}
  <p class="hiba" role="alert">{t('A statisztika nem érhető el: {hiba}', { hiba: modell.hiba })}</p>
{:else if !adat}
  <p class="halvany" role="status">{t('Betöltés…')}</p>
{:else}
  {#if modell.hiba}<p class="hiba" role="alert">{t('A frissítés nem sikerült ({hiba}): a korábban betöltött adat látszik.', { hiba: modell.hiba })}</p>{/if}
  {#if !vezerloKapcsolok.ertek.tracker}<p class="halvany">{t('A Tracker ki van kapcsolva: új adat nem gyűlik.')}</p>{/if}
  {#if vezerloKapcsolok.ertek.tracker && trackerKliens.nemFogad}
    <p class="hiba" role="alert">{t('A Tracker nem tud írni: {ok}. Új adat addig nem gyűlik.', { ok: trackerKliens.nemFogad })}</p>
  {/if}
  <p class="ma"><b>{idoSzoveg(ma?.aktiv_mp ?? 0)}</b> <span class="halvany">{t('aktív ma · {ido} a héten', { ido: idoSzoveg(adat.osszes.aktiv_mp) })}</span></p>
  <Oszlopok {oszlopok} kompakt leiras={t('Az aktív idő az utolsó 7 napban')} />
  {#if adat.tantargyak.length}
    <ul class="tantargyak" aria-label={t('Tanulási idő tantárgyanként')}>
      {#each adat.tantargyak as tt (tt.tantargy)}<li><span>{tt.tantargy || t('Besorolatlan')}</span><b>{idoSzoveg(tt.aktiv_mp)}</b></li>{/each}
    </ul>
  {/if}
  <button type="button" class="m-gomb semleges gomb" onclick={reszletek}>{t('Részletek')}</button>
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
