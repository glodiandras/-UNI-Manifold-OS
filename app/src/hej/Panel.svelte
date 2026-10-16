<!-- Egy panel: fülsor + az aktív fül nézete (a nézet-regiszterből). Kattintás vagy fókusz aktiválja. -->
<script lang="ts">
  import { t } from '../lib/i18n';
  import { nezetek } from '../lib/elrendezes/nezetek.svelte';
  import type { PanelCs } from '../lib/elrendezes/munkaterulet.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import { fulHuzas, huzasZona, HUZAS_TIPUS, type HuzasZona } from '../lib/elrendezes/fulHuzas.svelte';
  import Fulsor from './Fulsor.svelte';
  import { szinkronAllapot } from '../lib/elrendezes/fulHuzas.svelte';

  let { panel }: { panel: PanelCs } = $props();
  const { felulet, fajlok } = kornyezet();
  const m = felulet.munkaterulet;

  const ful = $derived(panel.fulek.find((f) => f.id === panel.aktiv) ?? null);
  const info = $derived(ful?.ut ? fajlok.info(ful.ut) : undefined);
  const nezet = $derived(ful ? nezetek.valaszt(ful, info) : undefined);
  const aktiv = $derived(m.aktivPanelId === panel.id);
  const nezetId = $derived(`nezet-${panel.id}`);
  const szinkronig = szinkronAllapot;

  function aktival() {
    if (!aktiv) m.aktival(panel.id);
  }

  // összekapcsolt fülcsoportok (06-workspace-08): a görgetés aránya követi a társcsoportokat. A nézet saját görgetője
  // (szerkesztő, olvasó) bármi lehet, ezért a `scroll` esemény célpontját a társ nézetben ugyanaz az osztály keresi meg.
  let nezetEl: HTMLElement | undefined = $state();
  function gorges(e: Event) {
    if (!panel.kapcsolt || Date.now() < szinkronig.ido) return;
    const forras = e.target as HTMLElement | null;
    if (!(forras instanceof HTMLElement) || forras.scrollHeight <= forras.clientHeight) return;
    const arany = forras.scrollTop / (forras.scrollHeight - forras.clientHeight);
    const osztaly = forras === nezetEl ? '' : forras.classList[0];
    for (const tars of m.kapcsoltTarsak(panel.id)) {
      const doboz = document.querySelector<HTMLElement>(`[data-panel-id="${tars.id}"] .nezet`);
      const cel = !doboz ? null : osztaly ? doboz.querySelector<HTMLElement>(`.${CSS.escape(osztaly)}`) : doboz;
      if (!cel || cel.scrollHeight <= cel.clientHeight) continue;
      szinkronig.ido = Date.now() + 120; // a programozott görgetés visszhangja nem indít újabb szinkront
      cel.scrollTop = arany * (cel.scrollHeight - cel.clientHeight);
    }
  }

  // fül húzása a panel szélére = osztás (06-workspace-02); a közép a fülcsoportba ejt
  let zona = $state<HuzasZona | null>(null);
  function felett(e: DragEvent) {
    if (!fulHuzas.fulId || !e.dataTransfer?.types.includes(HUZAS_TIPUS)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    zona = huzasZona(e.clientX - r.left, e.clientY - r.top, r.width, r.height);
  }
  function ejt(e: DragEvent) {
    const id = e.dataTransfer?.getData(HUZAS_TIPUS) || fulHuzas.fulId;
    const z = zona;
    zona = null;
    fulHuzas.fulId = null;
    if (!id || !z) return;
    e.preventDefault();
    if (z === 'kozep') m.athelyez(id, panel.id, panel.fulek.length);
    else m.athelyezOsztasba(id, panel.id, z);
  }
</script>

<section
  class="panel"
  class:aktiv
  data-panel-id={panel.id}
  aria-label={ful?.ut ? t('Panel: {ut}', { ut: ful.ut }) : t('Panel')}
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
    bind:this={nezetEl}
    onscrollcapture={gorges}
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
  {#if fulHuzas.fulId}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="huzas-reteg" data-huzas-reteg ondragover={felett} ondragleave={() => (zona = null)} ondrop={ejt}>
      {#if zona}<div class="zona {zona}" data-zona={zona}></div>{/if}
    </div>
  {/if}
</section>

<style>
  .panel {
    position: relative;
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

  .huzas-reteg {
    position: absolute;
    top: var(--fulsor-teljes);
    right: 0;
    bottom: 0;
    left: 0;
    z-index: var(--reteg-lap);
  }

  .zona {
    position: absolute;
    border: var(--keret-vastag) solid var(--keret-eros);
    background: var(--hatter-aktiv);
    opacity: var(--atlatszosag-felig);
    pointer-events: none;
  }

  .zona.bal { top: 0; bottom: 0; left: 0; width: 50%; }
  .zona.jobb { top: 0; right: 0; bottom: 0; width: 50%; }
  .zona.fel { top: 0; right: 0; left: 0; height: 50%; }
  .zona.le { right: 0; bottom: 0; left: 0; height: 50%; }
  .zona.kozep { inset: 0; }
</style>
