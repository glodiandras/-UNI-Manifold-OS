<!--
  A dolgozat-oldal (C28a): egy dolgozat felkészültsége egy nézetben, egy oszlopban, olvasótörzs-szélességben — a szám és
  a kilátás, a témák (összetevőkig lefúrhatóan), a gyenge pontok, az esedékes kártyák és a napi terv. A számot a core
  számolja (átlátható képlet, `core/felkeszultseg/`); az oldal csak olvas és megjelenít: a számok mindig szövegben is
  látszanak (a sáv és a szín csak kiegészíti), mért tudás nélkül nincs szám, hanem „—” és az, hogy mi hiányzik.
  A „Próbakvíz” a C22 után indítható: addig tiltott gomb, a magyarázata a szövegben áll.
-->
<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { FileText } from '../lib/ikon/ikonok';
  import type { NezetProps } from '../lib/elrendezes/nezetek.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import { fajlNev } from '../lib/vault/fajlok.svelte';
  import { napKulcs, napokSzoveg, napRovid, napSzoveg, szinkronSzoveg } from '../ma/datum';
  import { nyitasMod } from '../szerkeszto/linkek/navigacio';
  import { dolgozatAdat } from './modell.svelte';
  import {
    EREDMENY_MEZO_KULCS,
    EREDMENY_MEZO_PELDA,
    KALIBRACIO_SZOVEG,
    KOTES_SZOVEG,
    OSSZETEVO_SZOVEG,
    SZINT_SZOVEG,
    osszetevoAdat,
    percSzoveg,
    pontSzoveg,
    suly,
    szazalek,
    szazalekpont,
    tizedes,
    utolsoSzoveg,
  } from './szoveg';
  import type { Tema } from './tipusok';

  let { ful, aktiv }: NezetProps = $props();
  const { felulet } = kornyezet();

  // A nézet a csatolástól a lebontásig látszik (a panel nem aktív fülét a Panel le sem csatolja): addig tölt és
  // frissül, akkor is, ha a panel nem az aktív (T167).
  onMount(() => dolgozatAdat.megjelenik());

  // A fül állapotában tárolt dolgozat (`nezet.azon`) a kiválasztott; nélküle az első közelgő.
  const fulAzon = $derived(typeof ful.nezet?.azon === 'string' ? (ful.nezet.azon as string) : null);
  $effect(() => {
    const azon = fulAzon;
    if (aktiv && azon) untrack(() => void dolgozatAdat.valaszt(azon));
  });

  const lista = $derived(dolgozatAdat.lista);
  const dolgozatok = $derived(lista?.dolgozatok ?? []);
  const r = $derived(dolgozatAdat.reszlet);
  const ma = $derived(napKulcs(new Date()));
  const regi = $derived(!!(r?.naptar?.regi ?? lista?.naptar?.regi));
  const szinkron = $derived(r?.naptar?.utolso_szinkron ?? lista?.naptar?.utolso_szinkron ?? null);
  const nyitott = $state<Record<string, boolean>>({});

  function valaszt(azon: string) {
    ful.nezet = { ...ful.nezet, tipus: 'dolgozat', azon };
    void dolgozatAdat.valaszt(azon);
  }

  function megnyit(ut: string, e: MouseEvent) {
    felulet.munkaterulet.megnyit(ut, nyitasMod(e));
  }

  /** Mi hiányzik a szám mögül (a core `adatok` mezőiből). */
  const hianyzik = $derived(
    r
      ? ([
          ['kártya', r.adatok.kartya],
          ['kvíz', r.adatok.kviz],
          ['tracker', r.adatok.tracker],
        ] as const)
          .filter(([, a]) => a && a.van === false && a.ok)
          .map(([nev, a]) => `${nev}: ${a.ok}`)
      : [],
  );

  // C28b: a szöveges értékelés csak az aktuális dolgozaté; ha a tények ujjlenyomata eltér, a számok azóta változtak
  const ertekeles = $derived(dolgozatAdat.ertekeles && r && dolgozatAdat.ertekeles.azon === r.azon ? dolgozatAdat.ertekeles : null);
  const ertekelesElavult = $derived(!!(ertekeles && r?.ertekeles_kulcs && ertekeles.kulcs !== r.ertekeles_kulcs));
  const kal = $derived(dolgozatAdat.kalibracio);

  const meta = $derived(r ? [napokSzoveg(r.napok), napSzoveg(r.nap), r.ora, r.tantargy].filter(Boolean).join(' · ') : '');

  function temaMeta(t: Tema): string {
    const reszek = [t.kartya.db ? `${t.kartya.db} kártya${t.kartya.uj ? ` (${t.kartya.uj} új)` : ''}` : 'nincs kártya'];
    reszek.push(t.kviz.db ? `${t.kviz.db} kvízeredmény` : 'nincs kvíz');
    reszek.push(`utolsó tanulás: ${utolsoSzoveg(t.utolso_tanulas, ma)}`);
    if (t.tanult_perc) reszek.push(percSzoveg(t.tanult_perc));
    return reszek.join(' · ');
  }

  const idoSav = (nap: { kezd: string | null; veg: string | null }) =>
    nap.kezd && nap.veg ? `${nap.kezd.slice(11, 16)}–${nap.veg.slice(11, 16)}` : '';
</script>

{#snippet mezoTipp(eleje: string)}
  {eleje}: írj a kiértékelő jegyzet dolgozat-szakaszába egy saját sort, például <code>{EREDMENY_MEZO_PELDA}</code> (vagy
  <code>68%</code>, <code>16/23 (70%)</code>) — a mező a szöveg előtt áll, és az önkalibráció ezt használja.
{/snippet}

{#snippet sav(nev: string, x: number | null, szint: string)}
  <div
    class="sav"
    role="meter"
    aria-label={`${nev} felkészültsége`}
    aria-valuemin={0}
    aria-valuemax={100}
    aria-valuenow={x === null ? undefined : Math.round(x * 100)}
    aria-valuetext={x === null ? 'nincs adat' : `${szazalek(x)}, ${szint}`}
  >
    {#if x !== null}<span style:width={`${Math.round(x * 100)}%`}></span>{/if}
  </div>
{/snippet}

<div class="dolgozat olvasas">
  <header>
    <h1>{r?.cim ?? 'Dolgozat'}</h1>
    {#if r}<p class="meta">{meta}</p>{/if}
    {#if regi}<p class="regi" role="status">{szinkronSzoveg(szinkron)}</p>{/if}
    {#if dolgozatok.length > 1}
      <label class="valto">
        <span>Dolgozat</span>
        <select value={dolgozatAdat.valasztott ?? ''} onchange={(e) => valaszt((e.currentTarget as HTMLSelectElement).value)}>
          {#each dolgozatok as d (d.azon)}
            <option value={d.azon}>{napRovid(d.nap)} · {d.cim}{d.lezart ? ' (lezárt)' : ''}</option>
          {/each}
        </select>
      </label>
    {/if}
  </header>

  {#if dolgozatAdat.hiba && !lista}
    <p class="hiba" role="alert">A dolgozat-oldal adata nem tölthető be: {dolgozatAdat.hiba}</p>
  {:else if !dolgozatAdat.betoltve}
    <p class="ures" role="status">Betöltés…</p>
  {:else if !dolgozatok.length}
    <p class="ures">{lista?.hiba ? lista.hiba.charAt(0).toUpperCase() + lista.hiba.slice(1) : 'Nincs közelgő dolgozat a naptárban.'}</p>
  {:else if dolgozatAdat.reszletHiba}
    <p class="hiba" role="alert">{dolgozatAdat.reszletHiba}</p>
  {:else if r}
    {#if r.lezart}<p class="regi" role="status">Ez a dolgozat már lezárult: a számok a mostani állapotot mutatják.</p>{/if}

    <!-- ------------------------------------------------------------- szám -->
    <section class="fej" aria-label="Felkészültség">
      <div class="nagy" class:nincs={r.szam === null}>
        <span class="ertek">{szazalek(r.szam)}</span>
        <span class="szint">{SZINT_SZOVEG[r.szint ?? 'nincs_adat']}</span>
      </div>
      <div class="kiegeszito">
        {#if r.szam !== null}
          {#if r.kilatas !== null && !r.lezart}
            <p>Ha ma nem tanulsz többet: <strong>{szazalek(r.kilatas)}</strong> a dolgozat napjára.</p>
          {/if}
          <p class="halvany">
            {r.lefedettseg?.van} / {r.lefedettseg?.osszes} témára van mért adat.
            <span title={r.keplet.leiras}>A súlyok kalibrálatlan induló értékek.</span>
          </p>
        {:else}
          <p>Még nincs elég mért adat a számhoz (kártya vagy kvíz kell).</p>
          {#if hianyzik.length}<p class="halvany">{hianyzik.join(' · ')}</p>{/if}
        {/if}
        {#if r.eredmeny}
          <p class="eredmeny">
            A dolgozat eredménye: <strong>{tizedes(r.eredmeny.szazalek)}%</strong>
            {#if r.eredmeny.pont !== null}({pontSzoveg(r.eredmeny.pont, r.eredmeny.max)}){/if}
            {#if r.eredmeny.eredet === 'mezo'}
              <span class="halvany" data-eredet="mezo">— az „{EREDMENY_MEZO_KULCS}::” mezőből: <code>{r.eredmeny.forras}</code></span>
            {:else}
              <span class="halvany" data-eredet="szoveg">— a kiértékelő jegyzet szövegéből: „{r.eredmeny.forras}”</span>
            {/if}
          </p>
          {#if r.eredmeny.eredet !== 'mezo'}
            <p class="halvany mezo-tipp">{@render mezoTipp('Egyértelműbb eredményhez')}</p>
          {/if}
        {:else if r.eredmeny_ellentmondas}
          <p class="halvany" role="status">
            {#if r.eredmeny_ellentmondas.eredet === 'mezo'}
              A kiértékelő „{EREDMENY_MEZO_KULCS}::” mezője nem használható: {r.eredmeny_ellentmondas.ok}
            {:else}
              A kiértékelő jegyzetben ellentmondó eredmény áll ({r.eredmeny_ellentmondas.jeloltek.map((j) => j.forras).join(' · ')}): javítsd
              a jegyzetben, hogy az eredmény egyértelmű legyen.
            {/if}
          </p>
          <p class="halvany mezo-tipp">{@render mezoTipp('Javításként')}</p>
        {:else if r.lezart}
          <p class="halvany mezo-tipp">{@render mezoTipp('Az eredmény megadásához')}</p>
        {/if}
        {#if r.jegyzet}
          <p class="halvany">
            <button type="button" class="szoveg-gomb" onclick={(e) => megnyit(r.jegyzet!, e)} title={r.jegyzet}>
              <Ikon ikon={FileText} /> {fajlNev(r.jegyzet)}
            </button>
            · {r.kotes ? KOTES_SZOVEG[r.kotes.fok] : ''}
          </p>
        {/if}
      </div>
    </section>

    {#each r.figyelmeztetesek as f (f)}
      <p class="figy" role="status">{f}</p>
    {/each}

    <!-- ------------------------------------------------------------- szöveges értékelés (C28b) -->
    <section aria-labelledby="d-ertekeles">
      <h2 id="d-ertekeles">Szöveges értékelés</h2>
      {#if r.szam === null}
        <p class="ures">Mért tudás (kártya vagy kvíz) nélkül nincs mit szavakba önteni.</p>
      {:else}
        <p>
          <button
            type="button"
            class="m-gomb semleges gomb"
            disabled={dolgozatAdat.ertekelesFut}
            onclick={() => void dolgozatAdat.ertekelesKer(r.azon)}
          >
            {dolgozatAdat.ertekelesFut ? 'A helyi modell dolgozik…' : ertekeles ? 'Új értékelés' : 'Értékelés kérése'}
          </button>
          <span class="halvany">A számokat a program számolta; a helyi modell csak szavakba önti őket.</span>
        </p>
      {/if}
      {#if dolgozatAdat.ertekelesHiba}
        <p class="hiba" role="alert">A szöveges értékelés nem készült el: {dolgozatAdat.ertekelesHiba}</p>
      {/if}
      {#if ertekeles}
        {#if ertekeles.szoveg}
          <p class="ertekeles-szoveg">{ertekeles.szoveg}</p>
          <p class="halvany">
            {#if ertekeles.proba}
              Próba — a modell ({ertekeles.modell ?? 'helyi modell'}) erre a feladatra nincs kalibrálva, a szöveget fenntartással olvasd.
            {:else}
              Kalibrált helyi modell ({ertekeles.modell ?? 'helyi modell'}).
            {/if}
            A szövegben csak a fenti számok szerepelhettek, ezt a program ellenőrizte{ertekeles.probalkozas > 1 ? ' (a második próbálkozásra sikerült)' : ''}.
          </p>
          {#if ertekelesElavult}
            <p class="figy" role="status">A számok azóta változtak: kérj új értékelést.</p>
          {/if}
        {:else if ertekeles.uzenet}
          <p class="figy" role="status">{ertekeles.uzenet}</p>
        {/if}
      {/if}
    </section>

    <!-- ------------------------------------------------------------- témák -->
    <section aria-labelledby="d-temak">
      <h2 id="d-temak">Témák <span class="szam">{r.temak.length}</span></h2>
      {#if !r.temak.length}
        <p class="ures">Nincs téma: a felkészülési jegyzet `Source` és `NN` mezője nem hivatkozik jegyzetre.</p>
      {/if}
      {#if r.onmaga && r.temak.length}
        <p class="halvany">A jegyzet nem hivatkozik témajegyzetre: maga a felkészülési jegyzet az egyetlen téma.</p>
      {/if}
      <ul class="lista" role="list">
        {#each r.temak as t, i (t.ut)}
          <li>
            <div class="tema">
              <div class="tema-fej">
                <button type="button" class="szoveg-gomb nev" onclick={(e) => megnyit(t.ut, e)} title={t.ut}>{t.nev}</button>
                <span class="szazalek" class:nincs={t.szam === null}>{szazalek(t.szam)}</span>
                <button
                  type="button"
                  class="kicsi"
                  aria-expanded={!!nyitott[t.ut]}
                  aria-controls={`osszetevo-${i}`}
                  onclick={() => (nyitott[t.ut] = !nyitott[t.ut])}
                >
                  {nyitott[t.ut] ? 'Elrejt' : 'Hogyan?'}
                </button>
              </div>
              {@render sav(t.nev, t.szam, SZINT_SZOVEG[t.szint])}
              <p class="halvany">{temaMeta(t)}</p>
              {#if nyitott[t.ut]}
                <table id={`osszetevo-${i}`}>
                  <thead><tr><th>Összetevő</th><th>Érték</th><th>Bizalom</th><th>Súly</th><th>Adat</th></tr></thead>
                  <tbody>
                    {#each t.osszetevok as o (o.nev)}
                      <tr>
                        <td>{OSSZETEVO_SZOVEG[o.nev]}</td>
                        <td>{szazalek(o.ertek)}</td>
                        <td>{Math.round(o.bizalom * 100)}%</td>
                        <td>{suly(o.suly)}</td>
                        <td class="halvany">{osszetevoAdat(o.nev, o.adat)}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
                {#if t.szam === null}<p class="halvany">Mért tudás (kártya vagy kvíz) nélkül nincs szám; az idő és a frissesség csak finomít.</p>{/if}
                {#if t.kilatas !== null && !r.lezart}<p class="halvany">Kilátás a dolgozat napjára: {szazalek(t.kilatas)}.</p>{/if}
                {#if t.aliasok.length}<p class="halvany">A tanult idő az átnevezés előtti útvonalakat is tartalmazza: {t.aliasok.map(fajlNev).join(', ')}.</p>{/if}
              {/if}
            </div>
          </li>
        {/each}
      </ul>
      {#if r.forrasok.length}
        <p class="halvany">
          Források:
          {#each r.forrasok as f, i (f.ut)}{i ? ', ' : ' '}{fajlNev(f.ut)}{f.oldalak ? ` (${f.oldalak}. oldal)` : ''}{/each}
        </p>
      {/if}
    </section>

    <!-- ------------------------------------------------------------- gyenge pontok -->
    <section aria-labelledby="d-gyenge">
      <h2 id="d-gyenge">Gyenge pontok</h2>
      {#if r.gyenge_pontok.temak.length || r.gyenge_pontok.nincs_adat.length || r.gyenge_pontok.kartyak.length}
        <ul class="lista" role="list">
          {#each r.gyenge_pontok.temak as t (t.ut)}
            <li><span class="szoveg">{t.nev}</span><span class="halvany">gyenge: {szazalek(t.szam)}</span></li>
          {/each}
          {#each r.gyenge_pontok.nincs_adat as t (t.ut)}
            <li><span class="szoveg">{t.nev}</span><span class="halvany">nincs mért adat</span></li>
          {/each}
        </ul>
        {#if r.gyenge_pontok.kartyak.length}
          <h3>Leggyengébb kártyák</h3>
          <ul class="lista" role="list">
            {#each r.gyenge_pontok.kartyak as k (k.azon)}
              <li><span class="szoveg">{k.kerdes}</span><span class="halvany">{szazalek(k.felidezes)}</span></li>
            {/each}
          </ul>
        {/if}
      {:else}
        <p class="ures">Nincs gyenge pont a mért adatok alapján.</p>
      {/if}
      <p>
        <button type="button" class="m-gomb semleges gomb" disabled title="A próbakvíz ebből a nézetből még nem indítható.">Próbakvíz</button>
        <span class="halvany">A próbakvíz egyelőre nem indítható.</span>
      </p>
    </section>

    <!-- ------------------------------------------------------------- esedékes kártyák -->
    <section aria-labelledby="d-kartya">
      <h2 id="d-kartya">Esedékes kártyák <span class="szam">{r.esedekes_kartya ?? 0}</span></h2>
      <p class="halvany">
        {r.esedekes_kartya ?? 0} esedékes és {r.uj_kartya ?? 0} új, még nem tanult kártya ezekhez a témákhoz.
        {#if r.adatok.kartya.kotetlen}{r.adatok.kartya.kotetlen} kártya egyik laphoz sem köthető.{/if}
      </p>
      <p>
        <button type="button" class="m-gomb semleges gomb" disabled title="A kártyák ismétlése ebből a nézetből még nem indítható.">Mai ismétlés</button>
        <span class="halvany">A kártyaismétlés egyelőre nem indítható.</span>
      </p>
    </section>

    <!-- ------------------------------------------------------------- napi terv -->
    <section aria-labelledby="d-terv">
      <h2 id="d-terv">Napi terv <span class="szam">{r.terv.napok.length}</span></h2>
      {#if r.terv.uzenet}<p class="halvany">{r.terv.uzenet}</p>{/if}
      <ul class="lista terv" role="list">
        {#each r.terv.napok as n (n.nap)}
          <li>
            <div class="nap">
              <p class="nap-fej">
                <strong>{napRovid(n.nap)}</strong> <span class="halvany">{napokSzoveg(Math.round((Date.parse(n.nap) - Date.parse(ma)) / 86_400_000))} · {percSzoveg(n.perc)}</span>
                {#if n.javaslat}<span class="jelzo" title="A naptárba írást jóvá kell hagyni a Ma oldalon.">naptár-javaslat ({n.javaslat.allapot === 'uj' ? 'jóváhagyásra vár' : n.javaslat.allapot})</span>{/if}
              </p>
              <ul class="reszlet" role="list">
                {#each n.szeletek as s (s.tema + s.perc)}
                  <li><span class="szoveg">{s.tema}</span><span class="halvany">{percSzoveg(s.perc)} · {s.ok}</span></li>
                {/each}
                {#if n.kartya_esedekes}<li><span class="szoveg">Kártyák</span><span class="halvany">kb. {n.kartya_esedekes} esedékes</span></li>{/if}
                {#each n.naptar as b (b.kezd)}<li><span class="szoveg">A naptárban: {b.cim}</span><span class="halvany">{idoSav(b)}</span></li>{/each}
              </ul>
            </div>
          </li>
        {/each}
      </ul>
    </section>

    <!-- ------------------------------------------------------------- képlet -->
    <section aria-labelledby="d-keplet">
      <h2 id="d-keplet">Hogyan számolódik</h2>
      <details>
        <summary>A képlet és a súlyok</summary>
        <p>{r.keplet.leiras}</p>
        <p class="halvany">
          Súlyok: kártya {suly(r.keplet.suly.kartya)} · kvíz {suly(r.keplet.suly.kviz)} · frissesség {suly(r.keplet.suly.frissesseg)} · idő {suly(r.keplet.suly.ido)}.
          Szám csak akkor születik, ha a mért összetevők bizonyítéka legalább {suly(r.keplet.min_bizonyitek)}. Célszint: {szazalek(r.keplet.cel)}.
          {r.keplet.kalibralt ? 'A súlyokat a valódi dolgozat-eredményekre illesztettük.' : 'A súlyok kalibrálatlan induló értékek.'}
        </p>
      </details>
      <details ontoggle={(e) => (e.currentTarget as HTMLDetailsElement).open && void dolgozatAdat.kalibracioBetolt()}>
        <summary>Önkalibráció és a becslés mért hibája</summary>
        {#if dolgozatAdat.kalibracioTolt && !kal}
          <p class="halvany" role="status">Számolom…</p>
        {:else if dolgozatAdat.kalibracioHiba && !kal}
          <p class="hiba" role="alert">Az önkalibráció állapota nem tölthető be: {dolgozatAdat.kalibracioHiba}</p>
        {:else if kal}
          <p>
            <strong>{KALIBRACIO_SZOVEG[kal.allapot]}</strong> — {kal.pontok} / {kal.kell} kalibrációs pont.
            {#if kal.allapot === 'nem_teljesitheto'}A súlyok addig nem változnak.{/if}
          </p>
          <p>{kal.ok}</p>
          {#if kal.alap.rmse !== null}
            <p class="halvany">
              Az induló súlyokkal {kal.alap.n} lezárt dolgozaton mért hiba: átlagosan {szazalekpont(kal.alap.mae)}
              (négyzetes átlag {szazalekpont(kal.alap.rmse)}, torzítás {szazalekpont(kal.alap.torzitas)}).
              {#if kal.kis_minta}Ennyi dolgozat kevés a következtetéshez: a szám tájékoztató.{/if}
            </p>
          {:else}
            <p class="halvany">A becslési hiba még nem mérhető: nincs egyetlen lezárt dolgozat sem, amelyre egyszerre van eredmény és a dolgozat előtti mért tudás.</p>
          {/if}
          {#if kal.pontok_reszlet.length}
            <table>
              <thead><tr><th>Dolgozat</th><th>Eredmény</th><th>Becslés</th><th>Hiba</th></tr></thead>
              <tbody>
                {#each kal.pontok_reszlet as p (p.azon)}
                  <tr>
                    <td>{napRovid(p.nap)} · {p.cim}</td>
                    <td>{szazalek(p.eredmeny)}</td>
                    <td>{szazalek(p.becsles)}</td>
                    <td>{p.hiba > 0 ? '+' : ''}{tizedes(p.hiba * 100)} százalékpont</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
          {#if kal.kihagyott.length}
            <p class="halvany">Kihagyva: {kal.kihagyott.map((k) => `${napRovid(k.nap)} ${k.cim} (${k.ok})`).join(' · ')}.</p>
          {/if}
          <p class="halvany">A kalibrált súlyok csak akkor kerülnek a beállításokba, ha az illesztés bizonyíthatóan javít.</p>
        {/if}
      </details>
    </section>
  {/if}
</div>

<style>
  .dolgozat {
    max-width: var(--olvasasi-szelesseg);
    margin-inline: auto;
    padding: var(--t-7) var(--t-5) var(--t-8);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg);
  }

  h1 {
    margin: 0;
    font-size: var(--betu-h1);
    line-height: 1.25;
    font-weight: var(--suly-cim);
    letter-spacing: -0.015em;
  }

  .meta {
    margin: var(--t-1) 0 0;
    color: var(--szoveg-masodlagos);
  }

  .regi {
    margin: var(--t-2) 0 0;
    color: var(--szoveg-halvany);
  }

  .valto {
    display: inline-flex;
    align-items: center;
    gap: var(--t-2);
    margin-top: var(--t-3);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  select {
    height: var(--magassag-gomb);
    max-width: 22rem;
    padding: 0 var(--t-2);
    border: var(--keret-vastag) solid var(--keret-eros);
    border-radius: var(--kerekites);
    background: transparent;
    color: var(--szoveg);
    font: inherit;
  }

  select:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  section {
    margin-top: var(--t-6);
  }

  h2,
  h3 {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin: 0 0 var(--t-2);
    padding-bottom: var(--t-1);
    border-bottom: var(--keret-vastag) solid var(--keret);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-weight: var(--suly-felkover);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--szoveg-halvany);
  }

  h3 {
    margin-top: var(--t-4);
    border-bottom: 0;
    padding-bottom: 0;
  }

  .szam {
    font-variant-numeric: tabular-nums;
    letter-spacing: 0;
  }

  p {
    margin: 0 0 var(--t-1);
  }

  .fej {
    display: flex;
    align-items: flex-start;
    gap: var(--t-5);
    flex-wrap: wrap;
  }

  .nagy {
    display: flex;
    flex-direction: column;
    min-width: 7rem;
  }

  .ertek {
    font-size: var(--betu-kijelzo);
    line-height: 1.1;
    font-weight: var(--suly-cim);
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
  }

  .nagy.nincs .ertek {
    color: var(--szoveg-halvany);
  }

  .szint {
    color: var(--szoveg-masodlagos);
  }

  .kiegeszito {
    flex: 1 1 14rem;
    min-width: 0;
    padding-top: var(--t-2);
  }

  .halvany {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .ures {
    margin: 0;
    color: var(--szoveg-halvany);
  }

  .hiba {
    margin: var(--t-4) 0 0;
    padding: var(--t-2) var(--t-3);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
  }

  .figy {
    margin: var(--t-3) 0 0;
    padding: var(--t-2) var(--t-3);
    border-radius: var(--kerekites);
    background: var(--figyelmeztetes-hatter);
    color: var(--figyelmeztetes);
  }

  .eredmeny strong,
  .ertekeles-szoveg {
    color: var(--szoveg);
  }

  .ertekeles-szoveg {
    margin: var(--t-3) 0 var(--t-1);
    max-width: var(--olvasasi-szelesseg);
  }

  details + details {
    margin-top: var(--t-2);
  }

  code {
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
  }

  .lista,
  .reszlet {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .lista > li {
    min-height: var(--magassag-sor);
    padding: var(--t-1) 0;
  }

  .reszlet li,
  .lista:not(.terv) > li:has(> .szoveg) {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--t-3);
  }

  .szoveg {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tema {
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
  }

  .tema-fej {
    display: flex;
    align-items: baseline;
    gap: var(--t-3);
  }

  .nev {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: var(--suly-felkover);
    text-align: left;
  }

  .szazalek {
    font-variant-numeric: tabular-nums;
    font-weight: var(--suly-felkover);
  }

  .szazalek.nincs {
    color: var(--szoveg-halvany);
    font-weight: normal;
  }

  .sav {
    height: 6px;
    border-radius: var(--kerekites-jel);
    background: var(--keret);
    overflow: hidden;
  }

  .sav span {
    display: block;
    height: 100%;
    border-radius: var(--kerekites-jel);
    background: var(--akcent);
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--betu-kicsi);
  }

  th,
  td {
    padding: var(--t-1) var(--t-2) var(--t-1) 0;
    text-align: left;
    font-variant-numeric: tabular-nums;
    border-bottom: var(--keret-vastag) solid var(--keret);
  }

  th {
    color: var(--szoveg-halvany);
    font-weight: var(--suly-felkover);
  }

  .nap {
    padding: var(--t-1) 0;
  }

  .nap-fej {
    display: flex;
    align-items: baseline;
    gap: var(--t-2);
    flex-wrap: wrap;
  }

  .jelzo {
    padding: 0 var(--t-2);
    border: var(--keret-vastag) solid var(--keret-eros);
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-kicsi);
  }

  .reszlet {
    margin-left: var(--t-3);
  }

  button {
    font: inherit;
  }

  .szoveg-gomb {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--akcent-szoveg);
    cursor: pointer;
  }

  .szoveg-gomb:hover {
    text-decoration: underline;
  }

  .kicsi,

  .kicsi {
    height: var(--magassag-suru);
    padding: 0 var(--t-2);
    font-size: var(--betu-kicsi);
  }

  .kicsi:hover,

  .szoveg-gomb:focus-visible,
  .kicsi:focus-visible,
  .gomb:focus-visible,
  summary:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  summary {
    cursor: pointer;
    color: var(--szoveg-masodlagos);
  }
</style>
