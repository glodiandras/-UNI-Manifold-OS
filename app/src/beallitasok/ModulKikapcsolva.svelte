<script lang="ts">
  import type { NezetProps } from '../lib/elrendezes/nezetek.svelte';
  const adat: NezetProps = $props();
  import { t } from '../lib/i18n';
  import { beallitasMegnyit } from './allapot.svelte';
</script>
<div class="kikapcsolva" role="status"><h2>{t('beallitasok.modul_kikapcsolva')}</h2>{#if adat.ful.ut}<p>{adat.ful.ut}</p>{/if}<p>{t('beallitasok.modul_vissza')}</p><button type="button" class="m-gomb semleges" onclick={() => beallitasMegnyit('modulok')}>{t('beallitasok.modulok')}</button></div>
<style>.kikapcsolva { padding: var(--t-6); color: var(--szoveg-masodlagos); } h2 { color: var(--szoveg); font-size: var(--betu-h4); font-weight: var(--suly-kozepes); }</style>
