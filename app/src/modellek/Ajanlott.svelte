<!--
  „Install recommended models now”: az ajánlott modellek közül a még hiányzók letöltése — a felhasználó kattintására (D3), a
  teljes méret kiírva. A Model Manager és a Setup „AI” lépése is ezt használja. Az állapot szöveggel jön; a hibát a modell sora mutatja.
-->
<script lang="ts">
  import { Download } from 'lucide';
  import { t, tk } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import type { ModellTar } from '../lib/modellek/allapot.svelte';
  import { gbSzoveg } from '../lib/modellek/megjelenites';

  let { tar, most = false, onindult }: { tar: ModellTar; /** a Setup-lépés felirata: „…now” */ most?: boolean; onindult?: (db: number) => void } = $props();
  const CIMKE = { alap: tk('modellek.ajanlott.gomb'), most: tk('modellek.ajanlott.gomb_most') };
  let indul = $state(false);
  let indult = $state<number | null>(null);

  const futoDb = $derived(tar.modellek.filter((m) => m.ajanlott && !!tar.aktiv(m, 'letoltes')).length);

  async function telepit() {
    indul = true;
    try {
      indult = await tar.ajanlottTelepit();
      onindult?.(indult);
    } finally {
      indul = false;
    }
  }
</script>

<div class="ajanlott" data-ajanlott>
  {#if tar.ajanlottOsszes === 0}
    <p class="halvany">{t('modellek.ajanlott.nincs')}</p>
  {:else if tar.ajanlottHianyzik.length === 0 && futoDb === 0}
    <p class="allapot" role="status">{t('Mind a(z) {db} ajánlott modell telepítve van.', { db: tar.ajanlottKesz })}</p>
  {:else}
    <p class="halvany">{t('{kesz} / {osszes} ajánlott modell telepítve.', { kesz: tar.ajanlottKesz, osszes: tar.ajanlottOsszes })}</p>
    {#if futoDb > 0}<p role="status">{t('Folyamatban lévő ajánlott letöltések: {db}.', { db: futoDb })}</p>{/if}
    {#if tar.ajanlottHianyzik.length > 0}
      <div>
        <button type="button" class="m-gomb" disabled={indul} onclick={() => void telepit()}><Ikon ikon={Download} />{most ? t(CIMKE.most) : t(CIMKE.alap)}</button>
        <span class="halvany meret">{t('{db} modell · {meret}', { meret: gbSzoveg(tar.ajanlottGb), db: tar.ajanlottHianyzik.length })}</span>
      </div>
      <p class="halvany">{t('modellek.ajanlott.csak_kattintasra')}</p>
    {/if}
  {/if}
</div>

<style>
  .ajanlott { display: flex; flex-direction: column; gap: var(--t-2); }
  p { margin: 0; }
  .halvany { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); line-height: var(--sor-kicsi); }
  .meret { margin-inline-start: var(--t-3); }
</style>
