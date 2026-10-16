<!--
  Health (F7): az alkalmazás állapota ellenőrzésenként. Minden sorban: Diagnose (részletek, csak olvas), Fix (biztonságos,
  visszafordítható gépi javítás vagy kézi lépés) és Learn more. Az állapot sosem csak szín: ikon + szó. Developer módban a
  nyers diagnosztika (a doctor szövege, a teljes JSON) is látszik.
-->
<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { fejlesztoMod } from '../lib/beallitasok/fejleszto';
  import { egeszseg as alapTar, type EgeszsegTar } from '../lib/egeszseg/allapot.svelte';
  import { ALLAPOT_SZOVEG, CIM, JAVITAS_KEZI, JAVITAS_LEIRAS, RESZLET_CIM, TUDJ_ALTALANOS, TUDJ_MEG } from '../lib/egeszseg/szoveg';
  import type { EgeszsegAllapot, EgeszsegSor } from '../lib/egeszseg/tipusok';
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { CircleAlert, CircleCheck, Info, TriangleAlert } from '../lib/ikon/ikonok';
  import DokuSzakasz from '../lib/egeszseg/DokuSzakasz.svelte';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import HibaPanel from '../lib/ui/HibaPanel.svelte';
  import UresAllapot from '../lib/ui/UresAllapot.svelte';

  let { tar = alapTar, kod = null, onbezar, onjegyzet }: { tar?: EgeszsegTar; kod?: string | null; onbezar: () => void; onjegyzet?: (ut: string) => void } = $props();
  let szakaszNyitva = $state<Record<string, boolean>>({});

  const IKON = { ok: CircleCheck, info: Info, figyelem: TriangleAlert, hiba: CircleAlert } as const;
  let nyitva = $state<Record<string, 'diagnosztika' | 'javitas' | 'tudj' | undefined>>({});
  let cimElem: HTMLHeadingElement | undefined = $state();
  const adat = $derived(tar.adat);
  const osszegzes = $derived(
    !adat ? '' : adat.osszesen.hiba ? t('egeszseg.osszegzes.hiba') : adat.osszesen.figyelem ? t('egeszseg.osszegzes.figyelem') : t('egeszseg.osszegzes.ok'),
  );
  const osszIkon = $derived(!adat ? Info : adat.osszesen.hiba ? CircleAlert : adat.osszesen.figyelem ? TriangleAlert : CircleCheck);

  onMount(() => {
    void (async () => {
      await tar.betolt();
      if (kod) await valt(kod, 'diagnosztika');
      await tick();
      cimElem?.focus();
    })();
  });

  async function valt(k: string, mod: 'diagnosztika' | 'javitas' | 'tudj') {
    if (nyitva[k] === mod) { nyitva[k] = undefined; return; }
    nyitva[k] = mod;
    if (mod === 'diagnosztika') await tar.diagnosztika(k);
    if (mod === 'tudj') await tar.tudjMeg(k);
  }
  const cim = (s: EgeszsegSor) => (CIM[s.kod] ? t(CIM[s.kod]) : s.cim);
  const allapotSzo = (a: EgeszsegAllapot) => t(ALLAPOT_SZOVEG[a]);
  const reszletCim = (k: string) => (RESZLET_CIM[k] ? t(RESZLET_CIM[k]) : fejlesztoMod() ? k : '');
  const lathatoReszletek = (s: EgeszsegSor) => s.reszletek.map((r) => ({ ...r, cim: reszletCim(r.kulcs) })).filter((r) => r.cim);
  const ertek = (v: unknown) => (typeof v === 'boolean' ? (v ? t('egeszseg.igen') : t('egeszseg.nem')) : String(v ?? '–'));
  const problema = (s: EgeszsegSor) => s.allapot === 'figyelem' || s.allapot === 'hiba';
</script>

<Atfedes cimke={t('egeszseg.cim')} nev="egeszseg" {onbezar} szeles>
  <header>
    <h1 tabindex="-1" bind:this={cimElem}>{t('egeszseg.cim')}</h1>
    <div class="fej-gombok">
      <button type="button" class="m-gomb semleges" disabled={tar.betoltes} onclick={() => tar.betolt()}>{t('egeszseg.ujra')}</button>
      <button type="button" class="m-gomb semleges" onclick={onbezar}>{t('egeszseg.bezar')}</button>
    </div>
  </header>
  <div class="tartalom">
    {#if tar.betoltes && !adat}<p role="status">{t('egeszseg.betoltes')}</p>{/if}
    {#if tar.hiba && !adat}
      <HibaPanel mi={tar.hiba} javitas={t('egeszseg.nem_elerheto_javitas')} ujra={() => tar.betolt()} />
    {/if}
    {#if adat}
      <p class="osszegzes" role="status"><Ikon ikon={osszIkon} /> <span>{osszegzes}</span></p>
      <p class="leiras">{t('egeszseg.leiras')}</p>
      {#if tar.eredmeny}<p class="siker" role="status"><Ikon ikon={CircleCheck} /> <span>{tar.eredmeny.uzenet}</span></p>{/if}
      {#if tar.javitasHiba}<p class="hiba" role="alert">{tar.javitasHiba}</p>{/if}
      {#if adat.ellenorzesek.length === 0}
        <UresAllapot ikon={Info} cim={t('egeszseg.ures_cim')} leiras={t('egeszseg.ures_leiras')} muvelet={{ cimke: t('egeszseg.ujra'), onclick: () => tar.betolt() }} />
      {/if}
      <ul class="lista" role="list">
        {#each adat.ellenorzesek as s (s.kod + s.uzenet_kod)}
          <li class="sor {s.allapot}" data-ellenorzes={s.kod} data-allapot={s.allapot}>
            <div class="sor-fej">
              <span class="allapot-jel"><Ikon ikon={IKON[s.allapot]} /><span class="allapot-szo">{allapotSzo(s.allapot)}</span></span>
              <h2>{cim(s)}</h2>
            </div>
            <p class="uzenet">{s.uzenet}</p>
            <div class="gombok">
              <button type="button" class="m-gomb semleges suru" aria-expanded={nyitva[s.kod] === 'diagnosztika'} onclick={() => valt(s.kod, 'diagnosztika')}>{t('egeszseg.diagnosztika')}</button>
              {#if problema(s) || s.javitas}<button type="button" class="m-gomb semleges suru" aria-expanded={nyitva[s.kod] === 'javitas'} onclick={() => valt(s.kod, 'javitas')}>{t('egeszseg.javitas')}</button>{/if}
              <button type="button" class="m-gomb semleges suru" aria-expanded={nyitva[s.kod] === 'tudj'} onclick={() => valt(s.kod, 'tudj')}>{t('egeszseg.tudj_meg')}</button>
            </div>
            {#if nyitva[s.kod] === 'diagnosztika'}
              <div class="panel" data-panel="diagnosztika">
                {#if lathatoReszletek(s).length}
                  <dl>{#each lathatoReszletek(s) as r}<dt>{r.cim}</dt><dd>{ertek(r.ertek)}</dd>{/each}</dl>
                {:else}<p class="leiras">{t('egeszseg.nincs_reszlet')}</p>{/if}
                {#if fejlesztoMod()}<pre class="nyers" data-nyers>{s.nyers ? s.nyers + '\n' : ''}{JSON.stringify(s, null, 2)}</pre>{/if}
              </div>
            {:else if nyitva[s.kod] === 'javitas'}
              <div class="panel" data-panel="javitas">
                {#if s.javitas}
                  <HibaPanel
                    mi={s.uzenet}
                    javitas={t(JAVITAS_LEIRAS[s.javitas] ?? JAVITAS_KEZI[s.kod])}
                    automatikus={async () => { const r = await tar.javit(s.javitas!); return r?.uzenet; }}
                    diagnosztika={() => valt(s.kod, 'diagnosztika')}
                  />
                {:else if problema(s)}
                  <HibaPanel mi={s.uzenet} javitas={t(JAVITAS_KEZI[s.kod])} diagnosztika={() => valt(s.kod, 'diagnosztika')} />
                {:else}
                  <p class="leiras">{t('egeszseg.nincs_teendo')}</p>
                {/if}
              </div>
            {:else if nyitva[s.kod] === 'tudj'}
              <div class="panel" data-panel="tudj">
                <p>{t(TUDJ_MEG[s.kod] ?? TUDJ_ALTALANOS)}</p>
                {#if tar.tudj[s.kod]}
                  {@const cel = tar.tudj[s.kod]}
                  <p class="utmutato" data-utmutato>{t('Útmutató: {oldal} › {szakasz}', { oldal: cel.oldal.cim, szakasz: cel.fejlec })}</p>
                  <div class="gombok">
                    {#if cel.munkater_ut && onjegyzet}
                      <button type="button" class="m-gomb semleges suru" data-utmutato-megnyit onclick={() => onjegyzet(cel.munkater_ut!)}>{t('egeszseg.utmutato_megnyit')}</button>
                    {:else}
                      <button type="button" class="m-gomb semleges suru" data-utmutato-mutat aria-expanded={!!szakaszNyitva[s.kod]} onclick={() => szakaszNyitva[s.kod] = !szakaszNyitva[s.kod]}>
                        {szakaszNyitva[s.kod] ? t('egeszseg.utmutato_elrejt') : t('egeszseg.utmutato_mutat')}
                      </button>
                    {/if}
                  </div>
                  {#if szakaszNyitva[s.kod] && !(cel.munkater_ut && onjegyzet)}<DokuSzakasz szoveg={cel.szakasz} />{/if}
                {/if}
              </div>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</Atfedes>

<style>
  header { display: flex; align-items: center; justify-content: space-between; gap: var(--t-3); padding: var(--t-4); border-bottom: var(--keret-vastag) solid var(--keret); }
  h1 { margin: 0; font-size: var(--betu-h4); font-weight: var(--suly-kozepes); }
  h2 { margin: 0; font-size: var(--betu-torzs); font-weight: var(--suly-kozepes); }
  .fej-gombok, .gombok { display: flex; flex-wrap: wrap; gap: var(--t-2); }
  .tartalom { flex: 1; min-height: 0; overflow-y: auto; padding: var(--t-5); display: flex; flex-direction: column; gap: var(--t-3); }
  .osszegzes { display: flex; align-items: center; gap: var(--t-2); margin: 0; font-weight: var(--suly-kozepes); }
  .leiras { margin: 0; color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .siker { display: flex; align-items: center; gap: var(--t-2); margin: 0; color: var(--siker); }
  .hiba { margin: 0; color: var(--hiba); display: flex; }
  .lista { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: var(--t-3); }
  .sor { display: flex; flex-direction: column; gap: var(--t-2); padding: var(--t-4); border: var(--keret-vastag) solid var(--keret); border-radius: var(--kerekites); background: var(--hatter); }
  .sor.figyelem { background: var(--figyelmeztetes-hatter); }
  .sor.hiba { background: var(--hiba-hatter); }
  .sor-fej { display: flex; align-items: center; gap: var(--t-3); flex-wrap: wrap; }
  .allapot-jel { display: inline-flex; align-items: center; gap: var(--t-1); font-size: var(--betu-kicsi); font-weight: var(--suly-kozepes); }
  .sor.ok .allapot-jel { color: var(--siker); }
  .sor.figyelem .allapot-jel { color: var(--figyelmeztetes); }
  .sor.hiba .allapot-jel { color: var(--hiba); }
  .sor.info .allapot-jel { color: var(--szoveg-masodlagos); }
  .uzenet { margin: 0; }
  .panel { padding-top: var(--t-2); border-top: var(--keret-vastag) solid var(--keret); }
  .panel p { margin: 0; }
  .panel { display: flex; flex-direction: column; gap: var(--t-2); }
  .utmutato { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: var(--t-1) var(--t-4); margin: 0; }
  dt { color: var(--szoveg-masodlagos); }
  dd { margin: 0; overflow-wrap: anywhere; }
  .nyers { margin: var(--t-3) 0 0; padding: var(--t-3); background: var(--hatter-kod); color: var(--kod-szoveg); font-family: var(--betu-mono); font-size: var(--betu-kicsi); overflow-x: auto; user-select: text; }
</style>
