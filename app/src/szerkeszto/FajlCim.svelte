<script lang="ts">
  import { fajlNev, mappa } from '../lib/vault/fajlok.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import { szerkesztok } from './szerkesztok.svelte';
  import { atnevezesTerv, atnevezesVegrehajt, atnevezesErtesites } from './linkek/atnevezes';
  let { ut, irhato = true }: { ut: string; irhato?: boolean } = $props();
  const { felulet } = kornyezet();
  let dolgozik = $state(false);
  let hiba = $state('');

  async function ment(mezo: HTMLInputElement) {
    const nev = mezo.value.trim();
    if (nev === fajlNev(ut) || dolgozik) return;
    if (!nev) { mezo.value = fajlNev(ut); return; }
    dolgozik = true;
    hiba = '';
    try {
      await szerkesztok.dokumentumok.mindLezar();
      const uj = [mappa(ut), nev + (nev.toLowerCase().endsWith('.md') ? '' : '.md')].filter(Boolean).join('/');
      const t = await atnevezesTerv(ut, uj);
      if (!t.ok) throw new Error(t.blokkolok.join(' '));
      const r = await atnevezesVegrehajt(ut, uj, t.terv_hash);
      atnevezesErtesites(r, felulet);
    } catch (e) {
      hiba = e instanceof Error ? e.message : String(e);
      mezo.value = fajlNev(ut);
    } finally { dolgozik = false; }
  }
</script>

<div class="fajlcim">
  <input aria-label="Jegyzet fájlneve" title="Fájlnév szerkesztése — a tartalom címsora ettől független"
    value={fajlNev(ut)} disabled={!irhato || dolgozik} spellcheck="false"
    onblur={(e) => void ment(e.currentTarget)}
    onkeydown={(e) => {
      if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur(); }
      if (e.key === 'Escape') { e.preventDefault(); e.currentTarget.value = fajlNev(ut); e.currentTarget.blur(); }
    }} />
  {#if hiba}<p class="hiba" role="alert">{hiba}</p>{/if}
</div>

<style>
  .fajlcim { width: 100%; max-width: var(--olvasasi-szelesseg); margin: 0 auto; padding: var(--t-2) var(--t-6); box-sizing: border-box; }
  input { width: 100%; border: 0; background: transparent; color: var(--szoveg); font: inherit;
    font-size: var(--betu-h2); font-weight: var(--suly-felkover); padding: var(--t-1) 0; }
  .hiba { color: var(--hiba); font-size: var(--betu-kicsi); }
</style>
