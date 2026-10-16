<!--
  Az eszközlánc állapota nyelvenként (F10): a fejlécben egy jelvény (ikon + szó: kész / hiányzik), alatta a hiányzó eszközlánc
  érthető teendője (a core `kod.*` hibakódjának mondata + a telepítési tipp) és az „Újraellenőrzés”; a jelvényre kattintva az
  összes nyelv listája. A felderítést a core végzi (`GET /api/kod/nyelvek`), a felület csak mutatja; semmit nem tölt le (D3).
  Az állapotot sosem csak szín jelzi (ikon + szó), a burgundi sehol nem állapotjelző. Csak tokenből rajzol.
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { Check, CircleAlert, RotateCw } from '../lib/ikon/ikonok';
  import UresAllapot from '../lib/ui/UresAllapot.svelte';
  import { kodNyelvek, nyelvAzonosito } from './nyelvek.svelte';

  let { nyelv, resz }: { nyelv: string | null; resz: 'jel' | 'panel' } = $props();

  $effect(() => {
    kodNyelvek.kellLista();
  });

  const nev = $derived(nyelvAzonosito(nyelv)?.nev ?? nyelv ?? '');
  const elerheto = $derived(kodNyelvek.elerheto(nyelv));
  const teendo = $derived(kodNyelvek.teendo(nyelv));
  const hianyzo = $derived(kodNyelvek.hianyzo(nyelv));
  const lista = $derived(kodNyelvek.lista ?? []);
</script>

{#if resz === 'jel'}
  <button
    type="button"
    class="jelveny"
    class:rossz={elerheto === false}
    class:jo={elerheto === true}
    aria-expanded={kodNyelvek.panelNyitva}
    aria-label={t('Nyelvek és eszközláncok')}
    title={t('Nyelvek és eszközláncok')}
    onclick={() => (kodNyelvek.panelNyitva = !kodNyelvek.panelNyitva)}
  >
    <span class="nev">{nev}</span>
    {#if elerheto === true}
      <Ikon ikon={Check} meret={14} /><span>{t('Eszközlánc kész')}</span>
    {:else if elerheto === false}
      <Ikon ikon={CircleAlert} meret={14} /><span>{t('Eszközlánc hiányzik')}</span>
    {:else if kodNyelvek.hiba}
      <Ikon ikon={CircleAlert} meret={14} /><span>{t('Az eszközlánc állapota nem ismert')}</span>
    {:else}
      <span class="halvany">{t('Eszközlánc ellenőrzése…')}</span>
    {/if}
  </button>
{:else}
  {#if elerheto === false}
    <div class="figy" role="status">
      <Ikon ikon={CircleAlert} meret={16} />
      <div class="figy-szoveg">
        <p class="cim">{t('{nyelv}: az eszközlánc hiányzik', { nyelv: nev })}</p>
        {#if hianyzo.length}<p class="reszlet">{t('Hiányzik: {lista}', { lista: hianyzo.join(', ') })}</p>{/if}
        {#if teendo}<p class="reszlet">{teendo}</p>{/if}
      </div>
      <button type="button" class="m-gomb semleges suru" disabled={kodNyelvek.folyamatban} onclick={() => void kodNyelvek.betolt(true)}>
        <Ikon ikon={RotateCw} meret={14} /> {t('Újraellenőrzés')}
      </button>
    </div>
  {/if}

  {#if kodNyelvek.panelNyitva}
    <section class="lista" aria-label={t('Nyelvek és eszközláncok')}>
      {#if kodNyelvek.hiba && !kodNyelvek.lista}
        <UresAllapot
          kicsi
          ikon={CircleAlert}
          cim={t('Az eszközláncok állapota nem kérdezhető le')}
          leiras={kodNyelvek.hiba}
          muvelet={{ cimke: t('Újraellenőrzés'), onclick: () => void kodNyelvek.betolt(true) }}
        />
      {:else if !kodNyelvek.lista}
        <p class="halvany sor">{t('Eszközlánc ellenőrzése…')}</p>
      {:else}
        <ul>
          {#each lista as n (n.azonosito)}
            <li class:aktualis={n.azonosito === nyelv}>
              <span class="nev">{n.nev}</span>
              <span class="allapot" class:jo={n.elerheto} class:rossz={!n.elerheto}>
                <Ikon ikon={n.elerheto ? Check : CircleAlert} meret={14} />
                {n.elerheto ? t('kész') : t('hiányzik')}
              </span>
              <span class="halvany reszlet">
                {#if n.elerheto}
                  {n.eszkozlanc === 'beagyazott' ? t('beépített eszközlánc') : t('rendszer-eszközlánc')}
                {:else if n.hiba}
                  {kodNyelvek.teendo(n.azonosito)}
                {:else}
                  {n.telepites_tipp}
                {/if}
              </span>
            </li>
          {/each}
        </ul>
        <div class="alja">
          <button type="button" class="m-gomb semleges suru" disabled={kodNyelvek.folyamatban} onclick={() => void kodNyelvek.betolt(true)}>
            <Ikon ikon={RotateCw} meret={14} /> {kodNyelvek.folyamatban ? t('Ellenőrzés…') : t('Újraellenőrzés')}
          </button>
        </div>
      {/if}
    </section>
  {/if}
{/if}

<style>
  .jelveny {
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--magassag-suru);
    padding: 0 var(--t-2);
    border: none;
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter-hover);
    color: var(--szoveg-masodlagos);
    font: inherit;
    font-size: var(--betu-kicsi);
    cursor: pointer;
  }

  .jelveny.jo {
    color: var(--siker);
    background: var(--siker-hatter);
  }

  .jelveny.rossz {
    color: var(--hiba);
    background: var(--hiba-hatter);
  }

  .jelveny .nev {
    font-weight: var(--suly-kozepes);
  }

  .jelveny:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  .halvany {
    color: var(--szoveg-halvany);
  }

  .figy {
    flex: none;
    display: flex;
    align-items: flex-start;
    gap: var(--t-2);
    padding: var(--t-2) var(--t-4);
    border-top: 1px solid var(--keret);
    background: var(--figyelmeztetes-hatter);
    color: var(--figyelmeztetes);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
  }

  .figy-szoveg {
    flex: 1 1 auto;
    min-width: 0;
    color: var(--szoveg);
  }

  .figy p {
    margin: 0;
  }

  .cim {
    font-weight: var(--suly-kozepes);
  }

  .reszlet {
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-masodlagos);
  }

  .lista {
    flex: none;
    max-height: 40%;
    overflow: auto;
    border-top: 1px solid var(--keret);
    background: var(--hatter-emelt);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
  }

  .lista ul {
    list-style: none;
    margin: 0;
    padding: var(--t-1) var(--t-3);
  }

  .lista li {
    display: grid;
    grid-template-columns: 7em 8em minmax(0, 1fr);
    align-items: baseline;
    gap: var(--t-2);
    padding: var(--t-1) var(--t-2);
    border-radius: var(--kerekites-kicsi);
  }

  .lista li.aktualis {
    background: var(--hatter-hover);
  }

  .lista .nev {
    font-weight: var(--suly-kozepes);
  }

  .allapot {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    font-size: var(--betu-kicsi);
  }

  .allapot.jo {
    color: var(--siker);
  }

  .allapot.rossz {
    color: var(--hiba);
  }

  .sor {
    margin: 0;
    padding: var(--t-2) var(--t-4);
  }

  .alja {
    padding: var(--t-1) var(--t-4) var(--t-2);
  }
</style>
