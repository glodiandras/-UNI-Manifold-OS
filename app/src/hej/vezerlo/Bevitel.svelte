<!-- A „Bevitel” szakasz (C20a, C20b): videólinkek letöltése a stagingbe (yt-dlp, D3: az egyetlen hálózati lépés), és a staging videóinak
     bevitele a vaultba (`video_integralas`: videónként egy gépi írás, a vezérlő „Mit változtatott” nézetéből visszavonható). A behúzott
     vagy kiválasztott videófájl darabonként a core beérkező mappájába kerül, onnan ugyanez a bevitel viszi a vaultba. A felület nem ír a
     vaultba. 84. döntés (javasolt): „Az oldal összes videója (bejárás)” — a core `video_bejaras` feladata felderíti a kezdőoldal alatti
     videóoldalakat (letöltés nélkül), a lista itt jelölhető, és a kijelölt videók egy `video_letoltes` feladatba mennek. -->
<script lang="ts">
  import { t, tp } from '../../lib/i18n';
  import { onMount, tick, untrack } from 'svelte';
  import { ApiHiba } from '../../lib/core/api';
  import { kornyezet } from '../../lib/kornyezet';
  import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
  import { vezerloApi } from '../../lib/vezerlo/api';
  import { feladatsor } from '../../lib/vezerlo/feladatsor.svelte';
  import { LEZART } from '../../lib/vezerlo/tipusok';
  import { videoBevitel } from '../../lib/vezerlo/videoBevitel.svelte';
  import { VIDEO_MAX, linkekBeolvas } from '../../lib/vezerlo/videoLink';
  import { alapKijeloles, forrasLeiras, letoltesTerv, type BejarasEredmeny } from '../../lib/vezerlo/videoBejaras';
  import { videoFajl, videoFeltolt, videoValaszt } from '../../lib/vezerlo/videoFeltoltes';
  import FeladatSor from './FeladatSor.svelte';

  let { onnyit }: { onnyit: (id: string) => void } = $props();
  const { kapcsolat } = kornyezet();

  let szoveg = $state('');
  let mezo: HTMLTextAreaElement | undefined = $state();
  let dolgozik = $state(false);
  let hiba = $state<string | null>(null);
  let bevitel = $state(true);
  let proba = $state(false);
  let varakozik = $state<number | null>(null);
  let feltoltes = $state<string | null>(null);
  let huzas = $state(false);
  // bejárás: a felderítő feladat, a kezdő-link, az eredmény és a kijelölés
  let bejarasMod = $state(false);
  let bejarasFeladat = $state<string | null>(null);
  let bejarasUrl = $state<string | null>(null);
  let eredmeny = $state.raw<BejarasEredmeny | null>(null);
  let kijelolt = $state.raw<Set<string>>(new Set());
  let megerosit = $state(false);
  let betoltottFeladat: string | null = null;
  // 86. döntés (javasolt): a célmappás bevitel — a kényszerített téma-mappa és a kijelölt várakozó forrásmappák
  let celmappa = $state('');
  let fuggo = $state.raw<{ mappa: string; cim: string }[]>([]);
  let temamappak = $state.raw<string[]>([]);
  let celKijelolt = $state.raw<Set<string>>(new Set());
  const cel = $derived(celmappa.trim());
  // a letöltés utáni automatikus bevitel a téma-felismeréssel menne (a core a célmappát a letöltéssel nem kapja): kitöltött
  // célmappánál nem indul, a letöltött videó itt, a célmappába vihető be
  const automatikusBevitel = $derived(bevitel && !cel);

  const beolvasva = $derived(linkekBeolvas(szoveg));
  const indithato = $derived(
    (bejarasMod ? beolvasva.urlek.length === 1 : beolvasva.urlek.length > 0 && beolvasva.urlek.length <= VIDEO_MAX) && !dolgozik,
  );
  const tetelek = $derived(eredmeny?.tetelek ?? []);
  const terv = $derived(letoltesTerv(tetelek, kijelolt, eredmeny?.max_db ?? 50));
  const feladatok = $derived(
    feladatsor.lista
      .filter((f) => ['video_letoltes', 'video_integralas', 'video_bejaras'].includes(f.tipus) && f.allapot !== 'torolve')
      .slice(0, 3),
  );

  // a felderítés vége (kész vagy megállítva: a részlista is mentődik) → az eredmény betöltése; hiba → az üzenet
  $effect(() => {
    const f = bejarasFeladat ? feladatsor.kap(bejarasFeladat) : undefined;
    if (!f || !bejarasUrl || betoltottFeladat === f.id) return;
    if (f.allapot === 'kesz' || f.allapot === 'megallitva') {
      betoltottFeladat = f.id;
      void eredmenyBetolt(bejarasUrl);
    } else if (f.allapot === 'hiba' || f.allapot === 'megszakadt') {
      betoltottFeladat = f.id;
      hiba = f.hiba ?? t('Az oldal bejárása nem sikerült (a részletek a feladat naplójában).');
    }
  });

  async function eredmenyBetolt(url: string) {
    try {
      const e = await vezerloApi.videoBejarasEredmeny(url);
      eredmeny = e;
      kijelolt = alapKijeloles(e.tetelek ?? []);
      megerosit = false;
    } catch (e) {
      hiba = e instanceof ApiHiba ? e.message : String(e);
    }
  }

  function valt(video: string) {
    const uj = new Set(kijelolt);
    if (uj.has(video)) uj.delete(video);
    else uj.add(video);
    kijelolt = uj;
  }

  async function bejarasInditas() {
    const url = beolvasva.urlek[0];
    dolgozik = true;
    hiba = null;
    try {
      const f = await vezerloApi.videoBejaras(url);
      feladatsor.upsert(f);
      bejarasFeladat = f.id;
      bejarasUrl = url;
      betoltottFeladat = null;
      eredmeny = null;
      ertesitesek.ertesit({
        szint: 'info',
        cim: t('Az oldal bejárása elindult'),
        szoveg: t('A videóoldalak listája néhány perc alatt összeáll (a robots.txt és a kért késleltetés szerint); letöltés még nincs.'),
      });
    } catch (e) {
      hiba = e instanceof ApiHiba ? e.message : String(e);
    } finally {
      dolgozik = false;
    }
  }

  async function bejarasLetoltes() {
    if (!terv.urlek.length || terv.tulSok || (terv.megerositesKell && !megerosit) || dolgozik) return;
    dolgozik = true;
    hiba = null;
    try {
      const f = await vezerloApi.videoLetoltes(terv.urlek, automatikusBevitel, { megerosit: terv.megerositesKell && megerosit });
      feladatsor.upsert(f);
      ertesitesek.ertesit({
        szint: 'info',
        cim: t('A letöltés elindult'),
        szoveg: tp('{n} videó a stagingbe; megállítható, és újraindítva a már letöltöttek kimaradnak.', terv.urlek.length),
      });
      eredmeny = null;
      szoveg = '';
    } catch (e) {
      hiba = e instanceof ApiHiba ? e.message : String(e);
    } finally {
      dolgozik = false;
    }
  }

  async function allapotFrissit() {
    try {
      const a = await vezerloApi.videoAllapot();
      varakozik = a.varakozik;
      fuggo = a.fuggo ?? [];
      temamappak = a.temamappak ?? [];
      const megvan = new Set(fuggo.map((f) => f.mappa));
      celKijelolt = new Set([...celKijelolt].filter((m) => megvan.has(m)));
    } catch {
      varakozik = null; // a szám csak tájékoztató: hiba esetén nem látszik, a bevitel így is indítható
    }
  }

  function celValt(mappa: string) {
    const uj = new Set(celKijelolt);
    if (uj.has(mappa)) uj.delete(mappa);
    else uj.add(mappa);
    celKijelolt = uj;
  }

  // a staging állapota a mountkor, és valahányszor egy letöltés vagy bevitel lezárul (a letöltött videó várakozóvá válik, a bevitt
  // kikerül); az újracsatlakozás (`hello`) után is
  let lezartak: string | null = null;
  $effect(() => {
    const most = feladatsor.lista
      .filter((f) => (f.tipus === 'video_letoltes' || f.tipus === 'video_integralas') && LEZART.has(f.allapot))
      .map((f) => `${f.id}:${f.allapot}`)
      .join(',');
    if (most === lezartak) return;
    lezartak = most;
    untrack(() => void allapotFrissit());
  });
  onMount(() => kapcsolat.figyel('hello', () => void allapotFrissit()));

  // a „Videó hozzáadása linkből…” parancs fókuszt kért: a mezőre kerül (akkor is, ha a szakasz csak most rajzolódott ki)
  $effect(() => {
    if (videoBevitel.fokuszKer !== videoBevitel.kezelt) {
      videoBevitel.kezelt = videoBevitel.fokuszKer;
      void tick().then(() => mezo?.focus());
    }
  });

  async function inditas() {
    if (!indithato) return;
    if (bejarasMod) return bejarasInditas();
    dolgozik = true;
    hiba = null;
    try {
      const f = await vezerloApi.videoLetoltes(beolvasva.urlek, automatikusBevitel);
      feladatsor.upsert(f);
      szoveg = '';
      ertesitesek.ertesit({
        szint: 'info',
        cim: t('A letöltés elindult'),
        szoveg: `${tp('{n} videó', beolvasva.urlek.length)} ${t('a stagingbe')}` +
          (automatikusBevitel
            ? t('; utána a vaultba kerül (visszavonható).')
            : cel
              ? t('; a letöltés után a „{cel}” célmappába itt viheted be.', { cel })
              : t('; a vaultba nem ír.')),
      });
    } catch (e) {
      hiba = e instanceof ApiHiba ? e.message : String(e);
    } finally {
      dolgozik = false;
    }
  }

  async function bevitelInditas() {
    if (dolgozik || (cel && !celKijelolt.size)) return;
    dolgozik = true;
    hiba = null;
    try {
      const mappak = fuggo.map((f) => f.mappa).filter((m) => celKijelolt.has(m));
      feladatsor.upsert(await vezerloApi.videoBevitel(proba, cel ? { temaMappa: cel, mappak } : undefined));
      ertesitesek.ertesit({
        szint: 'info',
        cim: t('A bevitel elindult'),
        szoveg: (proba ? t('Próba: a vault klónjára ír.') : t('Videónként egy gépi írás; a „Mit változtatott” nézetből visszavonható.')) +
          (cel ? ` ${t('Célmappa: {cel}.', { cel })}` : ''),
      });
      celKijelolt = new Set();
    } catch (e) {
      hiba = e instanceof ApiHiba ? e.message : String(e);
    } finally {
      dolgozik = false;
      void allapotFrissit();
    }
  }

  async function fajlokBe(fajlok: File[]) {
    if (dolgozik || !fajlok.length) return;
    if (!fajlok.some(videoFajl)) {
      hiba = t('Csak videófájl vihető be (mp4, m4v, mov, mkv, webm, avi).');
      return;
    }
    dolgozik = true;
    hiba = null;
    try {
      const f = await videoFeltolt(fajlok, {
        proba,
        haladas: (h) => (feltoltes = `${h.fajl} — ${h.szazalek}%${h.n > 1 ? ` (${h.i + 1}/${h.n})` : ''}`),
      });
      feladatsor.upsert(f);
      ertesitesek.ertesit({ szint: 'info', cim: t('A videó feltöltve'), szoveg: t('A bevitel a háttérben fut (a vezérlőben követhető).') });
    } catch (e) {
      hiba = e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e);
    } finally {
      dolgozik = false;
      feltoltes = null;
    }
  }
</script>

<form
  onsubmit={(e) => {
    e.preventDefault();
    void inditas();
  }}
>
  <label class="cimke" for="video-linkek">
    {bejarasMod ? 'Az oldal linkje' : t('Videólinkek')} <span class="halvany">{bejarasMod ? t('(a kezdőoldal)') : t('(soronként egy)')}</span>
  </label>
  <textarea
    id="video-linkek"
    bind:this={mezo}
    bind:value={szoveg}
    rows="3"
    spellcheck="false"
    autocomplete="off"
    placeholder="https://…"
    onkeydown={(e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        void inditas();
      }
    }}
  ></textarea>
  {#if szoveg.trim() && beolvasva.hibak.length}
    <ul class="figy" aria-label={t('A link nem használható')}>
      {#each beolvasva.hibak as h (h)}<li>{h}</li>{/each}
    </ul>
  {/if}
  <div class="sor">
    <button type="submit" class="m-gomb semleges gomb" disabled={!indithato}>{bejarasMod ? t('Videók keresése') : t('Letöltés')}</button>
    <span class="halvany">{beolvasva.urlek.length && !bejarasMod ? `${beolvasva.urlek.length} link` : ''}</span>
  </div>
  <label class="halvany kapcsolo"><input type="checkbox" bind:checked={bejarasMod} /> {t('Az oldal összes videója (bejárás)')}</label>
  {#if bejarasMod && beolvasva.urlek.length > 1}<p class="halvany leiras">{t('A bejáráshoz egy kezdőoldal kell.')}</p>{/if}
  <label class="halvany kapcsolo"><input type="checkbox" bind:checked={bevitel} disabled={!!cel} /> {t('Utána a vaultba is')}</label>
  {#if cel}
    <p class="halvany leiras">
      {t('A célmappa ki van töltve: a letöltés után a bevitel nem indul magától (a téma-felismerés helyett a „{cel}” mappába itt, lent viheted be).', { cel })}
    </p>
  {/if}
  <p class="halvany leiras">
    {t('A letöltés hálózatot használ (yt-dlp). A videó a staging-be kerül (a nem natív formátum mp4-re alakul); a vaultba a bevitel viszi.')}
  </p>
  {#if hiba}<p class="hiba" role="alert">{hiba}</p>{/if}
</form>

{#if eredmeny?.kesz}
  <section class="bejaras" aria-label={t('Az oldal videói')}>
    <p class="halvany">
      {tp('{n} videó', tetelek.length)} · {tp('{n} oldal olvasva', eredmeny.oldalak ?? 0)}{eredmeny.megszakitva ? ` · ${t('a bejárás megállítva (részlista)')}` : ''}
    </p>
    {#if tetelek.length}
      <ul class="tetelek">
        {#each tetelek as v (v.video)}
          <li>
            <label class="kapcsolo">
              <input type="checkbox" checked={kijelolt.has(v.video)} onchange={() => valt(v.video)} />
              <span class="tetel-cim">{v.cim}</span>
              {#if v.megvan}<span class="halvany">{t('megvan')}</span>{/if}
            </label>
            <span class="halvany tetel-url" title={v.oldal}>{v.video}</span>
            <span class="halvany tetel-url tetel-forras">{forrasLeiras(v)}{v.diak ? ` · ${t('diák: csak a link')}` : ''}</span>
          </li>
        {/each}
      </ul>
      {#if terv.megerositesKell && !terv.tulSok}
        <label class="halvany kapcsolo">
          <input type="checkbox" bind:checked={megerosit} /> {t('Igen, mind a {n} videót letöltöm (több, mint {max})', { n: terv.urlek.length, max: eredmeny.max_db ?? 50 })}
        </label>
      {/if}
      {#if terv.tulSok}<p class="figy">{t('Egy feladatban legfeljebb 200 videó; szűkítsd a kijelölést.')}</p>{/if}
      <div class="sor">
        <button
          type="button"
          class="m-gomb semleges gomb"
          disabled={!terv.urlek.length || terv.tulSok || (terv.megerositesKell && !megerosit) || dolgozik}
          onclick={() => void bejarasLetoltes()}>{t('Letöltés ({n})', { n: terv.urlek.length })}</button
        >
      </div>
    {:else}
      <p class="halvany leiras">{t('Ezen az oldalon (és az alatta lévőkön) nem találtam beágyazott videót.')}</p>
    {/if}
  </section>
{/if}

<div class="bevitel">
  <div
    class="huzo"
    class:aktiv={huzas}
    role="button"
    tabindex="0"
    aria-label={t('Videófájl behúzása vagy kiválasztása')}
    ondragover={(e) => {
      e.preventDefault();
      huzas = true;
    }}
    ondragleave={() => (huzas = false)}
    ondrop={(e) => {
      e.preventDefault();
      huzas = false;
      void fajlokBe(Array.from(e.dataTransfer?.files ?? []));
    }}
    onclick={() => void videoValaszt().then(fajlokBe)}
    onkeydown={(e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        void videoValaszt().then(fajlokBe);
      }
    }}
  >
    {feltoltes ?? t('Videófájl behúzása vagy kiválasztása…')}
  </div>
  <label class="cimke" for="video-celmappa">{t('Célmappa (téma)')} <span class="halvany">{t('(üresen: a téma-felismerés dönt)')}</span></label>
  <input
    id="video-celmappa"
    class="mezo"
    list="video-temamappak"
    bind:value={celmappa}
    spellcheck="false"
    autocomplete="off"
    placeholder={t('pl. A01 - Téma neve')}
  />
  <datalist id="video-temamappak">
    {#each temamappak as t (t)}<option value={t}></option>{/each}
  </datalist>
  {#if cel}
    {#if fuggo.length}
      <ul class="tetelek" aria-label={t('A célmappába vihető videók')}>
        {#each fuggo as f (f.mappa)}
          <li>
            <label class="kapcsolo" title={f.mappa}>
              <input type="checkbox" checked={celKijelolt.has(f.mappa)} onchange={() => celValt(f.mappa)} />
              <span class="tetel-cim">{f.cim}</span>
            </label>
            <span class="halvany tetel-url">{f.mappa}</span>
          </li>
        {/each}
      </ul>
      <div class="sor">
        <button type="button" class="m-gomb link" onclick={() => (celKijelolt = new Set(fuggo.map((f) => f.mappa)))}>{t('Mind')}</button>
        <button type="button" class="m-gomb link" onclick={() => (celKijelolt = new Set())}>{t('Egyik sem')}</button>
      </div>
    {:else}
      <p class="halvany leiras">{t('Nincs várakozó videó a stagingben.')}</p>
    {/if}
    <p class="halvany leiras">
      {t('A kijelölt videók a(z) „{cel}” mappába kerülnek (a hiányzó mappa létrejön): a felirat és a forrásleíró jegyzet a mappa média-almappájába, kötés csak a mappa saját jegyzeteihez. A téma-modell nem fut.', { cel })}
    </p>
  {/if}
  <div class="sor">
    <button
      type="button"
      class="m-gomb semleges gomb"
      disabled={dolgozik || varakozik === 0 || (!!cel && !celKijelolt.size)}
      onclick={() => void bevitelInditas()}
    >
      {#if cel}{t('Bevitel a célmappába ({n})', { n: celKijelolt.size })}{:else}{t('Bevitel a vaultba')}{varakozik ? ` (${varakozik})` : ''}{/if}
    </button>
    <label class="halvany kapcsolo"><input type="checkbox" bind:checked={proba} /> {t('Próba (a vault klónján)')}</label>
  </div>
  <p class="halvany leiras">
    {t('A videó a vault videómappája alá, a felirat és a forrásleíró jegyzet a téma média-almappájába, a kötések a jegyzetek Source mezőjébe kerülnek. Videónként egy gépi írás: a feladat „Mit változtatott” nézetéből visszavonható.')}
  </p>
</div>

{#if feladatok.length}
  <ul class="lista" aria-label={t('A legutóbbi letöltések')}>
    {#each feladatok as f (f.id)}<li><FeladatSor feladat={f} {onnyit} /></li>{/each}
  </ul>
{/if}

<style>
  form {
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
  }

  .cimke {
    color: var(--szoveg);
    font-size: var(--betu-kicsi);
  }

  .halvany {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  textarea {
    width: 100%;
    resize: vertical;
    min-height: 56px;
    padding: var(--t-2);
    border: var(--keret-vastag) solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: transparent;
    color: var(--szoveg);
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .mezo {
    width: 100%;
    height: var(--magassag-suru);
    padding: 0 var(--t-2);
    border: var(--keret-vastag) solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: transparent;
    color: var(--szoveg);
    font-size: var(--betu-kicsi);
  }

  .sor {
    display: flex;
    align-items: center;
    gap: var(--t-2);
  }

  .gomb {
    display: inline-flex;
    align-items: center;
    height: var(--magassag-suru);
  }

  .leiras {
    margin: 0;
    line-height: var(--sor-kicsi);
    max-width: 40ch;
  }

  .figy {
    margin: 0;
    padding-left: var(--t-4);
    color: var(--figyelmeztetes);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .hiba {
    margin: 0;
    padding: var(--t-2);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
    font-size: var(--betu-kicsi);
  }

  .bejaras {
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
    margin-top: var(--t-3);
  }

  .tetelek {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 320px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
  }

  .tetelek li {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .tetel-cim {
    color: var(--szoveg);
    font-size: var(--betu-kicsi);
  }

  .tetel-url {
    padding-left: var(--t-4);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .bevitel {
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
    margin-top: var(--t-3);
  }

  .huzo {
    padding: var(--t-3);
    border: var(--keret-vastag) dashed var(--keret-mezo);
    border-radius: var(--kerekites);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    text-align: center;
    cursor: pointer;
  }

  .huzo.aktiv {
    border-color: var(--keret-eros);
    color: var(--szoveg);
  }

  .kapcsolo {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
  }

  .lista {
    list-style: none;
    margin: var(--t-2) 0 0;
    padding: 0;
    margin-inline: calc(-1 * var(--t-2));
  }
</style>
