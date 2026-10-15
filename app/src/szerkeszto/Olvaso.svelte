<!--
  Az Olvasó: a jegyzet HTML-ként, a szerkesztővel azonos elemzőből (olvaso/html.ts). A dokumentum
  változásakor (jelölőnégyzet, külső változás) újrarajzol, a görgetési hely megmarad. A jelölőnégyzetre
  kattintás a dokumentumot írja; a lábjegyzet-hivatkozás a lap aljára ugrik, a ↩ vissza.
-->
<script lang="ts">
  import { ensureSyntaxTree } from '@codemirror/language';
  import type { EditorView } from '@codemirror/view';
  import { onDestroy, onMount } from 'svelte';
  import type { Dokumentum } from './dokumentum/dokumentum.svelte';
  import { obsidianElemzo } from './markdown/elemzo';
  import { domCel, elonezetKapcsol } from './linkek/elonezet';
  import { kulsoLink } from './linkek/kulso';
  import { linkMegnyit, nyitasMod } from './linkek/navigacio';
  import { dokumentumRenderel } from './olvaso/html';
  import { LustaRajzolo } from './olvaso/lusta';

  let { view, dok, ut, valtozat }: { view: EditorView; dok: Dokumentum; ut: string; valtozat: number } = $props();

  let gorgeto: HTMLDivElement | undefined = $state();
  let tartalom: HTMLElement | undefined = $state();
  let lusta: LustaRajzolo | null = null;
  let kesleltetes: ReturnType<typeof setTimeout> | null = null;
  const elotag = `lj${Math.random().toString(36).slice(2, 8)}`;

  function rajzol() {
    if (!tartalom || !gorgeto) return;
    const state = view.state;
    const doc = state.doc;
    const fa = ensureSyntaxTree(state, doc.length, 3000) ?? obsidianElemzo.parse(doc.toString());
    const gorgetes = gorgeto.scrollTop;
    lusta?.leall();
    lusta = new LustaRajzolo(gorgeto);
    const f = dokumentumRenderel(fa, { olvas: (a, b) => doc.sliceString(a, b), ut, lusta, elotag });
    tartalom.replaceChildren(f);
    gorgeto.scrollTop = gorgetes;
  }

  /** A legfelső látható blokk forrásbeli helye (a módváltás ide görget). */
  export function felsoPozicio(): number {
    if (!gorgeto || !tartalom) return 0;
    const teto = gorgeto.getBoundingClientRect().top;
    for (const e of tartalom.children) {
      if (!(e instanceof HTMLElement) || e.dataset.from === undefined) continue;
      if (e.getBoundingClientRect().bottom > teto + 4) return Number(e.dataset.from);
    }
    return 0;
  }

  export function gorget(pos: number): void {
    if (!tartalom || !gorgeto) return;
    let cel: HTMLElement | null = null;
    for (const e of tartalom.children) {
      if (!(e instanceof HTMLElement) || e.dataset.from === undefined) continue;
      if (Number(e.dataset.from) > pos) break;
      cel = e;
    }
    if (cel) gorgeto.scrollTop += cel.getBoundingClientRect().top - gorgeto.getBoundingClientRect().top - 8;
  }

  function linkNyit(e: MouseEvent | KeyboardEvent): boolean {
    const kulso = (e.target as HTMLElement).closest<HTMLElement>('a.link[data-url]');
    if (kulso?.dataset.url) {
      e.preventDefault();
      kulsoLink(kulso.dataset.url);
      return true;
    }
    const wl = (e.target as HTMLElement).closest<HTMLElement>('.wikilink[data-cel]');
    if (!wl || wl.dataset.forras === undefined) return false;
    e.preventDefault();
    void linkMegnyit({ forras: wl.dataset.forras, cel: wl.dataset.cel ?? '', alcel: wl.dataset.alcel ?? null }, nyitasMod(e));
    return true;
  }

  function kattintas(e: MouseEvent) {
    if (linkNyit(e)) return;
    const t = e.target as HTMLElement;
    const hiv = t.closest<HTMLElement>('[data-labjegyzet]');
    const vissza = t.closest<HTMLElement>('[data-labjegyzet-vissza]');
    if (hiv || vissza) {
      e.preventDefault();
      const id = hiv ? `${elotag}-def-${hiv.dataset.labjegyzet}` : `${elotag}-hiv-${vissza!.dataset.labjegyzetVissza}`;
      document.getElementById(id)?.scrollIntoView({ block: 'center' });
    }
  }

  function billentyu(e: KeyboardEvent) {
    if (e.key === 'Enter' && linkNyit(e)) return;
    if ((e.key === 'Enter' || e.key === ' ') && (e.target as HTMLElement).closest('[data-labjegyzet], [data-labjegyzet-vissza]')) {
      kattintas(e as unknown as MouseEvent);
    }
  }

  function valtas(e: Event) {
    const t = e.target as HTMLInputElement;
    if (!t.matches('input.feladat-jelolo') || t.dataset.jelolo === undefined) return;
    if (view.state.readOnly || dok.csakOlvashato) {
      t.checked = !t.checked;
      return;
    }
    const pos = Number(t.dataset.jelolo);
    // az újrarajzolás késleltetett (120 ms): ha közben a dokumentum megváltozott, a jelölő pozíciója elavult lehet — ekkor
    // nem írunk, hanem újrarajzolunk (T120)
    if (!/^\[[^\r\n]\]$/u.test(view.state.sliceDoc(pos, pos + 3))) {
      t.checked = !t.checked;
      rajzol();
      return;
    }
    const allapot = view.state.sliceDoc(pos + 1, pos + 2);
    view.dispatch({ changes: { from: pos + 1, to: pos + 2, insert: allapot === ' ' ? 'x' : ' ' }, userEvent: 'input.feladat' });
  }

  onMount(() => {
    rajzol();
    return tartalom ? elonezetKapcsol(tartalom, domCel) : undefined;
  });

  // a dokumentum változása (jelölőnégyzet, külső változás) után újrarajzol, kicsit késleltetve
  $effect(() => {
    void valtozat;
    if (kesleltetes) clearTimeout(kesleltetes);
    kesleltetes = setTimeout(rajzol, 120);
  });

  onDestroy(() => {
    if (kesleltetes) clearTimeout(kesleltetes);
    lusta?.leall();
  });
</script>

<div class="olvaso-gorgeto gorgeto" bind:this={gorgeto}>
  <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
  <article
    class="olvaso tipo olvasas md"
    bind:this={tartalom}
    aria-label="Olvasó nézet"
    onclick={kattintas}
    onkeydown={billentyu}
    onchange={valtas}
  ></article>
</div>

<style>
  .olvaso-gorgeto {
    flex: 1;
    min-height: 0;
  }

  .olvaso {
    padding: var(--t-5) var(--t-6) 30vh;
  }
</style>
