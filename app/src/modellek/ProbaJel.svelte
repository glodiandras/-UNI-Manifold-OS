<!--
  A kalibrációs jel (D9): „Calibrated” (a mérés átment a kapukon, az eredmény élesben használható) vagy „Trial” (próba: a modell erre
  a feladatra nem kalibrált). A jel ikonnal ÉS szóval jön, a szín nem hordoz jelentést (a burgundi sosem állapotjelző). A „Trial”
  mindenhol ugyanígy látszik, ahol az AI kimenete próba.
-->
<script lang="ts">
  import { CircleCheck, FlaskConical } from 'lucide';
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';

  let { jel, mero, feladat, indok }: { jel: 'kalibralt' | 'proba'; mero?: 'sajat' | 'szallitott'; feladat?: string; indok?: string | null } = $props();
</script>

<span class="jel" data-jel={jel} title={indok || (jel === 'kalibralt' ? t('modellek.jel.kalibralt_leiras') : t('modellek.jel.proba_leiras'))}>
  <Ikon ikon={jel === 'kalibralt' ? CircleCheck : FlaskConical} meret={14} />
  {#if feladat}<span class="feladat">{feladat}:</span>{/if}
  <span>{jel === 'kalibralt' ? t('modellek.jel.kalibralt') : t('modellek.jel.proba')}</span>
  {#if jel === 'kalibralt' && mero === 'sajat'}<span class="mero">{t('modellek.jel.sajat_halmaz')}</span>{/if}
</span>

<style>
  .jel { display: inline-flex; align-items: center; gap: var(--t-1); padding: 0 var(--t-2); border: var(--keret-vastag) solid var(--keret-mezo); border-radius: var(--kerekites-kicsi); color: var(--szoveg); font-size: var(--betu-kicsi); line-height: var(--sor-kicsi); white-space: nowrap; }
  .feladat, .mero { color: var(--szoveg-masodlagos); }
</style>
