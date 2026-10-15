<!--
  A héj rácsa: oldalsáv | munkaterület | jobb panel, alatta az állapotsor. A sávszélességek első
  festéskor véglegesek (a mentett állapot a mount előtt megjön), így nincs elcsúszás.
-->
<script lang="ts">
  import Paletta from '../atfedes/Paletta.svelte';
  import Atnevezes from '../atfedes/Atnevezes.svelte';
  import Valto from '../atfedes/Valto.svelte';
  import KeresoAblak from '../atfedes/KeresoAblak.svelte';
  import SablonValaszto from '../ma/SablonValaszto.svelte';
  import UjCppFeladat from '../kod/UjFeladat.svelte';
  import KulsoAi from '../osszefoglalas/KulsoAi.svelte';
  import { JOBB_PANEL, OLDALSAV } from '../lib/elrendezes/felulet.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import Allapotsor from './Allapotsor.svelte';
  import LeallVedelem from './LeallVedelem.svelte';
  import Atmeretezo from './Atmeretezo.svelte';
  import Ertesitesek from './Ertesitesek.svelte';
  import JavaslatKartya from '../lib/asszisztens/JavaslatKartya.svelte';
  import JobbPanel from './JobbPanel.svelte';
  import Ikonsav from './Ikonsav.svelte';
  import Oldalsav from './Oldalsav.svelte';
  import Osztas from './Osztas.svelte';

  const { felulet } = kornyezet();
  let huzas = $state(false);
</script>

<LeallVedelem>
<div
  class="hej"
  class:huzas
  style:--oldalsav-sz="{felulet.oldalsav.nyitva ? felulet.oldalsav.szelesseg : 0}px"
  style:--jobb-sz="{felulet.jobbPanel.nyitva ? felulet.jobbPanel.szelesseg : 0}px"
  style:--oldalsav-atfedes-sz="{felulet.oldalsav.szelesseg}px"
  style:--jobb-atfedes-sz="{felulet.jobbPanel.szelesseg}px"
>
  <Ikonsav />
  <Oldalsav />
  <main class="munkaterulet" data-regio="munkaterulet" aria-label="Munkaterület">
    {#if felulet.oldalsav.nyitva}
      <Atmeretezo
        bind:ertek={felulet.oldalsav.szelesseg}
        min={OLDALSAV.min}
        max={OLDALSAV.max}
        oldal="jobb"
        cimke="Az oldalsáv szélessége"
        onhuzas={(h) => (huzas = h)}
      />
    {/if}
    <Osztas cs={felulet.munkaterulet.gyoker} />
    {#if felulet.jobbPanel.nyitva}
      <div class="jobb-szel">
        <Atmeretezo
          bind:ertek={felulet.jobbPanel.szelesseg}
          min={JOBB_PANEL.min}
          max={JOBB_PANEL.max}
          oldal="bal"
          cimke="A jobb panel szélessége"
          onhuzas={(h) => (huzas = h)}
        />
      </div>
    {/if}
  </main>
  <JobbPanel />
  <Allapotsor />
</div>

<Ertesitesek />
<JavaslatKartya />
{#if felulet.atfedes === 'paletta'}
  <Paletta />
{:else if felulet.atfedes === 'valto'}
  <Valto />
{:else if felulet.atfedes === 'kereso'}
  <KeresoAblak />
{:else if felulet.atfedes === 'atnevezes' && felulet.atnevezes}
  <Atnevezes />
{:else if felulet.atfedes === 'sablon'}
  <SablonValaszto />
{:else if felulet.atfedes === 'cpp-feladat'}
  <UjCppFeladat />
{:else if felulet.atfedes === 'kulso-ai'}
  <KulsoAi />
{/if}
</LeallVedelem>

<style>
  .hej {
    display: grid;
    grid-template-columns: var(--szelesseg-ikonsav) var(--oldalsav-sz) minmax(0, 1fr) var(--jobb-sz);
    grid-template-rows: minmax(0, 1fr) var(--allapotsor-hely);
    grid-template-areas:
      'ikon oldalsav munka jobb'
      'ikon allapot allapot allapot';
    position: relative;
    height: 100%;
    transition: grid-template-columns var(--mozgas-alap) var(--mozgas-gorbe);
    /* az állapotsor sora: csendben 0, az állapotsor ekkor átfedésként jön elő (C38; nincs elcsúszás) */
    --allapotsor-hely: var(--allapotsor-teljes);
  }

  :global(html[data-csend]) .hej {
    --allapotsor-hely: 0px;
  }

  .hej.huzas {
    transition: none;
    cursor: col-resize;
  }

  .hej.huzas :global(*) {
    cursor: col-resize !important;
  }

  .munkaterulet {
    grid-area: munka;
    position: relative;
    display: flex;
    min-width: 0;
    min-height: 0;
  }

  .munkaterulet > :global(.panel),
  .munkaterulet > :global(.osztas) {
    flex: 1;
  }

  .jobb-szel {
    position: absolute;
    top: 0;
    bottom: 0;
    right: 0;
    width: 0;
  }

  .jobb-szel :global(.atmeretezo) {
    left: -4px;
  }
</style>
