<script lang="ts">
  import type { EditorView } from '@codemirror/view';
  import type { LinkForras } from './javaslat';
  import Tulajdonsagok from './Tulajdonsagok.svelte';
  let { view, ut, valtozat, nyitottsag, kiegeszites, hiba, jelez }: {
    view: EditorView; ut: string; valtozat: number;
    nyitottsag: { nyitva: boolean }; kiegeszites?: LinkForras;
    /** CX-006: a core szerint formai hibás frontmatter oka; ilyenkor a nyers YAML alatta szerkeszthető */
    hiba: string | null;
    jelez: (hiba: string | null) => void;
  } = $props();
</script>

{#if hiba}
  <p class="hiba" role="alert">A frontmatter formai hibás: {hiba}. A nyers szöveg alább szerkeszthető.</p>
{/if}
<div hidden={!!hiba}>
  <Tulajdonsagok {ut} {valtozat} {kiegeszites}
    szoveg={() => view.state.doc}
    alkalmaz={(c) => view.dispatch({ changes: c, userEvent: 'input.tulajdonsag' })}
    onelemzes={(e) => jelez(e.van ? e.hiba : null)}
    irhato={!view.state.readOnly} bind:nyitva={nyitottsag.nyitva} />
</div>

<style>
  .hiba { margin: 0; padding: var(--t-2) 0; color: var(--hiba); font-size: var(--betu-kicsi); }
</style>
