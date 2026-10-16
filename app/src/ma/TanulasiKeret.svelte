<script lang="ts">
  import { onMount } from 'svelte';
  import { hibaSzoveg, kerdez } from '../lib/core/api';
  import { t } from '../lib/i18n';
  import { maAdat } from './modell.svelte';
  let perc = $state(45), hiba = $state(''), mentve = $state(false);
  onMount(() => { void kerdez<{ napi_perc: number }>('/api/felkeszultseg/keret').then(d => perc = d.napi_perc).catch(e => hiba = hibaSzoveg(e)); });
  async function ment() {
    mentve = false; hiba = '';
    try { await kerdez('/api/felkeszultseg/keret', { metodus: 'PUT', torzs: { napi_perc: perc } }); mentve = true; await maAdat.frissit(); }
    catch(e) { hiba = hibaSzoveg(e); }
  }
</script>
<label>{t('Napi tanulási keret')} <input type="number" min="15" max="480" step="15" bind:value={perc} onchange={() => void ment()} /> {t('perc')}</label>
<p class="halvany">{t('Az összes dolgozat közös kerete. Naptárba csak az elfogadott javaslat kerül.')}</p>
{#if mentve}<p role="status" class="halvany">{t('Elmentve. Az új tervek ezt a keretet használják.')}</p>{/if}
{#if hiba}<p role="alert">{hiba}</p>{/if}
<style>
  label { display: flex; gap: var(--t-2); align-items: center; margin-top: var(--t-4); }
  input { width: 5em; padding: var(--t-1); border: var(--keret-vastag) solid var(--keret); border-radius: var(--kerekites); }
  .halvany { color: var(--szoveg-halvany); font-size: var(--betu-kicsi); }
  [role='alert'] { color: var(--hiba); }
</style>
