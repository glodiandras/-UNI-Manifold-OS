<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import { t, tk } from '../lib/i18n';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import { beallitasok, type BeallitasokTar } from '../lib/beallitasok/allapot.svelte';
  import { MODULOK, type Beallitasok, type BeallitasokValtozas } from '../lib/beallitasok/tipusok';
  import { parancsNev, regiszter } from '../lib/parancsok/regiszter';
  import { esemenybol, kanonikus, megjelenit } from '../lib/parancsok/billentyuk';
  import { epitesAllapot } from '../lib/vezerlo/epites.svelte';
  import { naptarHid } from '../lib/naptar/hid.svelte';
  import { beallitasAblak, SZAKASZOK } from './allapot.svelte';
  let { tar = beallitasok, onbezar, onsetup, onrendszer }: { tar?: BeallitasokTar; onbezar: () => void; onsetup: () => void; onrendszer: (szakasz: string) => void } = $props();
  const masolat = (v: Beallitasok) => JSON.parse(JSON.stringify(v)) as Beallitasok;
  let alap = $state(masolat(untrack(() => tar.ertek)));
  let vazlat = $state(masolat(untrack(() => tar.ertek)));
  let rev = $state(untrack(() => tar.adat?.rev ?? ''));
  let elvetes = $state(false);
  let elvetesGomb: HTMLButtonElement | undefined = $state();
  let elvetesElotti: HTMLElement | null = null;
  let mentve = $state(false);
  let billentyuHiba = $state('');
  let szures = $state('');
  const szakasz = $derived(beallitasAblak.szakasz);
  const cim = $derived(SZAKASZOK.find(s => s.id === szakasz)?.cim ?? 'beallitasok.cim');
  const modosult = $derived(JSON.stringify(alap) !== JSON.stringify(vazlat));
  const kulsoValtozas = $derived(!!rev && tar.adat?.rev !== rev);
  const parancsok = $derived(regiszter.mind().filter(p => parancsNev(p).toLocaleLowerCase().includes(szures.toLocaleLowerCase())));
  const MODUL_NEVEK = {
    hivatkozasok: tk('beallitasok.modul.hivatkozasok'), vazlat: tk('beallitasok.modul.vazlat'), tulajdonsagok: tk('beallitasok.modul.tulajdonsagok'),
    gyorsvalto: tk('beallitasok.modul.gyorsvalto'), kereses: tk('beallitasok.modul.kereses'), perjel: tk('beallitasok.modul.perjel'), cimkek: tk('beallitasok.modul.cimkek'),
    sablonok: tk('beallitasok.modul.sablonok'), napi: tk('beallitasok.modul.napi'), canvas: tk('beallitasok.modul.canvas'), bazis: tk('beallitasok.modul.bazis'), graf: tk('beallitasok.modul.graf'),
    pdf: tk('beallitasok.modul.pdf'), media: tk('beallitasok.modul.media'), kartya: tk('beallitasok.modul.kartya'), kviz: tk('beallitasok.modul.kviz'), osszefoglalas: tk('beallitasok.modul.osszefoglalas'),
    matek: tk('beallitasok.modul.matek'), kod: tk('beallitasok.modul.kod'), fuzet: tk('beallitasok.modul.fuzet'), video: tk('beallitasok.modul.video'), kerdezz: tk('beallitasok.modul.kerdezz'),
    asszisztens: tk('beallitasok.modul.asszisztens'), naptar: tk('beallitasok.modul.naptar'), felkeszultseg: tk('beallitasok.modul.felkeszultseg'), tracker: tk('beallitasok.modul.tracker'),
  };
  const FAJL_MEZOK = [
    { id: 'uj_mappa', cim: tk('beallitasok.uj_mappa') }, { id: 'csatolmany_mappa', cim: tk('beallitasok.csatolmany_mappa') },
    { id: 'sablon_mappa', cim: tk('beallitasok.sablon_mappa') }, { id: 'napi_ut', cim: tk('beallitasok.napi_ut') },
  ] as const;
  let navigacio: HTMLElement | undefined = $state();
  onMount(() => { navigacio?.querySelector<HTMLButtonElement>('[aria-current]')?.focus(); if (!tar.adat) void ujratolt(); });
  async function ujratolt() {
    await tar.betolt();
    if (tar.adat && !tar.hiba) atvesz();
  }
  function atvesz() { alap = masolat(tar.ertek); vazlat = masolat(tar.ertek); rev = tar.adat?.rev ?? ''; mentve = false; billentyuHiba = ''; }
  function elvetMegsem() {
    elvetes = false;
    void tick().then(() => elvetesElotti?.focus());
  }
  function bezar() {
    if (tar.mentes) return;
    if (elvetes) { elvetMegsem(); return; }
    if (!modosult) { onbezar(); return; }
    elvetesElotti = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    elvetes = true;
    void tick().then(() => elvetesGomb?.focus());
  }
  async function ment() {
    billentyuHiba = '';
    if (!Number.isInteger(vazlat.szerkeszto.tab_meret) || vazlat.szerkeszto.tab_meret < 1 || vazlat.szerkeszto.tab_meret > 8) { billentyuHiba = t('beallitasok.hibas_tab'); return; }
    if (!Number.isInteger(vazlat.megjelenes.betumeret) || vazlat.megjelenes.betumeret < 12 || vazlat.megjelenes.betumeret > 28) { billentyuHiba = t('beallitasok.hibas_betumeret'); return; }
    try { regiszter.billentyuketEllenoriz(vazlat.billentyuk); } catch (e) { billentyuHiba = e instanceof Error ? e.message : t('beallitasok.hibas_billentyu'); return; }
    const valtozas: BeallitasokValtozas = {};
    for (const kulcs of Object.keys(vazlat) as (keyof Beallitasok)[]) {
      if (JSON.stringify(vazlat[kulcs]) !== JSON.stringify(alap[kulcs])) Object.assign(valtozas, { [kulcs]: vazlat[kulcs] });
    }
    if (await tar.ment(valtozas, rev)) { atvesz(); mentve = true; }
  }
  function billentyuSzoveg(id: string): string {
    const kert = Object.hasOwn(vazlat.billentyuk, id) ? vazlat.billentyuk[id] : regiszter.alapBillentyu(id);
    if (!kert) return '';
    try { return megjelenit(kert); } catch { return t('beallitasok.hibas_billentyu'); }
  }
  function billentyu(e: KeyboardEvent, id: string) {
    if (e.key === 'Tab' || e.key === 'Escape') return;
    e.preventDefault(); e.stopPropagation();
    if (e.key === 'Backspace' || e.key === 'Delete') { vazlat.billentyuk[id] = ''; billentyuHiba = ''; return; }
    const a = esemenybol(e);
    if (!a) return;
    if (!a.mod && !a.ctrl && !a.alt && !/^F\d+$/.test(a.kulcs)) { billentyuHiba = t('beallitasok.modosito_kell'); return; }
    const uj = { ...vazlat.billentyuk, [id]: kanonikus(a) };
    try { regiszter.billentyuketEllenoriz(uj); vazlat.billentyuk = uj; billentyuHiba = ''; }
    catch (e) { billentyuHiba = e instanceof Error ? e.message : t('beallitasok.hibas_billentyu'); }
  }
  function nyitRendszer(cel: string) { if (modosult) { billentyuHiba = t('beallitasok.ments_elobb'); return; } onbezar(); onrendszer(cel); }
  function setupUjra() { if (modosult) { billentyuHiba = t('beallitasok.ments_elobb'); return; } onbezar(); onsetup(); }
</script>

<Atfedes cimke={t('beallitasok.cim')} nev="beallitasok" onbezar={bezar} szeles>
  <header><h1>{t('beallitasok.cim')}</h1><button class="m-gomb semleges" type="button" onclick={bezar}>{t('beallitasok.bezar')}</button></header>
  <div class="elrendezes" inert={elvetes}>
    <nav bind:this={navigacio} aria-label={t('beallitasok.szakaszok')}>
      {#each SZAKASZOK as s, i}
        {#if i === 0 || SZAKASZOK[i - 1].csoport !== s.csoport}<p class="csoport">{t(s.csoport)}</p>{/if}
        <button type="button" class:aktiv={szakasz === s.id} aria-current={szakasz === s.id ? 'page' : undefined} onclick={() => beallitasAblak.szakasz = s.id}>{t(s.cim)}</button>
      {/each}
    </nav>
    <section aria-label={t(cim)}>
      <h2>{t(cim)}</h2>
      {#if tar.betoltes}<p role="status">{t('beallitasok.betoltes')}</p>{/if}
      {#if !tar.adat}<p class="hiba" role="alert">{tar.hiba ?? t('beallitasok.nem_elerheto')}</p><button type="button" class="m-gomb semleges" onclick={ujratolt}>{t('beallitasok.ujratolt')}</button>
      {:else}
        <fieldset disabled={tar.mentes}>
          {#if szakasz === 'altalanos'}
            <p>{tar.adat.munkater.nev}</p><p class="ut">{tar.adat.munkater.vault}</p>
            <label>{t('beallitasok.nyelv')}<select bind:value={vazlat.altalanos.nyelv}><option value="auto">{t('beallitasok.auto')}</option><option value="hu">{t('beallitasok.magyar')}</option><option value="en">{t('beallitasok.angol')}</option></select></label>
            <p class="leiras">{t('beallitasok.nyelv_leiras')}</p>
            <label>{t('beallitasok.inditas')}<select bind:value={vazlat.altalanos.inditas}><option value="utolso">{t('beallitasok.utolso')}</option><option value="valaszto">{t('beallitasok.valaszto')}</option></select></label>
            <button class="m-gomb semleges" type="button" onclick={setupUjra}>{t('beallitasok.setup_ujra')}</button>
            <p class="leiras">{t('beallitasok.frissites_leiras')}</p>
          {:else if szakasz === 'szerkeszto'}
            <label>{t('beallitasok.alap_mod')}<select bind:value={vazlat.szerkeszto.mod}><option value="elo">{t('beallitasok.elo')}</option><option value="forras">{t('beallitasok.forras')}</option></select></label>
            <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.szerkeszto.olvashato_szelesseg} />{t('beallitasok.olvashato')}</label>
            <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.szerkeszto.helyesiras} />{t('beallitasok.helyesiras')}</label>
            <label>{t('beallitasok.tab')}<input type="number" min="1" max="8" bind:value={vazlat.szerkeszto.tab_meret} /></label>
            <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.szerkeszto.perjel} />{t('beallitasok.perjel')}</label>
          {:else if szakasz === 'fajlok'}
            <p class="leiras">{t('beallitasok.fajlok_leiras')}</p>
            {#each FAJL_MEZOK as m}<label>{t(m.cim)}<input type="text" bind:value={vazlat.fajlok[m.id]} spellcheck="false" /></label>{/each}
            <p class="leiras">{t('beallitasok.napi_leiras')}</p>
            <label>{t('beallitasok.link_formatum')}<select bind:value={vazlat.fajlok.link_formatum}><option value="rovid">{t('beallitasok.rovid')}</option><option value="relativ">{t('beallitasok.relativ')}</option></select></label>
            <p class="leiras">{t('beallitasok.kuka_leiras')}</p>
          {:else if szakasz === 'megjelenes'}
            <label>{t('beallitasok.tema')}<select bind:value={vazlat.megjelenes.tema}><option value="rendszer">{t('beallitasok.rendszer')}</option><option value="vilagos">{t('beallitasok.vilagos')}</option><option value="sotet">{t('beallitasok.sotet')}</option></select></label>
            <label>{t('beallitasok.betumeret')}<input type="number" min="12" max="28" bind:value={vazlat.megjelenes.betumeret} /></label>
            <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.megjelenes.csend} />{t('beallitasok.csend')}</label>
            <p class="leiras">{t('beallitasok.akcentus')}</p>
          {:else if szakasz === 'modulok'}
            <p class="leiras">{t('beallitasok.modul_leiras')}</p>
            {#each MODULOK as m}<label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.modulok[m]} />{t(MODUL_NEVEK[m])}</label>{/each}
          {:else if szakasz === 'billentyuk'}
            <p class="leiras">{t('beallitasok.billentyu_leiras')}</p>
            <label>{t('beallitasok.parancs_keres')}<input type="search" bind:value={szures} /></label>
            {#each parancsok as p (p.id)}
              <div class="billentyu"><label>{parancsNev(p)}<input aria-label={t('Gyorsbillentyű ehhez: {nev}', { nev: parancsNev(p) })} value={billentyuSzoveg(p.id)} readonly disabled={p.id === 'beallitasok.megnyit'} onkeydown={e => billentyu(e, p.id)} /></label>
                <button type="button" class="m-gomb semleges suru" aria-label={t('Gyorsbillentyű visszaállítása: {nev}', { nev: parancsNev(p) })} disabled={p.id === 'beallitasok.megnyit'} onclick={() => vazlat.billentyuk[p.id] = regiszter.alapBillentyu(p.id)}>{t('beallitasok.alaphelyzet')}</button>
              </div>
            {/each}
          {:else if ['halozat', 'telemetria', 'adatok', 'integraciok', 'engedelyek', 'asszisztens'].includes(szakasz)}
            <p class="leiras">{t('beallitasok.adatvedelem_leiras')}</p>
            <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.adatvedelem.asszisztens} />{t('beallitasok.modul.asszisztens')}</label>
            <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.adatvedelem.tracker} />{t('beallitasok.modul.tracker')}</label>
            <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.adatvedelem.ertesitesek} />{t('beallitasok.ertesitesek')}</label>
            <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.adatvedelem.naptar} />{t('beallitasok.naptar')}</label>
            {#if naptarHid.elerheto}<button type="button" class="m-gomb semleges" disabled={naptarHid.kerdesben} onclick={() => naptarHid.kerd()}>{t('beallitasok.naptar_engedely')}</button>{/if}
            {#if naptarHid.hiba}<p role="alert" class="hiba">{naptarHid.hiba}</p>{/if}
            <p class="leiras">{t('beallitasok.naptar_leiras')}</p>
            <button type="button" class="m-gomb semleges" onclick={() => nyitRendszer('rendszer')}>{t('beallitasok.rendszer_megnyit')}</button>
          {:else if szakasz === 'pillanatkepek' || szakasz === 'visszaallitas'}
            <p>{t('beallitasok.elozmeny_leiras')}</p>
            <button type="button" class="m-gomb semleges" disabled={!regiszter.kap('elozmenyek.megnyit') || !regiszter.elerheto(regiszter.kap('elozmenyek.megnyit')!)} onclick={() => nyitRendszer('elozmenyek')}>{t('beallitasok.elozmeny_megnyit')}</button>
          {:else if szakasz === 'nevjegy'}
            <h3>MANIFOLD</h3><p>{t('beallitasok.marka')}</p><p>{t('beallitasok.community')}</p>
            <details ontoggle={e => { if (e.currentTarget.open) void epitesAllapot.frissit(); }}><summary>{t('beallitasok.reszletek')}</summary><p>{t('beallitasok.architektura')}</p><p>{tar.adat.munkater.id}</p>{#if epitesAllapot.adat}<dl>{#each epitesAllapot.adat.reszek as r}<dt>{r.resz}</dt><dd>{r.azonosito}</dd>{/each}</dl>{:else if epitesAllapot.hiba}<p class="hiba" role="alert">{epitesAllapot.hiba}</p>{/if}</details>
          {:else}
            <p class="leiras">{t('beallitasok.meglevo_leiras')}</p>
            {#if ['modellek','kalibracio','teljesitmeny'].includes(szakasz)}<p>{t('beallitasok.modellek_leiras')}</p>{/if}
            {#if ['pillanatkepek','helyi_mentes','kulso_mentes','visszaallitas'].includes(szakasz)}<p>{t('beallitasok.mentes_leiras')}</p>{/if}
            <button type="button" class="m-gomb semleges" onclick={() => nyitRendszer(szakasz)}>{t('beallitasok.rendszer_megnyit')}</button>
          {/if}
        </fieldset>
      {/if}
    </section>
  </div>
  <footer>
    <div class="allapot" aria-live="polite">
      {#if tar.hiba && tar.adat}<p class="hiba" role="alert">{tar.hiba}</p>{/if}
      {#if billentyuHiba}<p class="hiba" role="alert">{billentyuHiba}</p>{/if}
      {#if kulsoValtozas || tar.utkozes}<p class="hiba" role="alert">{t('beallitasok.utkozes')}</p><button type="button" class="m-gomb semleges" onclick={ujratolt}>{t('beallitasok.ujratolt')}</button>{/if}
      {#if tar.mentes}<p role="status">{t('beallitasok.mentes')}</p>{:else if modosult}<p>{t('beallitasok.nem_mentett')}</p>{:else if mentve}<p role="status">{t('beallitasok.mentve')}</p>{/if}
      {#if tar.adat?.ujrainditas.length}<p>{t('beallitasok.ujranyitas')}</p>{/if}
    </div>
    <button class="m-gomb" type="button" disabled={!tar.adat || tar.mentes || !modosult || kulsoValtozas || elvetes} onclick={ment}>{t('beallitasok.ment')}</button>
  </footer>
  {#if elvetes}<div class="elvetes" role="alert"><p>{t('beallitasok.elvet_kerdes')}</p><button type="button" class="m-gomb semleges" bind:this={elvetesGomb} onclick={elvetMegsem}>{t('beallitasok.szerkesztes_folytat')}</button><button type="button" class="m-gomb semleges" onclick={onbezar}>{t('beallitasok.elvet')}</button></div>{/if}
</Atfedes>

<style>
  header, footer { display: flex; align-items: center; justify-content: space-between; gap: var(--t-3); padding: var(--t-4); border-bottom: var(--keret-vastag) solid var(--keret); }
  footer { border-top: var(--keret-vastag) solid var(--keret); border-bottom: 0; }
  h1, h2 { font-size: var(--betu-h4); font-weight: var(--suly-kozepes); margin: 0; }
  h2 { margin-bottom: var(--t-5); }
  .elrendezes { display: flex; min-height: 0; flex: 1; }
  nav { flex: 0 0 calc(var(--t-8) * 3); overflow-y: auto; padding: var(--t-3); background: var(--hatter-oldalsav); border-right: var(--keret-vastag) solid var(--keret); }
  nav button { display: block; width: 100%; border: 0; border-radius: var(--kerekites); padding: var(--t-2) var(--t-3); text-align: start; background: transparent; color: var(--szoveg); font: inherit; }
  nav button:hover { background: var(--hatter-hover); }
  nav button.aktiv { background: var(--hatter-aktiv); font-weight: var(--suly-kozepes); }
  .csoport { font-size: var(--betu-kicsi); color: var(--szoveg-masodlagos); margin: var(--t-3) var(--t-3) var(--t-1); }
  section { flex: 1; min-width: 0; overflow-y: auto; padding: var(--t-5); }
  fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
  label { display: flex; align-items: center; justify-content: space-between; gap: var(--t-4); padding: var(--t-3) 0; }
  label.kapcsolo { justify-content: flex-start; gap: var(--t-3); }
  input:not([type="checkbox"]), select { width: 50%; min-width: 0; padding: var(--t-2); color: var(--szoveg); background: var(--hatter); border: var(--keret-vastag) solid var(--keret-mezo); border-radius: var(--kerekites); font: inherit; }
  input[type="checkbox"] { accent-color: var(--akcent-kitoltes); }
  .leiras, .ut { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .ut { overflow-wrap: anywhere; }
  .hiba { color: var(--hiba); }
  .allapot { min-width: 0; }
  .allapot p { margin: 0; }
  .billentyu { display: flex; align-items: center; gap: var(--t-2); }
  .billentyu label { flex: 1; min-width: 0; }
  .elvetes { padding: var(--t-4); border-top: var(--keret-vastag) solid var(--keret); }
</style>
