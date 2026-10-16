<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import { CircleAlert, FolderOpen, ShieldCheck } from 'lucide';
  import { beallitasok, type BeallitasokTar } from '../lib/beallitasok/allapot.svelte';
  import type { Beallitasok } from '../lib/beallitasok/tipusok';
  import { t, tk } from '../lib/i18n';
  import { modellek, type ModellTar } from '../lib/modellek/allapot.svelte';
  import { ALLAPOT_CIM, SZEREP_CIM, gbSzoveg } from '../lib/modellek/megjelenites';
  import Ajanlott from '../modellek/Ajanlott.svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { naptarHid } from '../lib/naptar/hid.svelte';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import BeallitasSor from '../lib/ui/BeallitasSor.svelte';
  import Kapcsolo from '../lib/ui/Kapcsolo.svelte';
  import ImportFolyamat from '../import/ImportFolyamat.svelte';
  import { ELMENYEK, elmenyModulok, type Elmeny } from './elmeny';

  let { tar = beallitasok, modelltar = modellek, onbezar, onkesz, onai }: { tar?: BeallitasokTar; modelltar?: ModellTar; onbezar: () => void; onkesz?: () => void; onai?: () => void } = $props();
  const LEPESEK = [tk('Üdvözöl a Manifold'), tk('A munkatered'), tk('A jegyzetek nyelve'), tk('Válassz munkamódot'), tk('AI, amikor szükséged van rá'), tk('Adatvédelem és hozzáférés'), tk('Kezdődhet az írás')];
  let lepes = $state(0);
  let piszkozat = $state<Beallitasok | null>(null);
  let eredeti = $state<Beallitasok | null>(null);
  let cimElem = $state<HTMLHeadingElement>();
  let aiUtana = $state(false);
  let telepitesIndult = $state(false);
  let aiBetoltve = false;
  let naptarKeresve = $state(false);
  let alapRev = $state('');
  let importNyitva = $state(false);
  let el = true;

  function atvesz() {
    alapRev = tar.adat?.rev ?? '';
    eredeti = JSON.parse(JSON.stringify(tar.ertek)) as Beallitasok;
    piszkozat = JSON.parse(JSON.stringify(tar.ertek)) as Beallitasok;
  }

  onMount(() => {
    void (async () => {
      if (!tar.adat) await tar.betolt();
      if (el && tar.adat) { atvesz(); await tick(); cimElem?.focus(); }
    })();
    return () => { el = false; };
  });

  // az „AI” lépés első megnyitásakor olvassuk a modelllistát (csak olvas: semmit nem tölt le); a letöltés kattintásra indul (D3)
  $effect(() => {
    if (lepes === 4 && !aiBetoltve) { aiBetoltve = true; void modelltar.betolt(); }
  });
  $effect(() => {
    const lista = modelltar.feladatsor.lista;
    void modelltar.kovetes;
    untrack(() => void modelltar.szinkron(lista));
  });

  async function valt(kovetkezo: number) {
    lepes = kovetkezo;
    await tick();
    cimElem?.focus();
  }

  function bezar() { if (!tar.mentes) onbezar(); }

  function elmenyValaszt(id: Elmeny) {
    if (!piszkozat || !eredeti) return;
    piszkozat.setup.elmeny = id;
    piszkozat.modulok = elmenyModulok(id, eredeti.modulok);
  }

  async function ujratolt() {
    await tar.betolt();
    if (!tar.hiba && tar.adat) {
      atvesz();
      await valt(1);
    }
  }

  async function befejez() {
    if (!piszkozat || tar.mentes || tar.utkozes) return;
    const siker = await tar.ment({
      altalanos: { nyelv: piszkozat.altalanos.nyelv },
      modulok: { ...piszkozat.modulok },
      adatvedelem: { ...piszkozat.adatvedelem },
      setup: { kesz: true, elmeny: piszkozat.setup.elmeny },
    }, alapRev);
    if (!siker || !el) return;
    onkesz?.();
    onbezar();
    if (aiUtana || telepitesIndult) onai?.();
  }
</script>

<Atfedes cimke={t('Manifold beállítása')} nev="setup" onbezar={bezar}>
  <section class="setup" aria-busy={tar.mentes}>
    <header>
      <span class="marka">Manifold</span>
      <button type="button" class="m-gomb link" disabled={tar.mentes} onclick={bezar}>{t('Beállítás később')}</button>
    </header>

    <div class="tartalom">
      {#if piszkozat}
        <p class="lepes" aria-live="polite">{t('{n}. lépés / {osszes}', { n: lepes + 1, osszes: LEPESEK.length })}</p>
        <h2 tabindex="-1" bind:this={cimElem}>{t(LEPESEK[lepes])}</h2>

        {#if lepes === 0}
          <p class="bevezeto">{t('Egy nyugodt hely a gondolataidnak. Írj, kapcsolj össze és találj meg mindent a saját gépeden.')}</p>
          <ul class="igeretek">
            <li>{t('A jegyzeteid egyszerű Markdown-fájlok a saját mappádban.')}</li>
            <li>{t('Az írás, a hivatkozások és a keresés internet és AI-modellek nélkül is működik.')}</li>
            <li>{t('A meglévő jegyzeteid megmaradnak. Minden választás később módosítható.')}</li>
          </ul>
        {:else if lepes === 1}
          <div class="osszefoglalo">
            <Ikon ikon={FolderOpen} meret={20} />
            <div><strong>{tar.adat?.munkater.nev}</strong><p class="ut">{tar.adat?.munkater.vault}</p></div>
          </div>
          <p>{t('Ez a már megnyitott mappa lesz a munkatered. A jegyzetek, mellékletek és a meglévő Obsidian-beállítások megmaradnak.')}</p>
          <p class="halvany">{t('Másik mappát a Fájl menü Munkatér megnyitása parancsával választhatsz.')}</p>
          {#if importNyitva}
            <ImportFolyamat fajta="obsidian" onbezar={() => { importNyitva = false; }} onkesz={() => { importNyitva = false; }} />
          {:else}
            <div class="import-kartya" data-setup-import>
              <strong>{t('import.setup.cim')}</strong>
              <p class="halvany">{t('import.setup.leiras')}</p>
              <button type="button" class="m-gomb semleges" onclick={() => { importNyitva = true; }}>{t('import.setup.gomb')}</button>
            </div>
          {/if}
        {:else if lepes === 2}
          <p>{t('A szerkesztő automatikusan felismeri az éppen írt szöveg nyelvét. Ehhez semmit sem kell beállítanod.')}</p>
          <fieldset>
            <legend>{t('Opcionális tartalmi nyelv')}</legend>
            <label class="valasz"><input type="radio" name="setup-nyelv" value="auto" bind:group={piszkozat.altalanos.nyelv} /><span><strong>{t('Automatikus|setup')}</strong><small>{t('Nincs előre megadott nyelv. Ajánlott többnyelvű jegyzetekhez is.')}</small></span></label>
            <label class="valasz"><input type="radio" name="setup-nyelv" value="hu" bind:group={piszkozat.altalanos.nyelv} /><span>{t('Magyar|setup')}</span></label>
            <label class="valasz"><input type="radio" name="setup-nyelv" value="en" bind:group={piszkozat.altalanos.nyelv} /><span>{t('Angol|setup')}</span></label>
          </fieldset>
          <p class="halvany">{t('Ez a sablonok és az AI-eszközök tartalmi nyelvéhez ad támpontot. Az automatikus felismerés megmarad, a felület angol marad.')}</p>
        {:else if lepes === 3}
          <p>{t('Válassz kezdő modulokat. Ez a látható eszközöket rendezi, a jegyzeteidet nem módosítja.')}</p>
          <fieldset>
            <legend>{t('Mire használod a Manifoldot?')}</legend>
            {#each ELMENYEK as valasztas (valasztas.id)}
              <label class="valasz"><input type="radio" name="setup-elmeny" value={valasztas.id} checked={piszkozat.setup.elmeny === valasztas.id} onchange={() => elmenyValaszt(valasztas.id)} /><span><strong>{t(valasztas.nev)}</strong><small>{t(valasztas.leiras)}</small></span></label>
            {/each}
          </fieldset>
          <p class="halvany">{t('A modulokat a Beállításokban bármikor külön be- és kikapcsolhatod.')}</p>
        {:else if lepes === 4}
          <p class="bevezeto">{t('Az AI opcionális. A jegyzeteid most is használatra készek.')}</p>
          <p>{t('Az AI-eszközökhöz helyi modellek szükségesek. A modelleket külön kell beállítani és ellenőrizni, mielőtt jegyzeteket generálhatnak.')}</p>
          <p>{t('setup.ai.csak_kattintasra')}</p>
          {#if modelltar.hiba && !modelltar.lista}
            <div class="hiba" role="alert"><Ikon ikon={CircleAlert} /><div><strong>{t('setup.ai.lista_hiba')}</strong><p>{modelltar.hiba}</p><p>{t('setup.ai.lista_hiba_teendo')}</p>
              <button type="button" class="m-gomb semleges" disabled={modelltar.betoltes} onclick={() => void modelltar.betolt()}>{t('modellek.ujratolt')}</button></div></div>
          {:else if !modelltar.lista}
            <p role="status" class="halvany">{t('modellek.betoltes')}</p>
          {:else}
            <ul class="ajanlott-lista" aria-label={t('setup.ai.ajanlott_lista')}>
              {#each modelltar.modellek.filter((m) => m.ajanlott) as m (m.id)}
                <li><strong>{m.id}</strong> <span class="halvany">{SZEREP_CIM[m.szerep] ? t(SZEREP_CIM[m.szerep]) : m.szerep} · {gbSzoveg(m.meret_gb)} · {t(ALLAPOT_CIM[m.allapot])}{modelltar.aktiv(m, 'letoltes') ? ` · ${Math.round(modelltar.aktiv(m, 'letoltes')!.szazalek)} %` : ''}</span></li>
              {/each}
            </ul>
            <Ajanlott tar={modelltar} most onindult={(db) => { if (db > 0) telepitesIndult = true; }} />
            {#each modelltar.modellek.filter((m) => modelltar.uzenetek[m.id]?.fajta === 'hiba') as m (m.id)}
              <p class="hiba" role="alert">{m.id}: {modelltar.uzenetek[m.id].szoveg}</p>
            {/each}
          {/if}
          {#if telepitesIndult}<p role="status">{t('setup.ai.indult')}</p>{/if}
          {#if onai}
            <button type="button" class="m-gomb semleges" aria-pressed={aiUtana} onclick={() => { aiUtana = !aiUtana; }}>{aiUtana ? t('setup.ai.kezelo_beallitva') : t('setup.ai.kezelo_utan')}</button>
          {/if}
          <p class="halvany">{t('setup.ai.folytatas')}</p>
        {:else if lepes === 5}
          <p>{t('Te döntöd el, mi működjön a háttérben. A rendszerengedélyekhez külön hozzájárulás szükséges.')}</p>
          <BeallitasSor cim={t('Segéd|setup')} leiras={t('Helyi javaslatok a hivatkozásokhoz és a jegyzetek rendben tartásához.')}><Kapcsolo cimke={t('Segéd|setup')} bind:ertek={piszkozat.adatvedelem.asszisztens} /></BeallitasSor>
          <BeallitasSor cim={t('Használati statisztika|setup')} leiras={t('A tanulás és a munkamenetek statisztikái ezen a gépen.')}><Kapcsolo cimke={t('Használati statisztika|setup')} bind:ertek={piszkozat.adatvedelem.tracker} /></BeallitasSor>
          <BeallitasSor cim={t('Rendszerértesítések|setup')} leiras={t('Feladatok és hibák jelzése a macOS értesítési központjában. Az engedélyt az első értesítés előtt kéri az app.')}><Kapcsolo cimke={t('Rendszerértesítések|setup')} bind:ertek={piszkozat.adatvedelem.ertesitesek} /></BeallitasSor>
          <BeallitasSor cim={t('Naptárkapcsolat|setup')} leiras={t('Események és emlékeztetők használata a rendszer engedélyével.')}><Kapcsolo cimke={t('Naptárkapcsolat|setup')} bind:ertek={piszkozat.adatvedelem.naptar} /></BeallitasSor>
          {#if piszkozat.adatvedelem.naptar}
            {#if naptarHid.elerheto}
              <button type="button" class="m-gomb semleges naptar" disabled={naptarHid.kerdesben} onclick={() => { naptarKeresve = naptarHid.kerd(); }}>{naptarHid.kerdesben ? t('Rendszerengedélyre várunk…') : t('Naptár-hozzáférés kérése')}</button>
              {#if naptarKeresve && !naptarHid.kerdesben}
                <p role="status">{naptarHid.engedely?.esemeny === 'engedelyezve' ? t('A naptár-hozzáférés engedélyezve.') : t('A naptár-hozzáférés még nincs engedélyezve. Később is folytathatod.')}</p>
              {/if}
              {#if naptarKeresve && naptarHid.hiba}<p class="hiba" role="alert"><Ikon ikon={CircleAlert} />{naptarHid.hiba}</p>{/if}
            {:else}
              <p class="halvany">{t('A naptár-hozzáférés a Manifold asztali appban kérhető.')}</p>
            {/if}
          {/if}
        {:else}
          <div class="osszefoglalo"><Ikon ikon={ShieldCheck} meret={20} /><strong>{t('A beállítások készen állnak')}</strong></div>
          <p>{t('A befejezéssel elmentjük a választásaidat ehhez a munkatérhez. A jegyzeteid tartalma nem változik.')}</p>
          <dl>
            <div><dt>{t('Munkatér|setup')}</dt><dd>{tar.adat?.munkater.nev}</dd></div>
            <div><dt>{t('Tartalmi nyelv|setup')}</dt><dd>{piszkozat.altalanos.nyelv === 'auto' ? t('Automatikus|setup') : piszkozat.altalanos.nyelv === 'hu' ? t('Magyar|setup') : t('Angol|setup')}</dd></div>
            <div><dt>{t('Munkamód|setup')}</dt><dd>{t(ELMENYEK.find((e) => e.id === piszkozat?.setup.elmeny)!.nev)}</dd></div>
          </dl>
          <p class="halvany">{t('Minden beállítás elérhető később a Beállításokban (⌘,).')}</p>
        {/if}
      {:else if !tar.hiba}
        <p role="status">{t('Beállítások betöltése…|setup')}</p>
      {/if}

      {#if tar.hiba}
        <div class="hiba" role="alert"><Ikon ikon={CircleAlert} /><div><strong>{tar.utkozes ? t('A beállítások közben megváltoztak|setup') : piszkozat ? t('A beállításokat nem sikerült menteni|setup') : t('A beállításokat nem sikerült betölteni|setup')}</strong><p>{tar.hiba}</p>
          {#if tar.utkozes}<p>{t('Töltsd újra és nézd át a friss beállításokat. Más változtatásait nem írjuk felül.')}</p>{/if}
          {#if tar.utkozes || !piszkozat}<button type="button" class="m-gomb semleges" disabled={tar.betoltes} onclick={() => void ujratolt()}>{t('Újratöltés és áttekintés')}</button>{/if}
        </div></div>
      {/if}
    </div>

    {#if piszkozat && !importNyitva}
      <footer>
        <button type="button" class="m-gomb semleges" disabled={lepes === 0 || tar.mentes} onclick={() => void valt(lepes - 1)}>{t('Vissza')}</button>
        {#if lepes === LEPESEK.length - 1}
          <button type="button" class="m-gomb" disabled={tar.mentes || tar.utkozes} onclick={() => void befejez()}>{tar.mentes ? t('Beállítások mentése…|setup') : tar.hiba ? t('Mentés újra|setup') : t('Írás megkezdése')}</button>
        {:else}
          <button type="button" class="m-gomb" onclick={() => void valt(lepes + 1)}>{lepes === 4 && !aiUtana && !telepitesIndult ? t('Folytatás AI nélkül') : t('Tovább')}</button>
        {/if}
      </footer>
    {/if}
  </section>
</Atfedes>

<style>
  .setup { display: flex; flex-direction: column; height: calc(var(--t-8) * 7); max-height: inherit; min-height: 0; color: var(--szoveg); }
  header, footer { display: flex; flex: none; align-items: center; justify-content: space-between; gap: var(--t-3); padding: var(--t-4) var(--t-5); }
  header { border-bottom: var(--keret-vastag) solid var(--keret); }
  footer { border-top: var(--keret-vastag) solid var(--keret); }
  .marka { font-weight: var(--suly-felkover); }
  .tartalom { flex: 1; min-height: 0; overflow: auto; padding: var(--t-5); }
  .lepes { margin: 0 0 var(--t-2); color: var(--szoveg-halvany); font-size: var(--betu-kicsi); }
  h2 { margin: 0 0 var(--t-4); font-size: var(--betu-h3); line-height: var(--sor-torzs); font-weight: var(--suly-felkover); }
  h2:focus { outline: none; }
  p { margin: 0 0 var(--t-4); }
  .bevezeto { font-size: var(--betu-mezo); line-height: var(--sor-torzs); }
  .halvany, small, dt { color: var(--szoveg-masodlagos); }
  .igeretek { padding-inline-start: var(--t-5); }
  .igeretek li { margin-block: var(--t-3); }
  .osszefoglalo { display: flex; align-items: center; gap: var(--t-3); padding: var(--t-4); margin-bottom: var(--t-4); background: var(--hatter-oldalsav); border-radius: var(--kerekites); }
  .ut { margin: var(--t-1) 0 0; overflow-wrap: anywhere; color: var(--szoveg-masodlagos); }
  fieldset { margin: var(--t-4) 0; padding: 0; border: 0; }
  legend { margin-bottom: var(--t-2); font-weight: var(--suly-kozepes); }
  .valasz { display: flex; align-items: flex-start; gap: var(--t-3); padding: var(--t-3); border: var(--keret-vastag) solid var(--keret-mezo); border-radius: var(--kerekites); margin-block: var(--t-2); cursor: default; }
  .valasz:has(input:checked) { background: var(--hatter-kijelolt); border-color: var(--akcent); }
  input { flex: none; margin-block-start: var(--t-1); accent-color: var(--akcent); }
  small { display: block; margin-top: var(--t-1); font-size: var(--betu-kicsi); line-height: var(--sor-kicsi); }
  strong { font-weight: var(--suly-kozepes); }
  .naptar { margin-block: var(--t-3); }
  .import-kartya { display: flex; flex-direction: column; align-items: flex-start; gap: var(--t-2); padding: var(--t-4); margin-top: var(--t-4); border: var(--keret-vastag) solid var(--keret); border-radius: var(--kerekites); }
  .import-kartya p { margin: 0; }
  .ajanlott-lista { margin: 0 0 var(--t-3); padding-inline-start: var(--t-5); }
  .ajanlott-lista li { margin-block: var(--t-1); }
  .hiba { display: flex; align-items: flex-start; gap: var(--t-2); padding: var(--t-3); border-radius: var(--kerekites); background: var(--hiba-hatter); color: var(--hiba); }
  .hiba p { margin-block: var(--t-2); }
  dl { margin: var(--t-4) 0; }
  dl div { display: grid; grid-template-columns: 1fr 2fr; gap: var(--t-4); padding-block: var(--t-2); }
  dd { margin: 0; overflow-wrap: anywhere; }
</style>
