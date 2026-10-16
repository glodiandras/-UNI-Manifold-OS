<!-- Osztás-elválasztó két panel között: húzás és ←→ / ↑↓ (5 %); role="separator". -->
<script lang="ts">
  import { t } from '../lib/i18n';
  let {
    irany,
    arany,
    tarolo,
    onvaltozas,
  }: { irany: 'sor' | 'oszlop'; arany: number; tarolo: HTMLElement | undefined; onvaltozas: (a: number) => void } =
    $props();

  let huz = $state(false);

  function le(e: PointerEvent) {
    if (e.button !== 0) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    huz = true;
  }

  function mozog(e: PointerEvent) {
    if (!huz || !tarolo) return;
    const r = tarolo.getBoundingClientRect();
    onvaltozas(irany === 'sor' ? (e.clientX - r.left) / r.width : (e.clientY - r.top) / r.height);
  }

  function billentyu(e: KeyboardEvent) {
    const [elore, hatra] = irany === 'sor' ? ['ArrowRight', 'ArrowLeft'] : ['ArrowDown', 'ArrowUp'];
    if (e.key === elore) onvaltozas(arany + 0.05);
    else if (e.key === hatra) onvaltozas(arany - 0.05);
    else return;
    e.preventDefault();
  }
</script>

<!-- A fókuszálható separator a WAI-ARIA szerint widget (ablaktábla-elválasztó), nem díszítés. -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<div
  class="elvalaszto {irany}"
  class:huz
  role="separator"
  aria-orientation={irany === 'sor' ? 'vertical' : 'horizontal'}
  aria-label={t('Panelek közötti elválasztó')}
  aria-valuenow={Math.round(arany * 100)}
  aria-valuemin={15}
  aria-valuemax={85}
  tabindex="0"
  onpointerdown={le}
  onpointermove={mozog}
  onpointerup={() => (huz = false)}
  onpointercancel={() => (huz = false)}
  onkeydown={billentyu}
></div>

<style>
  .elvalaszto {
    position: relative;
    flex: none;
    background: var(--keret);
    z-index: 2;
    touch-action: none;
  }

  .elvalaszto.sor {
    width: 1px;
    cursor: col-resize;
  }

  .elvalaszto.oszlop {
    height: 1px;
    cursor: row-resize;
  }

  /* bővebb fogási sáv, a vonal 1 px marad */
  .elvalaszto::before {
    content: '';
    position: absolute;
    inset: 0 -4px;
  }

  .elvalaszto.oszlop::before {
    inset: -4px 0;
  }

  .elvalaszto:hover,
  .elvalaszto.huz,
  .elvalaszto:focus-visible {
    background: var(--akcent);
    box-shadow: 0 0 0 var(--keret-vastag) var(--akcent);
    outline: none;
  }
</style>
