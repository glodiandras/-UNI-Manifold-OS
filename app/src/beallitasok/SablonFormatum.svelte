<script lang="ts">
  import { t } from '../lib/i18n';
  import { hibaUzenet } from '../lib/core/api';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { TriangleAlert } from '../lib/ikon/ikonok';
  import { mostSzoveg, type MostSzoveg } from '../ma/api';
  let { fajta, cimke, ertek = $bindable('') }: { fajta: 'date'|'time'; cimke: string; ertek: string } = $props();
  let elonezet = $state<MostSzoveg | null>(null);
  let hiba = $state('');
  $effect(() => {
    const formatum = ertek;
    const tipus = fajta;
    let ervenyes = true;
    elonezet = null;
    hiba = '';
    const ido = setTimeout(() => {
      void mostSzoveg(tipus, formatum).then((r) => { if (ervenyes) elonezet = r; }).catch((e) => { if (ervenyes) hiba = hibaUzenet(e); });
    }, 180);
    return () => { ervenyes = false; clearTimeout(ido); };
  });
</script>

<div class="formatum">
  <label>{cimke}<input type="text" bind:value={ertek} maxlength="200" spellcheck="false" /></label>
  <div class="elonezet" aria-live="polite">
    {#if hiba}<span class="hiba"><Ikon ikon={TriangleAlert} meret={14} />{t('Az előnézet nem érhető el: {hiba}', { hiba })}</span>
    {:else if elonezet}
      <span>{t('Előnézet: {szoveg}', { szoveg: elonezet.szoveg })}</span>
      {#if elonezet.ismeretlen.length}<span class="figyelmeztetes"><Ikon ikon={TriangleAlert} meret={14} />{t('Nem támogatott formátumjelek: {tokenek}', { tokenek: elonezet.ismeretlen.join(', ') })}</span>{/if}
    {/if}
  </div>
</div>

<style>
  .formatum { display: flex; flex-direction: column; gap: var(--t-1); margin-bottom: var(--t-3); }
  label { display: flex; align-items: center; justify-content: space-between; gap: var(--t-3); }
  input { min-width: 0; padding: var(--t-1) var(--t-2); border: var(--keret-vastag) solid var(--keret-mezo); border-radius: var(--kerekites-kicsi); color: var(--szoveg); background: var(--hatter); font: inherit; }
  input:focus-visible { outline: var(--fokusz-vastag) solid var(--fokusz-gyuru); outline-offset: var(--fokusz-tav); }
  .elonezet { display: flex; flex-direction: column; gap: var(--t-1); color: var(--szoveg-halvany); font-size: var(--betu-kicsi); overflow-wrap: anywhere; }
  .hiba, .figyelmeztetes { display: flex; align-items: center; gap: var(--t-1); }
  .hiba { color: var(--hiba); }
  .figyelmeztetes { color: var(--figyelmeztetes); }
</style>
