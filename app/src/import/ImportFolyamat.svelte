<!--
  Az import folyamata (F8): mappák → előnézet → explicit jóváhagyás → futás (WS `import` esemény) → összegzés / hiba → visszavonás.
  Az Obsidian-import egy ÚJ munkatérbe másol; az eredeti vault nem módosul (ezt a képernyő végig kimondja). A v2-import
  (csak Developer módban, a hívó kapuja) a megnyitott munkatér beállításait veszi át. Ugyanaz a keret, két fajta.
-->
<script lang="ts">
  import { getContext, onMount, tick, untrack } from 'svelte';
  import { CircleAlert, CircleCheck, FolderOpen, Info, TriangleAlert } from '../lib/ikon/ikonok';
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import BeallitasSor from '../lib/ui/BeallitasSor.svelte';
  import HibaPanel from '../lib/ui/HibaPanel.svelte';
  import Kapcsolo from '../lib/ui/Kapcsolo.svelte';
  import { meretSzoveg } from '../lib/adatvedelem/megjelenites';
  import { hejbenFut, hejnek } from '../lib/core/hej';
  import type { CoreKapcsolat } from '../lib/core/ws.svelte';
  import { ImportTar } from '../lib/import/allapot.svelte';
  import { LEPES_CIM, abszolutUt, beallitasCim, kodSzoveg, szam } from '../lib/import/megjelenites';
  import type { ImportFajta } from '../lib/import/tipusok';
  import { alapValaszto } from '../lib/import/valaszto';
  import { KORNYEZET_KULCS, type Kornyezet } from '../lib/kornyezet';
  import ObsidianElonezet from './ObsidianElonezet.svelte';
  import V2Elonezet from './V2Elonezet.svelte';
  import Visszaford from './Visszaford.svelte';

  let { fajta = 'obsidian', tar: kivulrol, kapcsolat: kapcsolatKivulrol, valaszto, onbezar, onkesz }: {
    fajta?: ImportFajta;
    tar?: ImportTar;
    kapcsolat?: CoreKapcsolat | null;
    /** Mappaválasztó; hiányában a héj natív ablaka (`window.manifold.mappaValasztas`), és ha az sincs (böngésző), csak a beírt útvonal él.
     *  Visszatérés: a választott útvonal, `null` ha elvetette. */
    valaszto?: (cim: string) => Promise<string | null>;
    /** „Hide” / „Close”: a felület bezárja a folyamatot (a futó import a háttérben megy tovább). */
    onbezar?: () => void;
    /** A kész import után a felhasználó a „Done” gombbal lezárta. */
    onkesz?: () => void;
  } = $props();

  const tar = untrack(() => kivulrol ?? new ImportTar(fajta));
  const v2 = tar.fajta === 'v2';
  const kontextus = getContext<Kornyezet | undefined>(KORNYEZET_KULCS);
  const kapcsolat = untrack(() => (kapcsolatKivulrol === undefined ? (kontextus?.kapcsolat ?? null) : kapcsolatKivulrol));
  const azon = Math.random().toString(36).slice(2, 8);

  let cimElem = $state<HTMLHeadingElement>();
  let visszaNyitva = $state(false);
  let valasztasHiba = $state('');
  let megszakitasKerdes = $state(false);
  let megmaradGomb = $state<HTMLButtonElement>();

  onMount(() => tar.figyel(kapcsolat));

  // minden szakasz-váltásnál a cím kap fókuszt (billentyűzettel/képernyőolvasóval követhető)
  $effect(() => {
    void tar.fazis;
    void tick().then(() => cimElem?.focus());
  });

  const forrasHiba = $derived(tar.forras.trim() !== '' && !abszolutUt(tar.forras));
  const celHiba = $derived(!v2 && tar.cel.trim() !== '' && !abszolutUt(tar.cel));
  const e = $derived(tar.elonezet);
  const kesz = $derived(tar.eredmeny);
  const szazalek = $derived(tar.halad && tar.halad.osszes_db > 0 ? Math.min(100, Math.round((tar.halad.kesz_db / tar.halad.osszes_db) * 100)) : null);
  const munkaterValaszto = $derived(hejbenFut());
  const valasztoFn = $derived(valaszto ?? alapValaszto());
  const megszakitvaKesz = $derived(tar.halad && tar.halad.osszes_db > 0 ? tar.halad : null);

  async function valaszt(melyik: 'forras' | 'cel') {
    const valaszto = valasztoFn;
    if (!valaszto) return;
    valasztasHiba = '';
    try {
      const ut = await valaszto(melyik === 'forras' ? (v2 ? t('import.v2.forras_valaszt') : t('import.forras_valaszt')) : t('import.cel_valaszt'));
      if (ut) { if (melyik === 'forras') tar.setForras(ut); else tar.setCel(ut); }
    } catch {
      valasztasHiba = t('import.valaszto_hiba');
    }
  }

  async function megszakitasKer() {
    megszakitasKerdes = true;
    await tick();
    megmaradGomb?.focus();         // a biztonságos válasz (az import folytatása) kap fókuszt
  }

  async function megszakit() {
    megszakitasKerdes = false;
    await tar.megszakit();
  }

  function befejez() {
    tar.ujKezdes();
    visszaNyitva = false;
    onkesz?.();
  }

  function submit(ev: SubmitEvent) {
    ev.preventDefault();
    void tar.elonezetKer();
  }
</script>

<section class="folyamat" aria-busy={tar.foglalt} data-import-folyamat={tar.fajta} data-fazis={tar.fazis}>
  {#if tar.fazis === 'beallit'}
    <h3 tabindex="-1" bind:this={cimElem}>{v2 ? t('import.v2.cim') : t('import.cim')}</h3>
    <p class="biztonsag"><Ikon ikon={Info} /> <span>{v2 ? t('import.v2.forras_erintetlen') : t('import.forras_erintetlen')}</span></p>
    <p>{v2 ? t('import.v2.leiras') : t('import.leiras')}</p>
    <form onsubmit={submit}>
      <div class="mezo-sor">
        <label for="imp-forras-{azon}">{v2 ? t('import.v2.forras') : t('import.forras')}</label>
        <div class="mezo-vezerlo">
          <input id="imp-forras-{azon}" class="mezo" type="text" spellcheck="false" autocomplete="off" placeholder={t('import.ut_minta')} value={tar.forras} oninput={(ev) => tar.setForras(ev.currentTarget.value)} aria-invalid={forrasHiba} aria-describedby={forrasHiba ? `imp-forras-hiba-${azon}` : undefined} />
          {#if valasztoFn}<button type="button" class="m-gomb semleges" onclick={() => void valaszt('forras')}><Ikon ikon={FolderOpen} /> {t('import.mappa_valaszt')}</button>{/if}
        </div>
        {#if forrasHiba}<p id="imp-forras-hiba-{azon}" class="hiba" role="alert">{t('import.ut_hiba')}</p>{/if}
      </div>
      {#if !v2}
        <div class="mezo-sor">
          <label for="imp-cel-{azon}">{t('import.cel')}</label>
          <div class="mezo-vezerlo">
            <input id="imp-cel-{azon}" class="mezo" type="text" spellcheck="false" autocomplete="off" placeholder={t('import.ut_minta')} value={tar.cel} oninput={(ev) => tar.setCel(ev.currentTarget.value)} aria-invalid={celHiba} aria-describedby="imp-cel-seg-{azon}{celHiba ? ` imp-cel-hiba-${azon}` : ''}" />
            {#if valasztoFn}<button type="button" class="m-gomb semleges" onclick={() => void valaszt('cel')}><Ikon ikon={FolderOpen} /> {t('import.mappa_valaszt')}</button>{/if}
          </div>
          <p id="imp-cel-seg-{azon}" class="halvany">{t('import.cel_seged')}</p>
          {#if celHiba}<p id="imp-cel-hiba-{azon}" class="hiba" role="alert">{t('import.ut_hiba')}</p>{/if}
        </div>
        <div class="mezo-sor">
          <label for="imp-nev-{azon}">{t('import.nev')}</label>
          <input id="imp-nev-{azon}" class="mezo" type="text" autocomplete="off" bind:value={tar.nev} />
        </div>
        <BeallitasSor cim={t('import.opcio.obsidian')} leiras={t('import.opcio.obsidian_leiras')}><Kapcsolo cimke={t('import.opcio.obsidian')} bind:ertek={tar.obsidianMappa} /></BeallitasSor>
        <BeallitasSor cim={t('import.opcio.kuka')} leiras={t('import.opcio.kuka_leiras')}><Kapcsolo cimke={t('import.opcio.kuka')} bind:ertek={tar.kukaMappa} /></BeallitasSor>
      {/if}
      {#if valasztasHiba}<p class="hiba" role="alert">{valasztasHiba}</p>{/if}
      {#if tar.hiba}<HibaPanel mi={tar.hiba.mi} javitas={tar.hiba.javitas} />{/if}
      <div class="gombok">
        <button type="submit" class="m-gomb" disabled={!tar.urlapKesz || tar.foglalt}>{tar.foglalt ? t('import.elonezet_tolt') : t('import.elonezet_gomb')}</button>
        {#if onbezar}<button type="button" class="m-gomb semleges" disabled={tar.foglalt} onclick={() => onbezar?.()}>{t('import.bezar')}</button>{/if}
      </div>
      {#if tar.foglalt}<p role="status" class="halvany">{t('import.elonezet_tolt_leiras')}</p>{/if}
    </form>

  {:else if tar.fazis === 'elonezet' && e}
    <h3 tabindex="-1" bind:this={cimElem}>{t('import.elonezet_cim')}</h3>
    <p class="biztonsag"><Ikon ikon={Info} /> <span>{v2 ? t('import.v2.forras_erintetlen') : t('import.forras_erintetlen')}</span></p>
    {#if e.eredmeny === 'kesz' && e.fajta === 'obsidian'}
      <p class="eredmeny" role="status"><Ikon ikon={CircleCheck} /> <strong>{t('import.mar_kesz')}</strong></p>
      <p class="halvany">{t('import.mar_kesz_leiras')}</p>
      <dl><dt>{t('import.osszesites.forras')}</dt><dd class="ut">{e.forras}</dd><dt>{t('import.osszesites.cel')}</dt><dd class="ut">{e.cel}</dd></dl>
      {#if visszaNyitva}
        <Visszaford id={e.id} fajta="obsidian" onmegse={() => (visszaNyitva = false)} />
      {:else}
        <div class="gombok">
          <button type="button" class="m-gomb semleges" onclick={() => (visszaNyitva = true)}>{t('import.visszaford.gomb')}</button>
          <button type="button" class="m-gomb semleges" onclick={() => tar.vissza()}>{t('import.mappak_valtoztat')}</button>
        </div>
      {/if}
    {:else}
      {#if e.eredmeny === 'tilos'}
        <HibaPanel mi={t('import.hiba.tilos')} javitas={t('import.javitas.tilos')} ujra={() => tar.vissza()} ujraCimke={t('import.mappak_valtoztat')} />
      {/if}
      {#if tar.hiba}<HibaPanel mi={tar.hiba.mi} javitas={tar.hiba.javitas} ujra={() => void tar.elonezetKer()} ujraCimke={t('import.elonezet_ujra')} />{/if}
      {#if e.fajta === 'v2'}<V2Elonezet {e} />{:else}<ObsidianElonezet {e} />{/if}
      {#if tar.folytatas}
        <p class="figyelem" role="status"><Ikon ikon={TriangleAlert} /> <span>{t('import.folytatas_leiras')}</span></p>
      {/if}
      <p class="halvany">{v2 ? t('import.v2.jovahagyas') : t('import.jovahagyas')}</p>
      <div class="gombok">
        {#if e.eredmeny !== 'tilos'}
          <button type="button" class="m-gomb" disabled={!tar.indithato} onclick={() => void tar.indit()}>
            {#if tar.foglalt}{t('import.indul')}{:else if tar.folytatas}{t('import.folytat')}{:else if v2}{t('import.v2.indit')}{:else}{t('import.indit')}{/if}
          </button>
        {/if}
        <button type="button" class="m-gomb semleges" disabled={tar.foglalt} onclick={() => tar.vissza()}>{t('import.mappak_valtoztat')}</button>
      </div>
    {/if}

  {:else if tar.fazis === 'fut'}
    <h3 tabindex="-1" bind:this={cimElem}>{t('import.fut.cim')}</h3>
    <p class="biztonsag"><Ikon ikon={Info} /> <span>{t('import.forras_erintetlen')}</span></p>
    <div role="status" aria-live="polite" class="haladas" data-haladas>
      {#if tar.halad}
        <p><strong>{kodSzoveg(LEPES_CIM, tar.halad.lepes, 'import.lepes.masolas')}</strong></p>
        {#if tar.halad.lepes === 'masolas'}
          <progress max="100" value={szazalek ?? undefined} aria-label={t('import.fut.folyamat')}></progress>
          <p class="halvany">{t('{kesz} / {osszes} fájl másolva · {meret}', { kesz: szam(tar.halad.kesz_db), osszes: szam(tar.halad.osszes_db), meret: meretSzoveg(tar.halad.bajt) })}{szazalek !== null ? ` · ${szazalek} %` : ''}</p>
        {:else}
          <progress aria-label={t('import.fut.folyamat')}></progress>
        {/if}
      {:else}
        <progress aria-label={t('import.fut.folyamat')}></progress>
        <p class="halvany">{t('import.fut.indul')}</p>
      {/if}
    </div>
    <p class="halvany">{t('import.fut.leiras')}</p>
    {#if tar.hiba}<HibaPanel mi={tar.hiba.mi} javitas={tar.hiba.javitas} />{/if}
    {#if megszakitasKerdes}
      <section class="megszakit" aria-labelledby="megszakit-cim-{azon}" data-megszakit-kerdes>
        <h4 id="megszakit-cim-{azon}">{t('import.megszakit.kerdes')}</h4>
        <p>{t('import.megszakit.leiras')}</p>
        <p class="halvany">{t('import.forras_erintetlen')}</p>
        <div class="gombok">
          <button type="button" class="m-gomb" onclick={() => void megszakit()}>{t('import.fut.megszakit')}</button>
          <button type="button" class="m-gomb semleges" bind:this={megmaradGomb} onclick={() => (megszakitasKerdes = false)}>{t('import.megszakit.marad')}</button>
        </div>
      </section>
    {:else}
      {#if tar.megszakitasFolyik}<p role="status" class="halvany" data-megszakit-folyik>{t('import.megszakit.folyamatban')}</p>{/if}
      <div class="gombok">
        {#if onbezar}<button type="button" class="m-gomb semleges" onclick={() => onbezar?.()}>{t('import.fut.elrejt')}</button>{/if}
        <button type="button" class="m-gomb semleges" disabled={tar.megszakitasFolyik || !tar.id} onclick={() => void megszakitasKer()}>{t('import.fut.megszakit')}</button>
      </div>
    {/if}

  {:else if tar.fazis === 'megszakitva'}
    <h3 tabindex="-1" bind:this={cimElem}><Ikon ikon={TriangleAlert} meret={20} /> {t('import.megszakitva.cim')}</h3>
    <p class="biztonsag"><Ikon ikon={Info} /> <span>{t('import.forras_erintetlen')}</span></p>
    {#if megszakitvaKesz}<p data-megszakitva-darab>{t('{kesz} / {osszes} fájl másolva a megszakításig', { kesz: szam(megszakitvaKesz.kesz_db), osszes: szam(megszakitvaKesz.osszes_db) })}</p>{/if}
    <p class="halvany">{t('import.megszakitva.megmarad')}</p>
    {#if visszaNyitva && tar.id}
      <Visszaford id={tar.id} fajta="obsidian" onmegse={() => (visszaNyitva = false)} />
    {:else}
      <div class="gombok">
        <button type="button" class="m-gomb" onclick={() => void tar.ujraElonezet()}>{t('import.attekint_folytat')}</button>
        {#if tar.id}<button type="button" class="m-gomb semleges" onclick={() => (visszaNyitva = true)}>{t('import.visszaford.gomb')}</button>{/if}
        <button type="button" class="m-gomb semleges" onclick={() => tar.vissza()}>{t('import.mappak_valtoztat')}</button>
        {#if onbezar}<button type="button" class="m-gomb link" onclick={() => onbezar?.()}>{t('import.bezar')}</button>{/if}
      </div>
    {/if}

  {:else if tar.fazis === 'hiba' && tar.hiba}
    <h3 tabindex="-1" bind:this={cimElem}>{t('import.hiba.cim')}</h3>
    <p class="biztonsag"><Ikon ikon={Info} /> <span>{t('import.forras_erintetlen')}</span></p>
    <HibaPanel mi={tar.hiba.mi} javitas={tar.hiba.javitas} ujra={() => void tar.ujraElonezet()} ujraCimke={t('import.attekint_folytat')} />
    {#if tar.hiba.lista.length}
      <ul class="akadalyok">{#each tar.hiba.lista as sor, i (i)}<li><Ikon ikon={CircleAlert} /><span>{sor}</span></li>{/each}</ul>
    {/if}
    <p class="halvany">{t('import.hiba.megmarad')}</p>
    {#if visszaNyitva && tar.id}
      <Visszaford id={tar.id} fajta="obsidian" onmegse={() => (visszaNyitva = false)} />
    {:else}
      <div class="gombok">
        {#if tar.id}<button type="button" class="m-gomb semleges" onclick={() => (visszaNyitva = true)}>{t('import.visszaford.gomb')}</button>{/if}
        <button type="button" class="m-gomb semleges" onclick={() => tar.vissza()}>{t('import.mappak_valtoztat')}</button>
      </div>
    {/if}

  {:else if tar.fazis === 'kesz'}
    <h3 tabindex="-1" bind:this={cimElem}><Ikon ikon={CircleCheck} meret={20} /> {v2 ? t('import.v2.kesz_cim') : t('import.kesz.cim')}</h3>
    <p class="biztonsag"><Ikon ikon={Info} /> <span>{v2 ? t('import.v2.forras_erintetlen') : t('import.forras_erintetlen')}</span></p>
    {#if kesz && !v2}
      {#if kesz.ismetles}<p class="halvany">{t('import.kesz.ismetles')}</p>{/if}
      <dl data-osszegzes>
        <dt>{t('import.kesz.masolt')}</dt><dd data-mezo="masolt_db">{szam(kesz.masolt_db)}</dd>
        {#if (kesz.megvolt_db ?? 0) > 0}<dt>{t('import.kesz.megvolt')}</dt><dd>{szam(kesz.megvolt_db)}</dd>{/if}
        <dt>{t('import.osszesites.meret')}</dt><dd>{meretSzoveg(kesz.bajt)}</dd>
        <dt>{t('import.kesz.kihagyott')}</dt><dd>{szam(kesz.kihagyott_db)}</dd>
        {#if kesz.cel}<dt>{t('import.kesz.munkater')}</dt><dd class="ut" data-mezo="cel">{kesz.cel}</dd>{/if}
      </dl>
      {#if kesz.beallitasok_irva?.length}
        <p class="halvany">{t('import.kesz.beallitasok')} {kesz.beallitasok_irva.map((k) => beallitasCim(k)).join(', ')}</p>
      {/if}
      {#if kesz.forras_valtozott?.length}
        <div class="figyelem" role="status"><Ikon ikon={TriangleAlert} /> <div><p>{t('import.kesz.forras_valtozott')}</p><ul>{#each kesz.forras_valtozott as ut (ut)}<li class="ut">{ut}</li>{/each}</ul></div></div>
      {/if}
      <p>{t('import.kesz.kovetkezo')}</p>
    {:else if kesz && v2}
      <dl data-osszegzes>
        <dt>{t('import.v2.kesz_valtozas')}</dt><dd data-mezo="valtozas">{szam(kesz.valtozas)}</dd>
        {#if kesz.irt?.length}<dt>{t('import.v2.kesz_irt')}</dt><dd class="ut">{kesz.irt.join(', ')}</dd>{/if}
      </dl>
      {#if kesz.ismetles}<p class="halvany">{t('import.v2.nincs_valtozas')}</p>{/if}
      {#if kesz.ujrainditas}<p class="figyelem" role="status"><Ikon ikon={TriangleAlert} /> <span>{t('import.v2.ujrainditas')}</span></p>{/if}
    {/if}
    {#if visszaNyitva && tar.id}
      <Visszaford id={tar.id} fajta={tar.fajta} onmegse={() => (visszaNyitva = false)} />
    {/if}
    <div class="gombok">
      {#if !visszaNyitva && tar.id}<button type="button" class="m-gomb semleges" onclick={() => (visszaNyitva = true)}>{t('import.visszaford.gomb')}</button>{/if}
      {#if !v2 && munkaterValaszto && !visszaNyitva}<button type="button" class="m-gomb semleges" onclick={() => hejnek({ tipus: 'munkater-valaszto' })}><Ikon ikon={FolderOpen} /> {t('import.kesz.megnyit')}</button>{/if}
      <button type="button" class="m-gomb" onclick={befejez}>{t('import.kesz.gomb')}</button>
    </div>
  {/if}
</section>

<style>
  .folyamat { display: flex; flex-direction: column; gap: var(--t-3); min-width: 0; }
  h3 { display: flex; align-items: center; gap: var(--t-2); margin: 0; font-size: var(--betu-h4); font-weight: var(--suly-kozepes); }
  h3:focus { outline: none; }
  p { margin: 0; }
  form { display: flex; flex-direction: column; gap: var(--t-3); }
  .biztonsag { display: flex; align-items: flex-start; gap: var(--t-2); padding: var(--t-2) var(--t-3); background: var(--hatter-oldalsav); border-radius: var(--kerekites); }
  .halvany { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .mezo-sor { display: flex; flex-direction: column; gap: var(--t-1); }
  .mezo-vezerlo { display: flex; gap: var(--t-2); align-items: center; }
  label { font-weight: var(--suly-kozepes); }
  .mezo { flex: 1; min-width: 0; min-height: var(--magassag-gomb); padding: var(--t-1) var(--t-2); color: var(--szoveg); background: var(--hatter); border: var(--keret-vastag) solid var(--keret-mezo); border-radius: var(--kerekites); font: inherit; }
  .gombok { display: flex; flex-wrap: wrap; gap: var(--t-2); }
  .hiba { display: flex; align-items: flex-start; color: var(--hiba); }
  .figyelem { display: flex; align-items: flex-start; gap: var(--t-2); color: var(--figyelmeztetes); }
  .eredmeny { display: flex; align-items: center; gap: var(--t-2); }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: var(--t-1) var(--t-4); margin: 0; }
  dt { color: var(--szoveg-masodlagos); }
  dd { margin: 0; overflow-wrap: anywhere; user-select: text; }
  progress { width: 100%; accent-color: var(--szoveg-masodlagos); }  /* a haladás állapot: nem burgundi */
  .haladas { display: flex; flex-direction: column; gap: var(--t-2); }
  .megszakit { display: flex; flex-direction: column; gap: var(--t-2); padding: var(--t-4); background: var(--hatter-oldalsav); border: var(--keret-vastag) solid var(--keret); border-radius: var(--kerekites); }
  .megszakit h4 { margin: 0; font-size: var(--betu-torzs); font-weight: var(--suly-kozepes); }
  .akadalyok { list-style: none; margin: 0; padding: 0; }
  .akadalyok li { display: flex; align-items: flex-start; gap: var(--t-2); padding: var(--t-2) var(--t-3); background: var(--hiba-hatter); color: var(--hiba); border-radius: var(--kerekites); }
  ul { margin: 0; padding-inline-start: var(--t-5); }
  .ut { overflow-wrap: anywhere; user-select: text; }
</style>
