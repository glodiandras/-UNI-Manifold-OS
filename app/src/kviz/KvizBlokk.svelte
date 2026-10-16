<!--
  A beágyazott kvíz kitöltése a jegyzetben (C22a): csendes fejléc → kérdésenként válasz (1–4 / A–D), „biztos vagyok” /
  „csak tippeltem” / „nem tudom”, azonnali visszajelzés a magyarázattal és a forrásmondattal → a végén az elemzés
  (tudod · szerencsés tipp · tévképzet · hiány; mit és hol nézz át). A pontszámot és az elemzést a core adja; a kulcs a
  válasz előtt nincs a kliensben. Csak tokenekből rajzol (25. döntés).
-->
<script lang="ts">
  import { tartalmiNyelv } from '../lib/munkater/nyelv.svelte';
  import { tick } from 'svelte';
  import { nyelv, t, tk, tp } from '../lib/i18n';
  import { linkMegnyit, nyitasMod } from '../szerkeszto/linkek/navigacio';
  import { BETUK } from './allando';
  import { md } from './megjelenites';
  import type { KvizMenet } from './menet.svelte';
  import type { Kategoria } from './tipusok';

  let { menet, forras }: { menet: KvizMenet; forras: string } = $props();

  let gyoker: HTMLDivElement | undefined = $state();
  let kilepesKerdes = $state(false);

  const KATEGORIA: Record<Kategoria, { cim: string; leiras: string; osztaly: string }> = {
    tudja: { cim: tk('tudod'), leiras: tk('helyes, és biztos voltál'), osztaly: 'siker' },
    szerencses: { cim: tk('szerencsés tipp'), leiras: tk('helyes, de tippelted — ingatag'), osztaly: 'figy' },
    tevkepzet: { cim: tk('tévképzet'), leiras: tk('biztos voltál, de rossz — ezt javítsd először'), osztaly: 'hiba' },
    hiany: { cim: tk('hiány'), leiras: tk('nem tudtad (tippelve rossz, vagy kihagyva)'), osztaly: 'halvany' },
  };
  const ALLAPOT: Record<string, string> = { rendben: tk('rendben'), ingatag: tk('ingatag'), hianyos: tk('hiányos') };

  const cim = $derived(menet.adat?.kviz.cim ?? '');
  const utolso = $derived(menet.adat?.elozmenyek.at(-1) ?? null);
  const q = $derived(menet.aktualis);
  const m = $derived(menet.megoldas);
  const v = $derived(menet.valaszok.at(-1) ?? null);
  const utolsoKerdes = $derived(menet.i >= menet.lista.length - 1);

  const itelet = $derived.by(() => {
    if (!m || !v) return '';
    if (m.helyes) return v.tipp ? t('✓ Helyes — de tippelve: érdemes átnézni') : t('✓ Helyes');
    if (v.valasz === null) return t('Ez lett volna a helyes');
    return v.tipp ? t('✗ Nem ez') : t('✗ Nem ez — és biztosra mentél: ez tévképzet, ezt nézd át először');
  });

  /** A fázis- és kérdésváltáskor a fókusz a megfelelő elemre kerül (a billentyűk a blokkon belül élnek). */
  $effect(() => {
    const fazis = menet.fazis;
    void menet.i;
    if (fazis !== 'kerdes' && fazis !== 'visszajelzes' && fazis !== 'elemzes') return;
    void tick().then(() => {
      const cel = gyoker?.querySelector<HTMLElement>('[data-fokusz]') ?? gyoker;
      cel?.focus({ preventScroll: true });
    });
  });

  function billentyu(e: KeyboardEvent) {
    if (menet.billentyu(e)) {
      e.preventDefault();
      e.stopPropagation();
    }
  }

  function megnyit(e: MouseEvent, horgony: string | null) {
    if (!menet.adat) return;
    e.preventDefault();
    void linkMegnyit({ forras, cel: menet.adat.kviz.forras, alcel: horgony }, nyitasMod(e));
  }

  function kilepes() {
    if (menet.valaszok.length) kilepesKerdes = true;
    else void menet.kilep();
  }

  function szazalekSav(): number {
    return menet.lista.length ? Math.round((100 * (menet.i + (menet.fazis === 'visszajelzes' ? 1 : 0))) / menet.lista.length) : 0;
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions (a blokk saját billentyűit kezeli: 1–4, A–D, ↵, T, N) -->
<div class="kviz" bind:this={gyoker} tabindex="-1" role="group" aria-label={t('Kvíz: {cim}', { cim })} lang={nyelv.kod} onkeydown={billentyu}>
  {#if menet.fazis === 'betolt'}
    <p class="kviz-al">{t('Kvíz betöltése…')}</p>
  {:else if menet.fazis === 'hiba'}
    <p class="kviz-hiba" role="alert">{t('A kvíz nem tölthető be: {hiba}', { hiba: menet.hiba ?? '' })}</p>
    <div class="kviz-sor"><button type="button" class="m-gomb semleges kviz-gomb" onclick={() => void menet.betolt()}>{t('Újra')}</button></div>
  {:else if menet.fazis === 'kezdo' && menet.adat}
    <div class="kviz-fej">
      <div>
        <div class="kviz-cim">{t('Kvíz · {cim}', { cim })}</div>
        <div class="kviz-al">
          {tp('{n} kérdés', menet.adat.kviz.kerdesek.length)}{utolso ? ' · ' + t('legutóbb {pont}/{osszes} ({szazalek} %)', { pont: utolso.pont, osszes: utolso.osszes, szazalek: utolso.szazalek }) : ' · ' + t('még nem töltötted ki')}
        </div>
      </div>
      <div class="kviz-sor">
        {#if menet.adat.ujra.length}
          <button type="button" class="m-gomb semleges kviz-gomb" onclick={() => menet.indit('hibasak')}>{t('A hibások és tippeltek újra ({n})', { n: menet.adat.ujra.length })}</button>
        {/if}
        <button type="button" class="m-gomb kviz-gomb elsodleges" data-fokusz onclick={() => menet.indit()}>{t('Kitöltés')}</button>
      </div>
    </div>
    {#if menet.adat.megvaltozott}
      <p class="kviz-megj">{t('A kvíz az utolsó kitöltés óta megváltozott: az előzmények a régi kérdésekre vonatkoznak.')}</p>
    {/if}
    {#if menet.adat.hibak.length}
      <p class="kviz-megj">{tp('{n} hibás kérdés kimarad: {lista}.', menet.adat.hibak.length, { lista: menet.adat.hibak.map((h) => h.fajta.replaceAll('_', ' ')).join(', ') })}</p>
    {/if}
  {:else if (menet.fazis === 'kerdes' || menet.fazis === 'visszajelzes') && q}
    <div class="kviz-fej">
      <div>
        <div class="kviz-cim">{t('Kvíz · {cim}', { cim })}</div>
        <div class="kviz-al">
          {menet.mod === 'hibasak' ? t('csak az előzőleg hibás vagy tippelt kérdések') + ' · ' : ''}{t('{i}/{n}. kérdés', { i: menet.i + 1, n: menet.lista.length })}{q.kerdes.szakasz ? ' · ' + q.kerdes.szakasz : ''}
        </div>
      </div>
      {#if kilepesKerdes}
        <div class="kviz-sor" role="group" aria-label={t('Kilépés')}>
          <span class="kviz-al">{tp('Abbahagyod? {n} megválaszolt kérdés számít.', menet.valaszok.length)}</span>
          <button type="button" class="m-gomb semleges kviz-gomb" onclick={() => { kilepesKerdes = false; void menet.kilep(); }}>{t('Kiértékelés most')}</button>
          <button type="button" class="m-gomb semleges kviz-gomb" onclick={() => (kilepesKerdes = false)}>{t('Folytatom')}</button>
        </div>
      {:else}
        <button type="button" class="m-gomb semleges kviz-gomb" onclick={kilepes}>{t('Kilépés')}</button>
      {/if}
    </div>
    <div class="kviz-sav" aria-hidden="true"><i style:width="{szazalekSav()}%"></i></div>
    {#if q.kerdes.jelolt}
      <p class="kviz-megj">{t('Ezt a kérdést korábban hibásnak jelölted — a pontszámba nem számít.')}</p>
    {/if}
    <div class="kviz-kerdes" lang={tartalmiNyelv.kod} use:md={{ szoveg: q.kerdes.kerdes, ut: forras }}></div>
    <div class="kviz-opciok" role="radiogroup" aria-label={t('Válaszok')}>
      {#each q.sorrend as oi, p (oi)}
        <button
          type="button"
          role="radio"
          class="kviz-opcio"
          class:kivalasztott={menet.valasztott === oi}
          class:helyes={!!m && oi === m.helyes_index}
          class:rossz={!!m && menet.valasztott === oi && oi !== m.helyes_index}
          aria-checked={menet.valasztott === oi}
          disabled={!!m || menet.kuld}
          onclick={() => menet.valaszt(p)}
        >
          <span class="kviz-betu">{BETUK[p]}</span>
          <span class="kviz-opcio-szoveg" lang={tartalmiNyelv.kod} use:md={{ szoveg: q.kerdes.valaszok[oi], ut: forras }}></span>
        </button>
      {/each}
    </div>
    {#if menet.hiba}<p class="kviz-hiba" role="alert">{menet.hiba}</p>{/if}
    {#if menet.fazis === 'kerdes'}
      <div class="kviz-sor kviz-muveletek">
        <button type="button" class="m-gomb kviz-gomb elsodleges" disabled={menet.valasztott === null || menet.kuld} onclick={() => void menet.ellenoriz(false)}>{t('Ellenőrzés — biztos vagyok')}</button>
        <button type="button" class="m-gomb semleges kviz-gomb" disabled={menet.valasztott === null || menet.kuld} onclick={() => void menet.ellenoriz(true)}>{t('Csak tippeltem')}</button>
        <button type="button" class="m-gomb semleges kviz-gomb" disabled={menet.kuld} onclick={() => void menet.nemTudom()}>{t('Nem tudom')}</button>
      </div>
      <p class="kviz-al kviz-sugo">
        <kbd>1</kbd>–<kbd>4</kbd> {t('vagy')} <kbd>A</kbd>–<kbd>D</kbd> {t('választ')} · <kbd>↵</kbd> {t('biztos vagyok')} · <kbd>T</kbd> {t('csak tippeltem')} · <kbd>N</kbd> {t('nem tudom')}. {t('A „tipp” jelzése a válasz előtt számít: ebből látod meg, mit tudsz biztosan, és hol van tévképzet.')}
      </p>
    {:else if m}
      <div class="kviz-visszajelzes" class:rossz={!m.helyes} role="status" aria-live="polite">
        <div class="kviz-itelet">{itelet}</div>
        {#if !m.helyes}
          <div>{t('A helyes válasz:')} <b lang={tartalmiNyelv.kod} use:md={{ szoveg: m.helyes_valasz, ut: forras }}></b></div>
        {/if}
        {#if m.magyarazat}<div lang={tartalmiNyelv.kod} use:md={{ szoveg: m.magyarazat, ut: forras }}></div>{/if}
        <blockquote class="kviz-idezet">
          <div class="kviz-al">{t('A jegyzetben — {szakasz}', { szakasz: m.szakasz ?? cim })}</div>
          <div lang={tartalmiNyelv.kod} use:md={{ szoveg: m.idezet, ut: forras }}></div>
        </blockquote>
        <div class="kviz-sor">
          <button type="button" class="m-gomb semleges kviz-gomb" onclick={(e) => megnyit(e, m.horgony)}>{t('Átnézem a jegyzetben')}</button>
          <button type="button" class="m-gomb semleges kviz-gomb" class:aktiv={q.kerdes.jelolt} title={t('Ha a kérdés vagy a kulcs rossz: nem számít a pontszámba, és a kvízmodell mérésébe kerül')} onclick={() => void menet.jelol()}>
            {q.kerdes.jelolt ? t('Hibásnak jelölve — visszavonás') : t('Hibás a kérdés?')}
          </button>
        </div>
      </div>
      <div class="kviz-sor">
        <button type="button" class="m-gomb kviz-gomb elsodleges" data-fokusz disabled={menet.kuld} onclick={() => void menet.kovetkezo()}>{utolsoKerdes ? t('Kiértékelés') : t('Következő')}</button>
        <span class="kviz-al"><kbd>↵</kbd></span>
      </div>
    {/if}
  {:else if menet.fazis === 'elemzes' && menet.ertekeles}
    {@const e = menet.ertekeles}
    {@const o = e.osszegzes}
    <div class="kviz-fej">
      <div class="kviz-cim">{t('Elemzés · {cim}', { cim })}{e.mod === 'hibasak' ? ' · ' + t('csak a hibásak') : ''}</div>
      <button type="button" class="m-gomb semleges kviz-gomb" data-fokusz onclick={() => void menet.vissza()}>{t('Bezár')}</button>
    </div>
    <div class="kviz-eredmeny">
      <div class="kviz-pontszam"><b>{o.pont}/{o.osszes}</b><span>{o.szazalek} %</span></div>
      <p class="kviz-fo">{e.fo_uzenet}</p>
    </div>
    <div class="kviz-matrix">
      {#each Object.entries(KATEGORIA) as [kat, k] (kat)}
        <div class="kviz-cella {k.osztaly}"><b>{o.matrix[kat as Kategoria] ?? 0}</b><span>{t(k.cim)}</span><small>{t(k.leiras)}</small></div>
      {/each}
    </div>
    {#if e.onismeret.biztos || e.onismeret.tipp}
      <p class="kviz-al">
        {t('Önismeret:')}
        {[e.onismeret.biztos ? t('a biztosnak jelölt válaszaid közül {h}/{n} helyes', { h: e.onismeret.biztos_helyes, n: e.onismeret.biztos }) : '',
          e.onismeret.tipp ? t('a tippjeid közül {h}/{n} talált', { h: e.onismeret.tipp_helyes, n: e.onismeret.tipp }) : ''].filter(Boolean).join(' · ')}.
      </p>
    {/if}
    {#if menet.hiba}<p class="kviz-hiba" role="alert">{menet.hiba}</p>{/if}
    <div class="kviz-sor">
      {#if e.ujra.length}
        <button type="button" class="m-gomb kviz-gomb elsodleges" onclick={() => menet.indit('hibasak')}>{t('A hibások és tippeltek újra ({n})', { n: e.ujra.length })}</button>
      {/if}
      <button type="button" class="m-gomb semleges kviz-gomb" onclick={() => menet.indit()}>{t('Újra az egész')}</button>
      <button type="button" class="m-gomb semleges kviz-gomb" onclick={(ev) => megnyit(ev, null)}>{t('A jegyzet')}</button>
    </div>
    <h4 class="kviz-alcim">{t('Mit és hol nézz át')}</h4>
    {#each e.javaslatok as j, n (j.szakasz)}
      <div class="kviz-javaslat" class:elso={j.prioritas === 1}>
        <div class="kviz-sor">
          <span class="kviz-cimke p{j.prioritas}">{n + 1}. {j.cimke}</span>
          <b lang={tartalmiNyelv.kod}>{j.szakasz}</b>
          <span class="kviz-al">({t('{lista} kérdés', { lista: j.kerdesek.map((x) => `${x}.`).join(', ') })})</span>
          <button type="button" class="m-gomb semleges kviz-gomb" onclick={(ev) => megnyit(ev, j.horgony)}>{t('Átnézem')}</button>
        </div>
        <ul>{#each j.teendok as teendo (teendo)}<li>{teendo}</li>{/each}</ul>
        {#each j.tevkepzetek as tk2 (tk2.sorszam)}
          <div class="kviz-tevk">
            <b>{tk2.sorszam}.</b> <span lang={tartalmiNyelv.kod} use:md={{ szoveg: tk2.kerdes, ut: forras }}></span>
            <div class="kviz-al">{t('azt hitted:')} <b lang={tartalmiNyelv.kod} use:md={{ szoveg: tk2.hitted, ut: forras }}></b> · {t('a jegyzet szerint:')} <b lang={tartalmiNyelv.kod} use:md={{ szoveg: tk2.helyes, ut: forras }}></b></div>
          </div>
        {/each}
        {#each j.idezetek as idezet (idezet)}
          <blockquote class="kviz-idezet"><div class="kviz-al">{t('olvasd újra')}</div><div lang={tartalmiNyelv.kod} use:md={{ szoveg: idezet, ut: forras }}></div></blockquote>
        {/each}
      </div>
    {:else}
      <p class="kviz-siker-uzenet">{t('Nincs mit átnézni: minden válasz helyes volt, és biztos voltál benne.')}</p>
    {/each}
    {#if e.fedetlen_szakaszok.length}
      <p class="kviz-al">{t('Ez a kvíz nem kérdezett ezekből: {lista}. Egy új kvíz más kérdéseket kap.', { lista: e.fedetlen_szakaszok.join(', ') })}</p>
    {/if}
    {#if e.szakaszok.length}
      <details class="kviz-szakaszok">
        <summary>{t('Szakaszonként')}</summary>
        <table>
          <thead><tr><th>{t('Szakasz')}</th><th>{t('Helyes')}</th><th>{t('Állapot')}</th></tr></thead>
          <tbody>
            {#each e.szakaszok as s (s.szakasz)}
              <tr><td lang={tartalmiNyelv.kod}>{s.szakasz}</td><td class="kviz-szam">{s.helyes}/{s.osszes}</td><td><span class="kviz-cimke {s.allapot}">{t(ALLAPOT[s.allapot] ?? s.allapot)}</span></td></tr>
            {/each}
          </tbody>
        </table>
      </details>
    {/if}
  {/if}
</div>

<style>
  .kviz {
    display: block;
    margin-block: var(--t-2);
    padding: var(--t-4);
    border: var(--keret-vastag) solid var(--keret);
    border-radius: var(--kerekites-nagy);
    background: var(--hatter-emelt);
    color: var(--szoveg);
    font-family: var(--betu-rendszer);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    white-space: normal;          /* a szerkesztő sora `pre-wrap`: a sablon térközei ne látsszanak */
    outline: none;
  }

  .kviz-fej {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--t-2) var(--t-4);
  }

  .kviz-cim {
    font-weight: var(--suly-felkover);
  }

  .kviz-al,
  small {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .kviz-sor {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--t-2);
    margin-top: var(--t-3);
  }

  .kviz-fej .kviz-sor {
    margin-top: 0;
  }

  .kviz-gomb.aktiv {
    box-shadow: inset 0 0 0 var(--keret-vastag) var(--figyelmeztetes);
    color: var(--figyelmeztetes);
  }

  .kviz-gomb:focus-visible,
  .kviz-opcio:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  .kviz-sav {
    height: 3px;
    margin-top: var(--t-3);
    border-radius: var(--kerekites-jel);
    background: var(--keret);
    overflow: hidden;
  }

  .kviz-sav i {
    display: block;
    height: 100%;
    background: var(--akcent);
    transition: width var(--mozgas-lassu) var(--mozgas-gorbe);
  }

  .kviz-kerdes {
    margin-top: var(--t-4);
    font-size: var(--betu-torzs);
    line-height: 1.5;
  }

  .kviz-opciok {
    display: grid;
    gap: var(--t-2);
    margin-top: var(--t-3);
  }

  .kviz-opcio {
    display: flex;
    align-items: baseline;
    gap: var(--t-3);
    width: 100%;
    padding: var(--t-2) var(--t-3);
    border: var(--keret-vastag) solid var(--keret-eros);
    border-radius: var(--kerekites);
    background: var(--hatter);
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
    transition:
      background-color var(--mozgas-gyors) var(--mozgas-gorbe),
      border-color var(--mozgas-gyors) var(--mozgas-gorbe);
  }

  .kviz-opcio:hover:not(:disabled) {
    background: var(--hatter-hover);
  }

  .kviz-opcio.kivalasztott {
    border-color: var(--akcent);
    background: var(--hatter-kijelolt);
  }

  .kviz-opcio.helyes {
    border-color: var(--siker);
    background: var(--siker-hatter);
  }

  .kviz-opcio.rossz {
    border-color: var(--hiba);
    background: var(--hiba-hatter);
  }

  .kviz-opcio:disabled {
    cursor: default;
  }

  .kviz-betu {
    flex: none;
    min-width: 1.4em;
    color: var(--szoveg-halvany);
    font-weight: var(--suly-felkover);
  }

  .kviz-opcio-szoveg {
    flex: 1;
    min-width: 0;
  }

  .kviz-visszajelzes {
    display: grid;
    gap: var(--t-2);
    margin-top: var(--t-3);
    padding: var(--t-3) var(--t-4);
    border-left: 3px solid var(--siker);
    border-radius: var(--kerekites);
    background: var(--siker-hatter);
  }

  .kviz-visszajelzes.rossz {
    border-left-color: var(--hiba);
    background: var(--hiba-hatter);
  }

  .kviz-itelet {
    font-weight: var(--suly-felkover);
  }

  .kviz-idezet {
    margin: 0;
    padding: var(--t-1) var(--t-3);
    border-left: 2px solid var(--keret-eros);
    color: var(--szoveg-masodlagos);
  }

  .kviz-hiba {
    margin: var(--t-3) 0 0;
    color: var(--hiba);
  }

  .kviz-megj {
    margin: var(--t-3) 0 0;
    padding: var(--t-2) var(--t-3);
    border-radius: var(--kerekites);
    background: var(--figyelmeztetes-hatter);
    color: var(--figyelmeztetes);
  }

  .kviz-sugo {
    margin: var(--t-3) 0 0;
  }

  kbd {
    padding: 0 var(--t-1);
    border: var(--keret-vastag) solid var(--keret-eros);
    border-radius: var(--kerekites-kicsi);
    font: inherit;
    font-size: var(--betu-kicsi);
  }

  .kviz-eredmeny {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--t-2) var(--t-4);
    margin-top: var(--t-3);
  }

  .kviz-pontszam {
    display: grid;
    min-width: 80px;
    justify-items: center;
  }

  .kviz-pontszam b {
    font-size: var(--betu-h3);
    line-height: 1.2;
  }

  .kviz-fo {
    flex: 1;
    min-width: 220px;
    margin: 0;
  }

  .kviz-matrix {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: var(--t-2);
    margin-top: var(--t-3);
  }

  .kviz-cella {
    display: grid;
    gap: 2px;
    padding: var(--t-2) var(--t-3);
    border: var(--keret-vastag) solid var(--keret);
    border-top-width: 3px;
    border-radius: var(--kerekites);
  }

  .kviz-cella b {
    font-size: var(--betu-h4);
  }

  .kviz-cella.siker {
    border-top-color: var(--siker);
  }

  .kviz-cella.figy {
    border-top-color: var(--figyelmeztetes);
  }

  .kviz-cella.hiba {
    border-top-color: var(--hiba);
  }

  .kviz-cella.halvany {
    border-top-color: var(--keret-mezo);
  }

  .kviz-alcim {
    margin: var(--t-4) 0 var(--t-1);
    font-size: var(--betu-ui);
    font-weight: var(--suly-felkover);
  }

  .kviz-javaslat {
    margin-top: var(--t-2);
    padding: var(--t-3);
    border: var(--keret-vastag) solid var(--keret);
    border-radius: var(--kerekites);
  }

  .kviz-javaslat.elso {
    border-color: var(--hiba);
  }

  .kviz-javaslat ul {
    margin: var(--t-2) 0 0;
    padding-left: var(--t-5);
  }

  .kviz-tevk {
    margin-top: var(--t-2);
  }

  .kviz-cimke {
    padding: 0 var(--t-2);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter-aktiv);
    font-size: var(--betu-kicsi);
    font-weight: var(--suly-kozepes);
  }

  .kviz-cimke.p1,
  .kviz-cimke.hianyos {
    background: var(--hiba-hatter);
    color: var(--hiba);
  }

  .kviz-cimke.p2,
  .kviz-cimke.ingatag {
    background: var(--figyelmeztetes-hatter);
    color: var(--figyelmeztetes);
  }

  .kviz-cimke.p3,
  .kviz-cimke.rendben {
    background: var(--siker-hatter);
    color: var(--siker);
  }

  .kviz-siker-uzenet {
    margin: var(--t-3) 0 0;
    color: var(--siker);
  }

  .kviz-szakaszok {
    margin-top: var(--t-3);
  }

  .kviz-szakaszok summary {
    cursor: pointer;
    color: var(--szoveg-masodlagos);
  }

  .kviz-szakaszok table {
    margin-top: var(--t-2);
    border-collapse: collapse;
  }

  .kviz-szakaszok th,
  .kviz-szakaszok td {
    padding: var(--t-1) var(--t-3) var(--t-1) 0;
    text-align: left;
  }

  .kviz-szam {
    font-variant-numeric: tabular-nums;
  }

  /* a Markdown-renderelés blokkjai a kvízben nem adnak plusz margót */
  .kviz :global(p) {
    margin: 0;
  }

  .kviz :global(.katex) {
    font-size: 1.05em;
  }
</style>
