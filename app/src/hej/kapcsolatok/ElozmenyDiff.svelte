<!--
  Egy változat összevetése (C11b): kétoldalas, csak olvasható diff a `@codemirror/merge`-gyel — az előző változat és ez,
  vagy ez és a jelenlegi. Innen indul a visszaállítás is („Visszaállítás erre a verzióra”, megerősítés után).
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import type { MergeView } from '@codemirror/merge';
  import { onDestroy, onMount } from 'svelte';
  import Ikon from '../../lib/ikon/Ikon.svelte';
  import { RotateCcw } from '../../lib/ikon/ikonok';
  import Atfedes from '../../lib/ui/Atfedes.svelte';
  import { elozmenyApi, elozmenyIdo, visszaallitasOka, type ElozmenyBejegyzes, type ElozmenyValtozat } from '../../lib/vault/elozmeny';
  import { vaultApi } from '../../szerkeszto/dokumentum/api';
  import { szerkesztok } from '../../szerkeszto/szerkesztok.svelte';
  import { lf, mergeNezet } from './mergeNezet';

  let {
    ut,
    bejegyzes,
    legujabb,
    onbezar,
    onvisszaallit,
  }: {
    ut: string;
    bejegyzes: ElozmenyBejegyzes;
    legujabb: boolean;
    onbezar: () => void;
    onvisszaallit: (b: ElozmenyBejegyzes) => Promise<boolean>;
  } = $props();

  type Mod = 'elozo' | 'jelenlegi';
  let mod = $state<Mod>('elozo');
  let valtozat = $state.raw<ElozmenyValtozat | null>(null);
  let jelenlegi = $state<string | null>(null);
  let hiba = $state<string | null>(null);
  let megerosit = $state(false);
  let dolgozik = $state(false);
  let hely: HTMLDivElement | undefined = $state();
  let merge: MergeView | null = null;

  const oka = $derived(visszaallitasOka(bejegyzes, legujabb));

  onMount(() => {
    elozmenyApi.valtozat(ut, bejegyzes.sha).then(
      (v) => (valtozat = v),
      (e) => (hiba = e instanceof Error ? e.message : String(e)),
    );
    // a jelenlegi szöveg: a nyitott dokumentumé (mentetlen is), különben a lemezé
    const dok = szerkesztok.dokumentumok.kap(ut);
    if (dok) jelenlegi = dok.fajlSzoveg();
    else vaultApi().olvas(ut).then((f) => (jelenlegi = f.tartalom), () => (jelenlegi = ''));
  });

  onDestroy(() => merge?.destroy());

  const bal = $derived(mod === 'elozo' ? valtozat?.elozo : valtozat?.szoveg);
  const jobb = $derived(mod === 'elozo' ? valtozat?.szoveg : jelenlegi);
  const kesz = $derived(!!valtozat && (mod === 'elozo' || jelenlegi !== null));

  $effect(() => {
    if (!hely || !kesz) return;
    const a = lf(bal ?? null);
    const b = lf(jobb ?? null);
    merge?.destroy();
    merge = mergeNezet(hely, a, b);
    return () => {
      merge?.destroy();
      merge = null;
    };
  });

  const balCim = $derived(
    mod === 'elozo' ? (valtozat?.elozo_ok === 'nincs' || !bejegyzes.elozo ? t('Még nem létezett') : t('Az előző változat')) : t('Ez a változat'),
  );
  const jobbCim = $derived(mod === 'elozo' ? t('Ez a változat') : t('A jelenlegi (a szerkesztőben)'));

  async function visszaallit() {
    dolgozik = true;
    const ok = await onvisszaallit(bejegyzes);
    dolgozik = false;
    if (ok) onbezar();
    else megerosit = false;
  }

  const megjegyzes = $derived.by(() => {
    if (!valtozat) return '';
    const o = valtozat.szoveg_ok;
    if (o === 'kodolas') return t('A változat nem érvényes UTF-8, az összevetés nem érhető el.');
    if (o === 'nagy') return t('A változat túl nagy az összevetéshez.');
    if (o === 'nincs' && bejegyzes.statusz === 'D') return t('Ebben a pillanatképben a jegyzet törölve lett.');
    return '';
  });
</script>

<Atfedes cimke={t('A jegyzet egy korábbi változata')} nev="elozmeny" {onbezar} szeles>
  <div class="diff">
    <header class="fej">
      <div class="cim">
        <h2>{bejegyzes.cimke}</h2>
        <p>{elozmenyIdo(bejegyzes.datum)}{bejegyzes.kor ? ` · ${bejegyzes.kor}` : ''}{bejegyzes.regi_ut ? ` · ${t('átnevezve: {regi} → {uj}', { regi: bejegyzes.regi_ut, uj: bejegyzes.ut_akkor })}` : ''}</p>
      </div>
      <div class="mod" role="group" aria-label={t('Összevetés')}>
        <button type="button" aria-pressed={mod === 'elozo'} onclick={() => (mod = 'elozo')}>{t('az előzővel')}</button>
        <button type="button" aria-pressed={mod === 'jelenlegi'} onclick={() => (mod = 'jelenlegi')}>{t('a jelenlegivel')}</button>
      </div>
    </header>

    {#if hiba}<p class="hiba" role="alert">{hiba}</p>{/if}
    {#if megjegyzes}<p class="megjegyzes" role="status">{megjegyzes}</p>{/if}

    <div class="oszlopfej" aria-hidden="true"><span>{balCim}</span><span>{jobbCim}</span></div>
    <div class="merge" bind:this={hely}>
      {#if !valtozat && !hiba}<p class="toltes" role="status">{t('Betöltés…')}</p>{/if}
    </div>

    <footer class="gombok">
      {#if megerosit}
        <p class="figy">{t('A jegyzet erre a változatra áll vissza; a mostani szöveg az előzményekben megmarad, és a visszaállítás is visszavonható.')}</p>
        <button type="button" class="m-gomb semleges gomb" disabled={dolgozik} onclick={() => (megerosit = false)}>{t('Mégse')}</button>
        <button type="button" class="m-gomb gomb elsodleges" disabled={dolgozik} onclick={visszaallit}>{t('Visszaállítás')}</button>
      {:else}
        <button type="button" class="m-gomb semleges gomb" onclick={onbezar}>{t('Bezárás')}</button>
        <button
          type="button"
          class="m-gomb gomb elsodleges"
          disabled={!!oka || !valtozat}
          title={oka ?? undefined}
          onclick={() => (megerosit = true)}
        >
          <Ikon ikon={RotateCcw} meret={14} /> {t('Visszaállítás erre a verzióra')}
        </button>
      {/if}
    </footer>
  </div>
</Atfedes>

<style>
  .diff {
    display: flex;
    flex-direction: column;
    gap: var(--t-3);
    flex: 1;
    min-height: 0;
    padding: var(--t-5);
  }

  .fej {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--t-4);
  }

  h2 {
    font-size: var(--betu-torzs);
    line-height: var(--magassag-suru);
    font-weight: var(--suly-felkover);
  }

  p {
    margin: var(--t-1) 0 0;
    color: var(--szoveg-masodlagos);
  }

  .mod {
    display: flex;
    flex: none;
    padding: 2px;
    border-radius: var(--kerekites);
    background: var(--hatter-oldalsav);
  }

  .mod button {
    height: var(--magassag-suru);
    padding: 0 var(--t-3);
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-ui);
  }

  .mod button[aria-pressed='true'] {
    background: var(--hatter-aktiv);
    color: var(--szoveg);
  }

  .oszlopfej {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--t-4);
    font-size: var(--betu-kicsi);
    color: var(--szoveg-halvany);
  }

  .merge {
    flex: 1;
    min-height: 280px;
    overflow: auto;
    border: var(--keret-vastag) solid var(--keret);
    border-radius: var(--kerekites);
  }

  .toltes,
  .megjegyzes {
    margin: 0;
    padding: var(--t-3);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .hiba {
    color: var(--hiba);
  }

  .gombok {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: var(--t-2);
  }

  .figy {
    flex: 1;
    margin: 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--figyelmeztetes);
  }

  .gomb {
    display: inline-flex;
    align-items: center;
    gap: var(--t-2);
  }

</style>
