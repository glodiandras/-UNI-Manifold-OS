<!--
  Egy feladat részlete a vezérlő lapján (C17): állapot és haladás, leállítás, napló, „Mit változtatott”. A napló csak
  akkor kérdez, ha a feladat fut és az ablak látszik (2 s); a változások a feladat végén és a visszavonásra töltődnek újra.
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import { onMount, tick, untrack } from 'svelte';
  import { ApiHiba } from '../../lib/core/api';
  import Ikon from '../../lib/ikon/Ikon.svelte';
  import { ChevronLeft, Square } from '../../lib/ikon/ikonok';
  import { feladatsor } from '../../lib/vezerlo/feladatsor.svelte';
  import { vezerloApi } from '../../lib/vezerlo/api';
  import { egyszerre, naploHozzafuz, type NaploAllapot } from '../../lib/vezerlo/naplo';
  import { allapotCimke, feladatHiba, feladatSzoveg, haladasSzoveg, idoRovid, idotartam } from '../../lib/vezerlo/megjelenites';
  import type { Feladat } from '../../lib/vezerlo/tipusok';
  import Valtozasok from './Valtozasok.svelte';

  let { id, vissza }: { id: string; vissza: () => void } = $props();

  let betoltott = $state.raw<Feladat | null>(null);
  let naplo = $state.raw<NaploAllapot>({ sorok: [], tol: 0, levagva: 0 });
  const sorok = $derived(naplo.sorok);
  let hiba = $state<string | null>(null);
  let megerosit = $state(false);
  let dolgozik = $state(false);
  let naploEl: HTMLElement | undefined = $state();

  const feladat = $derived(feladatsor.kap(id) ?? betoltott);
  const fut = $derived(feladat?.allapot === 'fut');
  const sorban = $derived(feladat?.allapot === 'sorban');

  // egyszerre egy kérés (a 2 s-os lekérdezés, az állapot-effekt és a mount átfedhet); az elavult `tol` válasza eldobódik
  const naploFrissit = egyszerre(async () => {
    try {
      const kertTol = naplo.tol;
      const d = await vezerloApi.reszlet(id, kertTol);
      betoltott = d;
      const uj = naploHozzafuz(naplo, kertTol, d);
      if (uj) {
        const aljan = !naploEl || naploEl.scrollHeight - naploEl.scrollTop - naploEl.clientHeight < 24;
        naplo = uj;
        if (aljan) {
          await tick();
          if (naploEl) naploEl.scrollTop = naploEl.scrollHeight;
        }
      }
      hiba = null;
    } catch (e) {
      hiba = e instanceof ApiHiba && e.statusz === 404 ? t('Ez a feladat már nincs a listában.') : e instanceof Error ? e.message : String(e);
    }
  });

  onMount(() => {
    void naploFrissit();
    const t = setInterval(() => {
      if (feladat?.allapot === 'fut' && document.visibilityState === 'visible') void naploFrissit();
    }, 2000);
    return () => clearInterval(t);
  });

  // az állapotváltozáskor (indul, véget ér) a napló is frissül
  let elozo = '';
  $effect(() => {
    const a = feladat?.allapot ?? '';
    if (elozo && a !== elozo) untrack(() => void naploFrissit());
    elozo = a;
  });

  async function leallit(azonnal: boolean) {
    dolgozik = true;
    hiba = null;
    try {
      await vezerloApi.leallit(id, azonnal);
      megerosit = false;
      await feladatsor.betolt();
    } catch (e) {
      hiba = e instanceof Error ? e.message : String(e);
    } finally {
      dolgozik = false;
    }
  }
</script>

<div class="reszlet">
  <button type="button" class="vissza" onclick={vissza}><Ikon ikon={ChevronLeft} meret={14} /> {t('Feladatok')}</button>
  {#if !feladat}
    {#if hiba}<p class="hiba" role="alert">{hiba}</p>{:else}<p class="halvany" role="status">{t('Betöltés…')}</p>{/if}
  {:else}
    <h3 class="cim">{feladatSzoveg(feladat.cim)}</h3>
    <p class="meta">
      <span class="allapot" data-allapot={feladat.allapot}>{allapotCimke(feladat.allapot)}</span>
      {#if fut || sorban}{haladasSzoveg(feladat)}{:else}{idoRovid(feladat.vegzett)}{idotartam(feladat) ? ` · ${idotartam(feladat)}` : ''}{/if}
    </p>
    {#if fut}
      <div class="sav" role="progressbar" aria-label={t('Haladás')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(feladat.szazalek)}>
        <span style:width="{Math.max(2, feladat.szazalek)}%"></span>
      </div>
    {/if}
    {#if feladat.osszegzes}<p class="halvany">{feladatSzoveg(feladat.osszegzes)}</p>{/if}
    {#each feladat.figyelmeztetes as f (f)}<p class="figy">{feladatSzoveg(f)}</p>{/each}
    {#if feladat.hiba}<p class="hiba" role="alert">{feladatHiba(feladat)}</p>{/if}
    {#if hiba && feladat}<p class="hiba" role="alert">{hiba}</p>{/if}

    {#if fut || sorban}
      <div class="gombok">
        {#if megerosit}
          <span class="figy">{t('Azonnal leáll, a folyamatban lévő tétel megszakad.')}</span>
          <button type="button" class="m-gomb semleges gomb" disabled={dolgozik} onclick={() => (megerosit = false)}>{t('Mégse')}</button>
          <button type="button" class="m-gomb semleges gomb veszely" disabled={dolgozik} onclick={() => leallit(true)}>{t('Azonnali leállítás')}</button>
        {:else if sorban}
          <button type="button" class="m-gomb semleges gomb" disabled={dolgozik} onclick={() => leallit(false)}>{t('Törlés a sorból')}</button>
        {:else}
          <button
            type="button"
            class="m-gomb semleges gomb"
            disabled={dolgozik || feladat.leallitas_kerve}
            title={feladat.kulturalt_stop ? t('A folyamatban lévő tétel végén áll meg') : t('Azonnal leáll')}
            onclick={() => (feladat.kulturalt_stop ? leallit(false) : (megerosit = true))}
          >
            <Ikon ikon={Square} meret={14} /> {feladat.leallitas_kerve ? t('Leállítás kérve…') : t('Leállítás')}
          </button>
          {#if feladat.kulturalt_stop && !feladat.leallitas_kerve}
            <button type="button" class="m-gomb semleges gomb" disabled={dolgozik} onclick={() => (megerosit = true)}>{t('Azonnal…')}</button>
          {/if}
        {/if}
      </div>
    {/if}

    <h4 class="alcim">{t('Mit változtatott')}</h4>
    <Valtozasok {feladat} />

    <h4 class="alcim">{t('Napló')}</h4>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <pre class="naplo gorgeto" bind:this={naploEl} tabindex="0" aria-label={t('A feladat naplója')}>{sorok.length ? (naplo.levagva ? `${t('… (a korábbi {n} sor nem látszik)', { n: naplo.levagva })}\n` : '') + sorok.join('\n') : feladat.forras !== '2.0' ? t('Ehhez a feladathoz nincs elérhető napló.') : t('Még nincs naplósor.')}</pre>
  {/if}
</div>

<style>
  .reszlet {
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
  }

  .vissza {
    align-self: flex-start;
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--magassag-sor);
    padding: 0 var(--t-2) 0 var(--t-1);
    margin-left: calc(-1 * var(--t-1));
    border-radius: var(--kerekites);
    color: var(--szoveg-masodlagos);
  }

  .vissza:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .cim {
    margin: 0;
    font-size: var(--betu-torzs);
    line-height: var(--magassag-suru);
    font-weight: var(--suly-felkover);
  }

  .meta {
    margin: 0;
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-kicsi);
    font-variant-numeric: tabular-nums;
  }

  .allapot {
    font-weight: var(--suly-felkover);
    margin-right: var(--t-1);
  }

  [data-allapot='kesz'] {
    color: var(--siker);
  }

  [data-allapot='hiba'] {
    color: var(--hiba);
  }

  [data-allapot='megszakadt'],
  [data-allapot='megallitva'] {
    color: var(--figyelmeztetes);
  }

  .sav {
    height: 4px;
    border-radius: var(--kerekites-jel);
    background: var(--hatter-aktiv);
    overflow: hidden;
  }

  .sav span {
    display: block;
    height: 100%;
    background: var(--akcent);
    transition: width var(--mozgas-alap) var(--mozgas-gorbe);
  }

  .halvany {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .figy {
    margin: 0;
    color: var(--figyelmeztetes);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    flex: 1;
  }

  .hiba {
    margin: 0;
    padding: var(--t-2);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
    font-size: var(--betu-kicsi);
  }

  .gombok {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--t-2);
  }

  .gomb {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
  }

  .gomb.veszely {
    border-color: var(--hiba);
    color: var(--hiba);
  }

  .alcim {
    margin: var(--t-3) 0 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-weight: var(--suly-felkover);
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--szoveg-halvany);
  }

  .naplo {
    margin: 0;
    max-height: 260px;
    padding: var(--t-2);
    overflow: auto;
    border-radius: var(--kerekites);
    background: var(--hatter-kod);
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    color: var(--szoveg-masodlagos);
  }
</style>
