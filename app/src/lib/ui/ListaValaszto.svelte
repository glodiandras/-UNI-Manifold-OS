<!--
  A paletta és a gyorsváltó közös listája: combobox + listbox (WAI-ARIA 1.2), a fókusz végig a mezőben
  marad, az aktív sort az aria-activedescendant jelöli. ↑↓ (⌃N/⌃P), PageUp/PageDown, Enter, ⌘Enter, ⌥⌘Enter, Esc.
-->
<script module lang="ts">
  export interface Modositok {
    uj: boolean;
    oszt: boolean;
  }
</script>

<script lang="ts" generics="T">
  import type { Snippet } from 'svelte';
  import { tick } from 'svelte';

  let {
    elemek,
    kulcs,
    sor,
    lekerdezes = $bindable(''),
    helyorzo,
    cimke,
    ures,
    onvalaszt,
    onbevitel,
    onbezar,
    lablec,
  }: {
    elemek: T[];
    kulcs: (e: T) => string;
    sor: Snippet<[T, boolean]>;
    lekerdezes?: string;
    helyorzo: string;
    cimke: string;
    ures: string;
    onvalaszt: (e: T, m: Modositok) => void;
    /** Egyedi Enter (pl. új jegyzet): igaz esetén a listaválasztás kimarad. */
    onbevitel?: (e: KeyboardEvent) => boolean;
    onbezar: () => void;
    lablec?: Snippet;
  } = $props();

  const id = $props.id();
  let aktiv = $state(0);
  let lista: HTMLUListElement | undefined = $state();

  // Új találati lista → az első sor az aktív.
  $effect.pre(() => {
    void elemek;
    aktiv = 0;
  });

  $effect(() => {
    const i = aktiv;
    void tick().then(() => {
      lista?.querySelector<HTMLElement>(`[data-index="${i}"]`)?.scrollIntoView?.({ block: 'nearest' });
    });
  });

  function lep(d: number, kor = true) {
    const n = elemek.length;
    if (!n) return;
    let i = aktiv + d;
    if (kor) i = (i + n) % n;
    else i = Math.max(0, Math.min(n - 1, i));
    aktiv = i;
  }

  function valaszt(i: number, e: KeyboardEvent | MouseEvent) {
    const elem = elemek[i];
    if (elem === undefined) return;
    onvalaszt(elem, { uj: e.metaKey && !e.altKey, oszt: e.metaKey && e.altKey });
  }

  function billentyu(e: KeyboardEvent) {
    if (e.isComposing) return;
    const ctrl = e.ctrlKey && !e.metaKey && !e.altKey;
    if (e.key === 'ArrowDown' || (ctrl && e.key === 'n')) lep(1);
    else if (e.key === 'ArrowUp' || (ctrl && e.key === 'p')) lep(-1);
    else if (e.key === 'PageDown') lep(8, false);
    else if (e.key === 'PageUp') lep(-8, false);
    else if (e.key === 'Enter') { if (!onbevitel?.(e)) valaszt(aktiv, e); }
    else if (e.key === 'Escape') onbezar();
    else if (e.key === 'Tab') {
      /* a fókusz a mezőben marad */
    } else return;
    e.preventDefault();
    e.stopPropagation();
  }
</script>

<div class="valaszto">
  <div class="mezo">
    <input
      type="text"
      role="combobox"
      aria-label={cimke}
      aria-expanded="true"
      aria-controls="{id}-lista"
      aria-autocomplete="list"
      aria-activedescendant={elemek.length ? `${id}-${aktiv}` : undefined}
      placeholder={helyorzo}
      autocomplete="off"
      autocapitalize="off"
      spellcheck="false"
      bind:value={lekerdezes}
      onkeydown={billentyu}
      data-autofocus
      {@attach (el) => el.focus()}
    />
  </div>
  <ul class="lista gorgeto" id="{id}-lista" role="listbox" aria-label={cimke} bind:this={lista}>
    {#each elemek as elem, i (kulcs(elem))}
      <!-- A billentyűzet a combobox mezőjében él (aria-activedescendant), a sor csak egérrel kattintható. -->
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <li
        id="{id}-{i}"
        role="option"
        aria-selected={i === aktiv}
        class:aktiv={i === aktiv}
        data-index={i}
        onpointermove={() => (aktiv = i)}
        onmousedown={(e) => e.preventDefault()}
        onclick={(e) => valaszt(i, e)}
      >
        {@render sor(elem, i === aktiv)}
      </li>
    {/each}
  </ul>
  {#if !elemek.length}
    <p class="ures" role="status">{ures}</p>
  {/if}
  {#if lablec}
    <div class="lablec">{@render lablec()}</div>
  {/if}
</div>

<style>
  .valaszto {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .mezo {
    flex: none;
    border-bottom: var(--keret-vastag) solid var(--keret);
  }

  input {
    display: block;
    width: 100%;
    height: var(--magassag-mezo);
    padding: 0 var(--t-4);
    border: 0;
    background: transparent;
    font-size: var(--betu-mezo);
    line-height: var(--sor-mezo);
    color: var(--szoveg);
    user-select: text;
    -webkit-user-select: text;
  }

  input::placeholder {
    color: var(--szoveg-halvany);
  }

  input:focus-visible {
    outline: none;
  }

  .lista {
    margin: 0;
    padding: var(--t-1) var(--t-2) var(--t-2);
    list-style: none;
    min-height: 0;
    flex: 0 1 auto;
    scrollbar-gutter: auto;
  }

  li {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    height: var(--magassag-lista-sor);
    padding: 0 var(--t-2);
    border-radius: var(--kerekites);
    color: var(--szoveg);
  }

  li.aktiv {
    background: var(--hatter-kijelolt);
  }

  li:active {
    background: var(--hatter-aktiv);
  }

  .ures {
    padding: var(--t-4) var(--t-4) var(--t-5);
    color: var(--szoveg-halvany);
  }

  .lablec {
    flex: none;
    display: flex;
    flex-wrap: wrap;
    gap: var(--t-1) var(--t-4);
    align-items: center;
    min-height: var(--magassag-lista-sor);
    padding: var(--t-1) var(--t-4);
    border-top: var(--keret-vastag) solid var(--keret);
    background: var(--hatter-oldalsav);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }
</style>
