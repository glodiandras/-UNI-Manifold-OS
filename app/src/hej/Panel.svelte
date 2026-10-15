<!-- Egy panel: fülsor + az aktív fül nézete (a nézet-regiszterből). Kattintás vagy fókusz aktiválja. -->
<script lang="ts">
  import { nezetek } from '../lib/elrendezes/nezetek.svelte';
  import type { PanelCs } from '../lib/elrendezes/munkaterulet.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import Fulsor from './Fulsor.svelte';

  let { panel }: { panel: PanelCs } = $props();
  const { felulet, fajlok } = kornyezet();
  const m = felulet.munkaterulet;

  const ful = $derived(panel.fulek.find((f) => f.id === panel.aktiv) ?? null);
  const info = $derived(ful?.ut ? fajlok.info(ful.ut) : undefined);
  const nezet = $derived(ful ? nezetek.valaszt(ful, info) : undefined);
  const aktiv = $derived(m.aktivPanelId === panel.id);
  const nezetId = $derived(`nezet-${panel.id}`);

  function aktival() {
    if (!aktiv) m.aktival(panel.id);
  }
</script>

<section
  class="panel"
  class:aktiv
  aria-label={ful?.ut ? `Panel: ${ful.ut}` : 'Panel'}
  onpointerdowncapture={aktival}
  onfocusin={aktival}
>
  <Fulsor {panel} aktivPanel={aktiv} {nezetId} />
  <div
    class="nezet gorgeto"
    id={nezetId}
    role="tabpanel"
    tabindex="-1"
    aria-labelledby={ful ? `ful-${ful.id}` : undefined}
    data-regio-fokusz={aktiv ? '' : undefined}
    onfocus={(e) => {
      // a nézet saját fókuszcélja (pl. a szerkesztő mezője) kapja a fókuszt (F6, a váltó bezárása után)
      if (e.target !== e.currentTarget) return;
      e.currentTarget.querySelector<HTMLElement>('[data-fokusz-cel]')?.focus({ preventScroll: true });
    }}
  >
    {#if ful && nezet}
      {#key ful.id + (ful.ut ?? '')}
        <nezet.komponens {ful} {info} {aktiv} />
      {/key}
    {/if}
  </div>
</section>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    height: 100%;
    background: var(--hatter);
  }

  .nezet {
    flex: 1;
    min-height: 0;
  }
</style>
