<!--
  A Manifold-OS vezérlő lapja: jobbról becsúszik, nem modális (a jegyzet mellette látszik), Esc zárja,
  a fókusz visszatér a megnyitóra. Szakaszai (TERV 5.3): Most (a feladatsor élő nézete), Bevitel, Tanulás,
  Statisztika, Használat, Naptár és emlékeztetők (C29), Asszisztens, Modellek, Rendszer — a későbbi chatek töltik, addig tiszta üres állapot (C17); a Bevitel a videólink-letöltés (C20a), a Tanulás a „Mai ismétlés” (C23b).
  Egy feladatra kattintva a lap a feladat részletét mutatja (haladás, leállítás, napló, mit változtatott).
-->
<script lang="ts">
  import { Activity, Boxes, CalendarDays, ChartNoAxesColumn, Gauge, GraduationCap, HardDrive, Inbox, MessageCircleQuestionMark, Sparkles } from '../lib/ikon/ikonok';
  import { kornyezet } from '../lib/kornyezet';
  import Bevitel from './vezerlo/Bevitel.svelte';
  import FeladatReszlet from './vezerlo/FeladatReszlet.svelte';
  import AsszisztensStatisztika from './vezerlo/AsszisztensStatisztika.svelte';
  import AsszisztensTanult from './vezerlo/AsszisztensTanult.svelte';
  import HasznalatSzakasz from './vezerlo/HasznalatSzakasz.svelte';
  import Kerdezz from './vezerlo/Kerdezz.svelte';
  import Kapcsolok from './vezerlo/Kapcsolok.svelte';
  import NaptarSzakasz from './vezerlo/NaptarSzakasz.svelte';
  import Modellek from './vezerlo/Modellek.svelte';
  import Most from './vezerlo/Most.svelte';
  import Rendszer from './vezerlo/Rendszer.svelte';
  import StatisztikaSzakasz from './vezerlo/StatisztikaSzakasz.svelte';
  import Tanulas from './vezerlo/Tanulas.svelte';
  import Szakasz from './Szakasz.svelte';

  const { felulet } = kornyezet();
  /** Alapból csak a „Most” nyitott; a többi szakasz állapota tartós. */
  const nyitva = (id: string) => felulet.vezerlo.nyitott[id] ?? id === 'most';
  const allit = (id: string, v: boolean) => (felulet.vezerlo.nyitott[id] = v);
</script>

<div class="lap" id="manifold-lap">
  <div class="tartalom gorgeto">
    {#if felulet.manifoldFeladat}
      <FeladatReszlet id={felulet.manifoldFeladat} vissza={() => (felulet.manifoldFeladat = null)} />
    {:else}
      <Szakasz cim="Most" ikon={Activity} bind:nyitva={() => nyitva('most'), (v) => allit('most', v)}>
        <Most onnyit={(id) => (felulet.manifoldFeladat = id)} />
      </Szakasz>
      <Szakasz cim="Bevitel" ikon={Inbox} bind:nyitva={() => nyitva('bevitel'), (v) => allit('bevitel', v)}>
        {#if nyitva('bevitel')}<Bevitel onnyit={(id) => (felulet.manifoldFeladat = id)} />{/if}
      </Szakasz>
      <Szakasz cim="Kérdezz a vaulttól" ikon={MessageCircleQuestionMark} bind:nyitva={() => nyitva('kerdezz'), (v) => allit('kerdezz', v)}>
        {#if nyitva('kerdezz')}<Kerdezz />{/if}
      </Szakasz>
      <Szakasz cim="Tanulás" ikon={GraduationCap} bind:nyitva={() => nyitva('tanulas'), (v) => allit('tanulas', v)}>
        {#if nyitva('tanulas')}<Tanulas />{/if}
      </Szakasz>
      <Szakasz cim="Statisztika" ikon={ChartNoAxesColumn} bind:nyitva={() => nyitva('statisztika'), (v) => allit('statisztika', v)}>
        {#if nyitva('statisztika')}<StatisztikaSzakasz />{/if}
      </Szakasz>
      <Szakasz cim="Használat" ikon={Gauge} bind:nyitva={() => nyitva('hasznalat'), (v) => allit('hasznalat', v)}>
        {#if nyitva('hasznalat')}<HasznalatSzakasz />{/if}
      </Szakasz>
      <Szakasz cim="Naptár és emlékeztetők" ikon={CalendarDays} bind:nyitva={() => nyitva('naptar'), (v) => allit('naptar', v)}>
        {#if nyitva('naptar')}<NaptarSzakasz />{/if}
      </Szakasz>
      <Szakasz cim="Asszisztens" ikon={Sparkles} bind:nyitva={() => nyitva('asszisztens'), (v) => allit('asszisztens', v)}>
        <Kapcsolok />
        {#if nyitva('asszisztens')}<AsszisztensTanult /><AsszisztensStatisztika />{/if}
      </Szakasz>
      <Szakasz cim="Modellek" ikon={Boxes} bind:nyitva={() => nyitva('modellek'), (v) => allit('modellek', v)}>
        {#if nyitva('modellek')}<Modellek />{/if}
      </Szakasz>
      <Szakasz cim="Rendszer" ikon={HardDrive} bind:nyitva={() => nyitva('rendszer'), (v) => allit('rendszer', v)}>
        {#if nyitva('rendszer')}<Rendszer />{/if}
      </Szakasz>
    {/if}
  </div>
</div>

<style>
  .lap { margin-top: var(--t-3); background: var(--hatter-emelt); border-radius: var(--kerekites); }
  .tartalom { padding: var(--t-2) var(--t-3) var(--t-5); }
</style>
