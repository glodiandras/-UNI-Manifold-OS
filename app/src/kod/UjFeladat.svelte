<!--
  „Új feladat…” (C36a-UI, F11: a kód-munkafelület bármely nyelvén): név, nyelv és mappa → `POST /api/cpp/feladat` (a core a forrásfájlt és
  a feladat-jegyzetet hozza létre, két commitban); utána a jegyzet nyílik, a forrás osztásban. A felhasználó művelete: gép forrást nem ír (53(d)).
-->
<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { t } from '../lib/i18n';
  import { kornyezet } from '../lib/kornyezet';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import { mappa as mappaja } from '../lib/vault/fajlok.svelte';
  import { KOD_NYELVEK } from '../lib/vault/kodFajl';
  import { ujFeladat } from './muveletek';

  const { felulet, fajlok } = kornyezet();
  const alapMappa = untrack(() => {
    const ut = felulet.munkaterulet.aktivFul?.ut;
    return ut ? mappaja(ut) : '';
  });

  let nev = $state('');
  let hely = $state(alapMappa);
  let nyelv = $state('cpp');
  let folyik = $state(false);
  let hiba = $state<string | null>(null);
  let bevitel: HTMLInputElement | undefined = $state();

  onMount(() => bevitel?.focus());

  function bezar() {
    felulet.atfedes = null;
  }

  async function letrehoz() {
    const n = nev.trim();
    if (!n || folyik) return;
    const m = hely.trim().replace(/^\/+|\/+$/g, '');
    if (m && !fajlok.mappak.includes(m)) {
      hiba = t('Nincs ilyen mappa: {mappa}', { mappa: m });
      return;
    }
    folyik = true;
    hiba = null;
    const r = await ujFeladat(felulet, m, n, nyelv);
    folyik = false;
    if (r.ok) bezar();
    else hiba = r.hiba;
  }

  function billentyu(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.isComposing) {
      e.preventDefault();
      void letrehoz();
    }
  }
</script>

<Atfedes cimke={t('kod.uj_feladat.cim')} nev="cpp-feladat" onbezar={bezar}>
  <div class="doboz">
    <h2 class="cim">{t('kod.uj_feladat.cim')}</h2>
    <label class="mezo">
      <span>{t('Név')}</span>
      <input bind:this={bevitel} bind:value={nev} onkeydown={billentyu} spellcheck="false" autocomplete="off" placeholder={t('pl. Két szám összege')} />
    </label>
    <label class="mezo">
      <span>{t('kod.uj_feladat.nyelv')}</span>
      <select bind:value={nyelv} data-teszt="uj-feladat-nyelv">
        {#each KOD_NYELVEK as n (n.azonosito)}<option value={n.azonosito}>{n.nev}</option>{/each}
      </select>
    </label>
    <label class="mezo">
      <span>{t('Mappa')}</span>
      <input bind:value={hely} onkeydown={billentyu} list="cpp-feladat-mappak" spellcheck="false" autocomplete="off" placeholder={t('(a vault gyökere)')} />
      <datalist id="cpp-feladat-mappak">
        {#each fajlok.mappak as m (m)}<option value={m}></option>{/each}
      </datalist>
    </label>
    <p class="seg">{t('kod.uj_feladat.seg')}</p>
    {#if hiba}<p class="hiba" role="alert">{hiba}</p>{/if}
    <div class="gombok">
      <button type="button" class="m-gomb semleges masodlagos" onclick={bezar}>{t('Mégse')}</button>
      <button type="button" class="m-gomb elso" disabled={!nev.trim() || folyik} onclick={() => void letrehoz()}>
        {folyik ? t('Létrehozás…') : t('Létrehozás')}
      </button>
    </div>
  </div>
</Atfedes>

<style>
  .doboz {
    display: flex;
    flex-direction: column;
    gap: var(--t-3);
    padding: var(--t-4) var(--t-5);
  }

  .cim {
    margin: 0;
    font-size: var(--betu-h4);
  }

  .mezo {
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
    font-size: var(--betu-ui);
    color: var(--szoveg-masodlagos);
  }

  .mezo input,
  .mezo select {
    padding: var(--t-2) var(--t-3);
    border: var(--keret-vastag) solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
  }

  .mezo input:focus-visible,
  .mezo select:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  .seg {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .hiba {
    margin: 0;
    color: var(--hiba);
    font-size: var(--betu-ui);
  }

  .gombok {
    display: flex;
    justify-content: flex-end;
    gap: var(--t-2);
  }

</style>
