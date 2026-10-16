<!--
  „Reset demo” (F11): csak a demo munkatérben látszik (`GET /api/demo/allapot` → `demo: true`), megerősítéssel, a
  `POST /api/demo/alaphelyzet {megerosit: true}` végponton. A core előbb pillanatképet készít, a hozzáadott jegyzeteket
  félreteszi (nem törli). A hiba ikonnal és szóval jelenik meg; a szín nem hordoz jelentést.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { hibaUzenet, kerdez } from '../lib/core/api';
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { CircleAlert, CircleCheck } from '../lib/ikon/ikonok';

  interface Eredmeny { visszaallitva: number; ujra_letrehozva: number; felretett: string[] }

  let demo = $state(false);
  let kerdes = $state(false);
  let folyik = $state(false);
  let eredmeny = $state<Eredmeny | null>(null);
  let hiba = $state<string | null>(null);

  onMount(() => {
    void (async () => {
      try {
        demo = (await kerdez<{ demo: boolean }>('/api/demo/allapot')).demo === true;
      } catch {
        demo = false; // nincs állapot: nem mutatunk alaphelyzet-gombot (a felhasználói munkatérben soha nem jelenhet meg)
      }
    })();
  });

  async function alaphelyzet() {
    if (folyik) return;
    folyik = true;
    hiba = null;
    eredmeny = null;
    try {
      eredmeny = await kerdez<Eredmeny>('/api/demo/alaphelyzet', { metodus: 'POST', torzs: { megerosit: true }, idokorlat: 300_000 });
      kerdes = false;
    } catch (e) {
      hiba = hibaUzenet(e);
      kerdes = false;
    } finally {
      folyik = false;
    }
  }
</script>

{#if demo}
  <div class="demo" data-demo-alaphelyzet>
    <p class="cim">{t('demo.alaphelyzet.cim')}</p>
    <p class="leiras">{t('demo.alaphelyzet.leiras')}</p>
    {#if kerdes}
      <div class="megerosites" role="alertdialog" aria-labelledby="demo-megerosites-cim" aria-describedby="demo-megerosites-leiras">
        <p id="demo-megerosites-cim" class="cim">{t('demo.alaphelyzet.megerosites_cim')}</p>
        <p id="demo-megerosites-leiras" class="leiras">{t('demo.alaphelyzet.megerosites')}</p>
        <div class="gombok">
          <button class="m-gomb" type="button" data-demo-megerosit disabled={folyik} onclick={alaphelyzet}>{folyik ? t('demo.alaphelyzet.folyamatban') : t('demo.alaphelyzet.gomb')}</button>
          <button class="m-gomb semleges" type="button" data-demo-megse disabled={folyik} onclick={() => (kerdes = false)}>{t('demo.alaphelyzet.megse')}</button>
        </div>
      </div>
    {:else}
      <button class="m-gomb semleges" type="button" data-demo-gomb onclick={() => { kerdes = true; eredmeny = null; hiba = null; }}>{t('demo.alaphelyzet.gomb')}</button>
    {/if}
    {#if eredmeny}
      <p class="siker" role="status"><Ikon ikon={CircleCheck} /> <span>{t('A demó alaphelyzetre állt: {visszaallitva} visszaállítva vagy újra létrehozva, {felretett} félretéve.', { visszaallitva: eredmeny.visszaallitva + eredmeny.ujra_letrehozva, felretett: eredmeny.felretett.length })}</span></p>
    {/if}
    {#if hiba}
      <p class="hiba" role="alert"><Ikon ikon={CircleAlert} /> <span>{t('A demót nem sikerült alaphelyzetre állítani: {uzenet}', { uzenet: hiba })}</span></p>
    {/if}
  </div>
{/if}

<style>
  .demo { display: flex; flex-direction: column; gap: var(--t-2); padding: var(--t-3); border: var(--keret-vastag) solid var(--keret); border-radius: var(--kerekites); }
  .megerosites { display: flex; flex-direction: column; gap: var(--t-2); }
  .cim { margin: 0; font-weight: var(--suly-kozepes); }
  .leiras { margin: 0; color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .gombok { display: flex; flex-wrap: wrap; gap: var(--t-2); }
  .siker, .hiba { display: flex; align-items: center; gap: var(--t-2); margin: 0; }
  .siker { color: var(--siker); }
  .hiba { color: var(--hiba); }
</style>
