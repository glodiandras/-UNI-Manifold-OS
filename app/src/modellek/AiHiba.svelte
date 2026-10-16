<!--
  Az AI-funkciók közös hibája (a hibaszerződés `ai` mezője szerint): mi történt, mit tegyen a felhasználó, és egy gomb a Model
  Managerre, ha az segít („no calibrated model” → „Open Model Manager”). A szöveget a `lib/modellek/aiHiba.ts` adja; a megjelenítés
  a közös hibapanel (ikon + szó, a burgundi nem jelez állapotot). A hívó átadhatja az `Error`-t, a hibatörzset vagy az `ai` mezőt.
-->
<script lang="ts">
  import { aiHibaAdat, aiHibaSzoveg, modellkezelovelJavithato } from '../lib/modellek/aiHiba';
  import { modellek } from '../lib/modellek/allapot.svelte';
  import { t } from '../lib/i18n';
  import HibaPanel from '../lib/ui/HibaPanel.svelte';
  import { beallitasMegnyit } from '../beallitasok/allapot.svelte';

  let { hiba, onmodellek, diagnosztika }: { hiba: unknown; onmodellek?: () => void; diagnosztika?: () => void } = $props();

  const ai = $derived(aiHibaAdat(hiba));
  const szoveg = $derived(ai ? aiHibaSzoveg(ai, modellek.cimek) : null);
  const nyit = () => (onmodellek ?? (() => beallitasMegnyit('modellek')))();
</script>

{#if ai && szoveg}
  <HibaPanel
    mi={szoveg.mi}
    javitas={szoveg.javitas}
    ujra={modellkezelovelJavithato(ai) ? nyit : undefined}
    ujraCimke={t('modellek.ai.megnyit')}
    {diagnosztika}
  />
{/if}
