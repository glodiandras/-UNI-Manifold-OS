<!--
  Betűcsalád-mező (14-appearance-01/02): egy TELEPÍTETT család neve, előnézettel és alaphelyzet-gombbal. A név szigorú alakú
  (betűk, számjegyek, szóköz, . _ + -), a CSS-be idézőjelben és tartalékkal kerül; nincs URL, nincs külső betöltés (D3).
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { CircleAlert, TriangleAlert } from '../lib/ikon/ikonok';
  import { BETU_NEV_MAX, MONO_JAVASLAT, MONO_TARTALEK, SZOVEG_JAVASLAT, SZOVEG_TARTALEK, betuCss, betuNevJo, betuTelepitve, telepitettJavaslat, type Meroto } from '../lib/elrendezes/betutipus';

  let { ertek = $bindable(''), cimke, fajta, tiltott = false, mero }: {
    ertek?: string; cimke: string; fajta: 'szoveg' | 'mono'; tiltott?: boolean; mero?: Meroto | null;
  } = $props();

  const azonosito = $props.id();
  const jo = $derived(betuNevJo(ertek));
  const telepitve = $derived(jo && ertek !== '' ? betuTelepitve(ertek, mero) : null);
  const javaslat = $derived(telepitettJavaslat(fajta === 'mono' ? MONO_JAVASLAT : SZOVEG_JAVASLAT, mero));
  const css = $derived(betuCss(jo ? ertek : '', fajta === 'mono' ? MONO_TARTALEK : SZOVEG_TARTALEK));
</script>

<div class="betu" data-betu={fajta}>
  <label for="{azonosito}-nev">{cimke}</label>
  <div class="sor">
    <input id="{azonosito}-nev" type="text" bind:value={ertek} list="{azonosito}-lista" spellcheck="false" autocomplete="off" autocapitalize="off"
      maxlength={BETU_NEV_MAX} disabled={tiltott} placeholder={t('beallitasok.betu_alap')} aria-invalid={!jo} aria-describedby="{azonosito}-allapot" />
    <datalist id="{azonosito}-lista">{#each javaslat as n}<option value={n}></option>{/each}</datalist>
    <button type="button" class="m-gomb semleges" disabled={tiltott || ertek === ''} onclick={() => { ertek = ''; }}>{t('beallitasok.betu_alaphelyzet')}</button>
  </div>
  <p class="elonezet {fajta}" style:--betu-jegyzet={fajta === 'szoveg' ? css : undefined} style:--betu-mono={fajta === 'mono' ? css : undefined} data-elonezet={fajta} aria-label={t('beallitasok.betu_elonezet')}>
    {fajta === 'mono' ? t('beallitasok.betu_minta_mono') : t('beallitasok.betu_minta_szoveg')}
  </p>
  <div id="{azonosito}-allapot" class="allapot">
    {#if !jo}
      <p class="hiba" role="alert"><Ikon ikon={CircleAlert} /> {t('beallitasok.betu_hibas')}</p>
    {:else if telepitve === false}
      <p class="figyel" role="status"><Ikon ikon={TriangleAlert} /> {t('A(z) „{nev}” betűcsalád nincs telepítve, ezért az alapértelmezett betű látszik.', { nev: ertek })}</p>
    {/if}
  </div>
</div>

<style>
  .betu { padding: var(--t-3) 0; }
  label { display: block; padding-bottom: var(--t-2); }
  .sor { display: flex; align-items: center; gap: var(--t-3); }
  input { flex: 1; min-width: 0; padding: var(--t-2); color: var(--szoveg); background: var(--hatter); border: var(--keret-vastag) solid var(--keret-mezo); border-radius: var(--kerekites); font: inherit; }
  input[aria-invalid='true'] { border-color: var(--hiba); }
  .elonezet { margin: var(--t-2) 0 0; padding: var(--t-2) var(--t-3); background: var(--hatter-emelt); border: var(--keret-vastag) solid var(--keret); border-radius: var(--kerekites); color: var(--szoveg); }
  .elonezet.szoveg { font-family: var(--betu-jegyzet); font-size: var(--betu-torzs); }
  .elonezet.mono { font-family: var(--betu-mono); font-size: var(--betu-ui); }
  .allapot p { display: flex; align-items: center; gap: var(--t-2); margin: var(--t-2) 0 0; font-size: var(--betu-kicsi); }
  .hiba { color: var(--hiba); }
  .figyel { color: var(--szoveg-masodlagos); }
</style>
