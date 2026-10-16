<script lang="ts">
  let { cimke, ertek = $bindable(false), tiltott = false }: { cimke: string; ertek?: boolean; tiltott?: boolean } = $props();
</script>

<button type="button" class="m-kapcsolo" role="switch" aria-label={cimke} aria-checked={ertek} disabled={tiltott} onclick={() => (ertek = !ertek)}>
  <span aria-hidden="true">{ertek ? '✓' : '−'}</span>
</button>

<style>
  .m-kapcsolo { display: inline-grid; place-items: center; width: var(--magassag-mezo); height: var(--magassag-gomb); border: var(--keret-vastag) solid var(--keret-mezo); border-radius: var(--kerekites); background: var(--hatter); color: var(--szoveg); cursor: default; }
  .m-kapcsolo[aria-checked='true'] { background: var(--hatter-kijelolt); border-color: var(--akcent); }
  .m-kapcsolo:hover:not(:disabled) { background: var(--hatter-hover); }
  .m-kapcsolo:disabled { opacity: var(--tiltott-atlatszosag); }
</style>
