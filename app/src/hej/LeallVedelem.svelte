<!--
  A „leáll” védelem (C29.7b, T121): a héj kilépéskor megvárja a mentést és a core leállását. Ez alatt az egész felület
  (`children`) `inert` — a CodeMirror, a canvas-kártya, a Bases-cella, a tulajdonság-panel egységesen nem szerkeszthető —,
  és egy modális jelző mondja meg az okot. A „Kényszerített kilépés” a héjnak szól (a második ⌘Q megfelelője).
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import type { Snippet } from 'svelte';
  import { hejnek } from '../lib/core/hej';
  import { leall } from '../lib/core/leall.svelte';

  const { children }: { children: Snippet } = $props();
  let gomb = $state<HTMLButtonElement>();

  /** A `inert` attribútum kifejezetten (nem DOM-tulajdonságként): minden motorban ugyanaz, és tesztelhető. */
  function inertAttr(node: HTMLElement, aktiv: boolean) {
    node.toggleAttribute('inert', aktiv);
    return { update: (a: boolean) => node.toggleAttribute('inert', a) };
  }

  $effect(() => {
    if (leall.aktiv && gomb) gomb.focus();
  });
</script>

<div class="vedett" use:inertAttr={leall.aktiv}>{@render children()}</div>
{#if leall.aktiv}
  <div class="hatter">
    <div class="leall" role="alertdialog" aria-modal="true" aria-labelledby="leall-cim" aria-describedby="leall-szoveg">
      <h2 id="leall-cim">{t('A Manifold leáll')}</h2>
      <p id="leall-szoveg">{leall.szoveg}</p>
      <p class="mellek">{t('A szerkesztés ilyenkor szünetel, hogy ami elmentődött, az maradjon is.')}</p>
      <button bind:this={gomb} type="button" onclick={() => hejnek({ tipus: 'kenyszeritett-kilepes' })}>{t('Kényszerített kilépés')}</button>
    </div>
  </div>
{/if}

<style>
  .vedett {
    display: contents;
  }

  .hatter {
    position: fixed;
    inset: 0;
    z-index: calc(var(--reteg-ertesites) + 1);
    display: grid;
    place-items: center;
    background: var(--hatter-fatyol);
  }

  .leall {
    width: min(26rem, calc(100vw - var(--t-8)));
    padding: var(--t-5) var(--t-6);
    background: var(--hatter-emelt);
    color: var(--szoveg);
    border: 1px solid var(--keret-eros);
    border-radius: var(--kerekites-nagy);
    box-shadow: var(--arnyek-atfedes);
    display: grid;
    gap: var(--t-3);
  }

  h2 {
    margin: 0;
    font-size: var(--betu-h4);
    font-weight: var(--suly-cim);
  }

  p {
    margin: 0;
    font-size: var(--betu-ui);
  }

  .mellek {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  button {
    justify-self: end;
    padding: var(--t-1) var(--t-4);
    border-radius: var(--kerekites);
    font-size: var(--betu-ui);
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  button:hover {
    background: var(--hatter-aktiv);
  }
</style>
