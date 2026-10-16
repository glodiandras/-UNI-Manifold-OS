<!-- A ⇧⌘F gyors belépő megmarad; a lista az oldalsávval közös komponensből és állapotból jön. -->
<script lang="ts">
  import { t } from '../lib/i18n';
  import { modulEngedelyezett } from '../lib/beallitasok/allapot.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import KeresoTartalom from '../lib/kereses/KeresoTartalom.svelte';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  const { felulet } = kornyezet();
  const engedelyezett = $derived(modulEngedelyezett('kereses'));
  $effect(() => { if (!engedelyezett && felulet.atfedes === 'kereso') felulet.atfedes = null; });
</script>

{#if engedelyezett}
  <Atfedes cimke={t('Keresés a vaultban')} nev="kereso" szeles onbezar={() => { felulet.atfedes = null; }}>
    <KeresoTartalom />
  </Atfedes>
{/if}
