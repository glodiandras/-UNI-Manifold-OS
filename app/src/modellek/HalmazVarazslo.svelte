<!--
  Saját aranyhalmaz-varázsló (F6): a felhasználó a saját példáiból állít össze mérőhalmazt, amelyen a modell a számára fontos
  szövegekkel mérhető. Lépések: fájl kiválasztása → átnézés és jóváhagyás (tételenként „marad / kiveszem”) → választás (a mérés
  melyik halmazt használja) → törlés (nem végleges: a halmaz félretéve marad). A core ellenőrzi a tételeket; a hibás tétel
  sora és mezője szöveggel jelenik meg. Valós modellt itt nem futtatunk: csak a halmaz készül.
-->
<script lang="ts">
  import { tick, untrack } from 'svelte';
  import { Check, CircleCheck, FileText, Trash2, Upload } from 'lucide';
  import { hibaUzenet } from '../lib/core/api';
  import { beallitasok } from '../lib/beallitasok/allapot.svelte';
  import { t, tk } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import type { ModellTar } from '../lib/modellek/allapot.svelte';
  import { HALMAZ_MEZOK, nyelvNev } from '../lib/modellek/megjelenites';
  import type { SajatTetel } from '../lib/modellek/tipusok';

  let { tar }: { tar: ModellTar } = $props();

  const NYELVEK = ['en', 'hu', 'de', 'fr', 'es', 'it', 'pl', 'ro', 'sk', 'cs'];
  const LEIRAS: Record<string, string> = {
    kiegeszites: tk('modellek.halmaz.mezok.kiegeszites'),
    kifejtes: tk('modellek.halmaz.mezok.kifejtes'),
    osszefoglal_kijeloles: tk('modellek.halmaz.mezok.osszefoglal_kijeloles'),
  };
  const PELDA: Record<string, string> = {
    kiegeszites: '[{ "elotte": "The capital of France is", "utana": ".", "elfogadhato": [" Paris"] }]',
    kifejtes: '[{ "ut": "Notes/Cells.md", "kezd": "The mitochondria", "veg": "produce energy.", "kulcs": [["ATP"]], "tema": [["mitochondria"]] }]',
    osszefoglal_kijeloles: '[{ "ut": "Notes/Cells.md", "kezd": "The mitochondria", "veg": "produce energy.", "kulcs": [["ATP"]] }]',
  };

  const tamogatott = $derived(tar.halmazok?.tamogatott ?? []);
  let feladat = $state('');
  $effect(() => {
    if (!feladat && tamogatott.length) feladat = untrack(() => tamogatott[0]);
  });
  const s = $derived(feladat ? tar.halmazok?.sajat[feladat] : undefined);
  const min = $derived(s?.min_tetel ?? tar.lista?.feladatok[feladat]?.min_tetel ?? 0);
  const alapNyelv = (): string => { const n = beallitasok.ertek.altalanos.nyelv; return n === 'hu' ? 'hu' : 'en'; };
  let nyelv = $state(alapNyelv());
  let tetelek = $state.raw<SajatTetel[] | null>(null);
  let fajlNev = $state('');
  let hiba = $state('');
  let ertesites = $state('');
  let dolgozik = $state(false);
  let megtart = $state<Record<string, boolean>>({});
  let torlesKerdes = $state(false);
  let megsemGomb: HTMLButtonElement | undefined = $state();
  let fajlMezo: HTMLInputElement | undefined = $state();

  // feladatváltáskor a félkész bevitel nem megy át a másik feladatra
  $effect(() => {
    void feladat;
    untrack(() => { tetelek = null; fajlNev = ''; hiba = ''; ertesites = ''; torlesKerdes = false; megtart = {}; });
  });
  // a vázlat tételei alapból mind megmaradnak
  $effect(() => {
    const t0 = s?.allapot === 'vazlat' ? s.tetelek : [];
    untrack(() => { megtart = Object.fromEntries(t0.map((x) => [x.id, true])); });
  });
  const marad = $derived(Object.entries(megtart).filter(([, v]) => v).map(([k]) => k));

  async function olvas(f: File): Promise<string> {
    if (typeof f.text === 'function') return f.text();
    return new Promise((ok, nem) => {
      const r = new FileReader();
      r.onload = () => ok(String(r.result ?? ''));
      r.onerror = () => nem(r.error);
      r.readAsText(f);
    });
  }

  /** A fájl tartalma tétellistává: közvetlen lista vagy egy lista egy kulcs alatt; a kötelező mezők ellenőrzése a core-nál szigorúbb nem. */
  function elemez(szoveg: string): SajatTetel[] {
    let adat: unknown;
    try { adat = JSON.parse(szoveg); } catch { throw new Error(t('modellek.halmaz.hiba.olvashatatlan')); }
    const lista = Array.isArray(adat) ? adat : adat && typeof adat === 'object' && Array.isArray((adat as { tetelek?: unknown }).tetelek) ? (adat as { tetelek: unknown[] }).tetelek : null;
    if (!lista || lista.length === 0) throw new Error(t('modellek.halmaz.hiba.nincs_lista'));
    const kell = HALMAZ_MEZOK[feladat] ?? [];
    for (let i = 0; i < lista.length; i++) {
      const x = lista[i];
      if (!x || typeof x !== 'object' || Array.isArray(x)) throw new Error(t('A(z) {sor}. tétel nem mezőkből álló bejegyzés.', { sor: i + 1 }));
      const hiany = kell.find((k) => !(k in (x as object)));
      if (hiany) throw new Error(t('A(z) {sor}. tételből hiányzik a(z) „{mezo}” mező.', { sor: i + 1, mezo: hiany }));
    }
    return lista as SajatTetel[];
  }

  async function fajlValaszt(e: Event) {
    hiba = ''; ertesites = ''; tetelek = null; fajlNev = '';
    const f = (e.currentTarget as HTMLInputElement).files?.[0];
    if (!f) return;
    fajlNev = f.name;
    try {
      tetelek = elemez(await olvas(f));
    } catch (x) {
      hiba = x instanceof Error ? x.message : hibaUzenet(x);
    }
  }

  async function feltolt() {
    if (!tetelek || dolgozik) return;
    dolgozik = true; hiba = ''; ertesites = '';
    try {
      const o = await tar.halmazLetrehoz(feladat, tetelek, nyelv);
      ertesites = t('A vázlat elkészült {n} tétellel. Nézd át és hagyd jóvá lent.', { n: o.tetelszam });
      tetelek = null; fajlNev = '';
      if (fajlMezo) fajlMezo.value = '';
    } catch (x) {
      hiba = hibaUzenet(x);
    } finally { dolgozik = false; }
  }

  async function jovahagy() {
    if (dolgozik) return;
    dolgozik = true; hiba = ''; ertesites = '';
    try {
      await tar.halmazJovahagy(feladat, marad);
      ertesites = t('modellek.halmaz.jovahagyva');
    } catch (x) {
      hiba = hibaUzenet(x);
    } finally { dolgozik = false; }
  }

  async function valaszt(mi: 'sajat' | 'szallitott') {
    if (dolgozik) return;
    dolgozik = true; hiba = ''; ertesites = '';
    try {
      await tar.halmazValaszt(feladat, mi);
      ertesites = mi === 'sajat' ? t('modellek.halmaz.valasztva_sajat') : t('modellek.halmaz.valasztva_szallitott');
    } catch (x) {
      hiba = hibaUzenet(x);
    } finally { dolgozik = false; }
  }

  async function torlesNyit() {
    torlesKerdes = true;
    await tick();
    megsemGomb?.focus();
  }
  async function torol() {
    if (dolgozik) return;
    dolgozik = true; hiba = ''; ertesites = '';
    try {
      await tar.halmazTorol(feladat);
      torlesKerdes = false;
      ertesites = t('modellek.halmaz.torolve');
    } catch (x) {
      hiba = hibaUzenet(x);
    } finally { dolgozik = false; }
  }
</script>

<section class="varazslo" data-halmaz-varazslo aria-label={t('modellek.halmaz.cim')}>
  <h3>{t('modellek.halmaz.cim')}</h3>
  <p class="leiras">{t('modellek.halmaz.leiras')}</p>

  {#if tar.halmazHiba && !tar.halmazok}
    <p class="hiba" role="alert">{tar.halmazHiba}</p>
    <button type="button" class="m-gomb semleges" onclick={() => void tar.halmazokBetolt()}>{t('modellek.ujratolt')}</button>
  {:else if !tar.halmazok}
    <p role="status" class="leiras">{t('modellek.betoltes')}</p>
  {:else if !tamogatott.length}
    <p class="leiras">{t('modellek.halmaz.nincs_tamogatott')}</p>
  {:else}
    <label class="mezo">{t('modellek.halmaz.feladat')}
      <select bind:value={feladat}>
        {#each tamogatott as f (f)}<option value={f}>{tar.feladatCim(f)}</option>{/each}
      </select>
    </label>

    {#if s}
      <p class="allapot" role="status" data-halmaz-allapot={s.allapot ?? 'nincs'}>
        <Ikon ikon={s.allapot === 'jovahagyott' ? CircleCheck : FileText} />
        <strong>{!s.van ? t('modellek.halmaz.allapot.nincs') : s.allapot === 'jovahagyott' ? t('modellek.halmaz.allapot.jovahagyott') : t('modellek.halmaz.allapot.vazlat')}</strong>
        {#if s.van}<span class="leiras">{t('{n} tétel · nyelv: {nyelv}', { n: s.tetelszam, nyelv: s.nyelv ? nyelvNev(s.nyelv) : '–' })}</span>{/if}
        {#if s.valasztva}<span class="leiras">{t('modellek.halmaz.valasztott')}</span>{/if}
      </p>
    {/if}

    <!-- 3. lépés: választás és törlés -->
    {#if s?.allapot === 'jovahagyott'}
      <div class="gombok">
        {#if s.valasztva}
          <button type="button" class="m-gomb semleges" disabled={dolgozik} onclick={() => void valaszt('szallitott')}>{t('modellek.halmaz.szallitottat_hasznal')}</button>
        {:else}
          <button type="button" class="m-gomb" disabled={dolgozik} onclick={() => void valaszt('sajat')}><Ikon ikon={Check} />{t('modellek.halmaz.sajatot_hasznal')}</button>
        {/if}
        {#if !torlesKerdes}<button type="button" class="m-gomb semleges" disabled={dolgozik} onclick={() => void torlesNyit()}><Ikon ikon={Trash2} />{t('modellek.halmaz.torles')}</button>{/if}
      </div>
    {/if}

    <!-- 2. lépés: átnézés és jóváhagyás -->
    {#if s?.allapot === 'vazlat'}
      <div class="atnezes">
        <p>{t('modellek.halmaz.atnezes')}</p>
        <ul class="tetelek">
          {#each s.tetelek as x (x.id)}
            <li><label class="kapcsolo"><input type="checkbox" bind:checked={megtart[x.id]} />{x.ut ? `${x.id} · ${x.ut}` : x.id}</label></li>
          {/each}
        </ul>
        <p class="leiras" data-szamlalo>{t('{n} / {osszes} tétel marad (legalább {min} kell).', { n: marad.length, osszes: s.tetelszam, min })}</p>
        <div class="gombok">
          <button type="button" class="m-gomb" disabled={dolgozik || marad.length < min} onclick={() => void jovahagy()}><Ikon ikon={Check} />{t('modellek.halmaz.jovahagy')}</button>
          {#if !torlesKerdes}<button type="button" class="m-gomb semleges" disabled={dolgozik} onclick={() => void torlesNyit()}><Ikon ikon={Trash2} />{t('modellek.halmaz.elvet')}</button>{/if}
        </div>
      </div>
    {/if}

    {#if torlesKerdes}
      <div class="megerosites" role="group" aria-label={t('modellek.halmaz.torles_cim')}>
        <p>{t('Törlöd a saját halmazt ehhez: {feladat}?', { feladat: tar.feladatCim(feladat) })}</p>
        <p class="leiras">{t('modellek.halmaz.torles_kovetkezmeny')}</p>
        <div class="gombok">
          <button type="button" class="m-gomb semleges" bind:this={megsemGomb} onclick={() => (torlesKerdes = false)}>{t('modellek.torles.megsem')}</button>
          <button type="button" class="m-gomb" disabled={dolgozik} onclick={() => void torol()}><Ikon ikon={Trash2} />{t('modellek.halmaz.torles_megerosit')}</button>
        </div>
      </div>
    {/if}

    <!-- 1. lépés: fájl kiválasztása (új vagy csere) -->
    <div class="fajl">
      <h4>{s?.van ? t('modellek.halmaz.csere') : t('modellek.halmaz.fajl_cim')}</h4>
      <details>
        <summary>{t('modellek.halmaz.felepites')}</summary>
        <p class="leiras">{t(LEIRAS[feladat] ?? LEIRAS.kiegeszites)}</p>
        <pre>{PELDA[feladat] ?? PELDA.kiegeszites}</pre>
      </details>
      <label class="mezo">{t('modellek.halmaz.fajl')}
        <input type="file" accept=".json,application/json" bind:this={fajlMezo} onchange={fajlValaszt} />
      </label>
      <label class="mezo">{t('modellek.halmaz.nyelv')}
        <select bind:value={nyelv}>{#each NYELVEK as n (n)}<option value={n}>{nyelvNev(n)}</option>{/each}</select>
      </label>
      {#if tetelek}<p class="allapot" role="status"><Ikon ikon={CircleCheck} />{t('{nev}: {n} tétel található.', { nev: fajlNev, n: tetelek.length })}</p>{/if}
      <div class="gombok">
        <button type="button" class="m-gomb" disabled={!tetelek || dolgozik} onclick={() => void feltolt()}><Ikon ikon={Upload} />{t('modellek.halmaz.feltolt')}</button>
      </div>
    </div>

    {#if hiba}<p class="hiba" role="alert" data-halmaz-hiba>{hiba}</p>{/if}
    {#if ertesites}<p class="allapot" role="status"><Ikon ikon={CircleCheck} />{ertesites}</p>{/if}
  {/if}
</section>

<style>
  .varazslo { display: flex; flex-direction: column; gap: var(--t-3); padding: var(--t-4); border: var(--keret-vastag) solid var(--keret); border-radius: var(--kerekites); }
  h3, h4 { margin: 0; font-size: var(--betu-ui); font-weight: var(--suly-felkover); }
  h4 { font-weight: var(--suly-kozepes); }
  p { margin: 0; }
  .leiras { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); line-height: var(--sor-kicsi); }
  .allapot { display: flex; flex-wrap: wrap; align-items: center; gap: var(--t-2); }
  .mezo { display: flex; flex-direction: column; gap: var(--t-1); font-size: var(--betu-kicsi); color: var(--szoveg-masodlagos); }
  select, input[type='file'] { min-width: 0; padding: var(--t-2); color: var(--szoveg); background: var(--hatter); border: var(--keret-vastag) solid var(--keret-mezo); border-radius: var(--kerekites); font: inherit; font-size: var(--betu-ui); }
  .gombok { display: flex; flex-wrap: wrap; gap: var(--t-2); }
  .fajl { display: flex; flex-direction: column; gap: var(--t-2); padding-top: var(--t-3); border-top: var(--keret-vastag) solid var(--keret); }
  .atnezes { display: flex; flex-direction: column; gap: var(--t-2); }
  .tetelek { list-style: none; margin: 0; padding: 0; max-height: calc(var(--t-8) * 3); overflow-y: auto; }
  .kapcsolo { display: flex; align-items: center; gap: var(--t-2); padding: var(--t-1) 0; }
  .megerosites { display: flex; flex-direction: column; gap: var(--t-2); padding: var(--t-3); background: var(--hatter-oldalsav); border-radius: var(--kerekites); }
  pre { margin: var(--t-2) 0 0; padding: var(--t-2); overflow-x: auto; background: var(--hatter-kod); border-radius: var(--kerekites-kicsi); font-family: var(--betu-mono); font-size: var(--betu-kicsi); }
  details summary { cursor: default; color: var(--akcent-szoveg); }
</style>
