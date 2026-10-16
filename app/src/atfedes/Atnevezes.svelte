<!--
  Jegyzet vagy mappa átnevezése / áthelyezése (C10, a legacy I30 szabálya; mappára C11a, 21. döntés): név vagy mappa
  megadása → a TERV (mely fájlok és hány link módosul, soronként előtte→utána; a blokkolók indokkal) → megerősítés →
  egy pillanatkép, utána a core teljes referencia-próbája; az értesítés „Visszavonás” gombbal. A link-átírás és a
  próba a core dolga. A fájlfa húzása a célmappával nyitja: ilyenkor azonnal a terv látszik (a húzás nem ír).
-->
<script lang="ts">
  import { t, tp } from '../lib/i18n';
  import { onMount, untrack } from 'svelte';
  import { ApiHiba } from '../lib/core/api';
  import { FuzzyIndex } from '../lib/kereses/fuzzy';
  import { kornyezet } from '../lib/kornyezet';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import { athelyezheto } from '../lib/vault/fa';
  import { fajlNev, mappa } from '../lib/vault/fajlok.svelte';
  import { atnevezesErtesites, atnevezesTerv, atnevezesVegrehajt, type Terv } from '../szerkeszto/linkek/atnevezes';

  const { felulet, fajlok } = kornyezet();
  // a párbeszéd tárgya a megnyitáskor rögzül (a zárás animációja alatt a felület állapota már üres)
  const cel = untrack(() => felulet.atnevezes!);
  const regi = cel.ut;
  const nevMod = cel.mod === 'nev';
  const mappaMod = cel.mappa === true; // egy mappa (a részfájával együtt) mozog
  const kiterjesztes = mappaMod ? '' : (/\.[^./]+$/.exec(regi)?.[0] ?? '');
  const alapNev = regi.slice(regi.lastIndexOf('/') + 1);
  const cimSzoveg = $derived(
    nevMod ? (mappaMod ? t('Mappa átnevezése') : t('Jegyzet átnevezése')) : mappaMod ? t('Mappa áthelyezése') : t('Jegyzet áthelyezése'),
  );

  let nev = $state('');
  let mappaKereso = $state('');
  let terv = $state<Terv | null>(null);
  let folyamat = $state<'' | 'terv' | 'vegrehajtas'>('');
  let hiba = $state<string | null>(null);
  let bevitel: HTMLInputElement | undefined = $state();
  let doboz: HTMLDivElement | undefined = $state();

  onMount(() => {
    nev = cel.nev ?? (mappaMod ? alapNev : fajlNev(regi));
    if (cel.cel !== undefined) void terveznel(cel.cel); // a fájlfa húzása: a célmappa már megvan, jöhet a terv
    else if (cel.nev !== undefined && nevMod) void terveznel(); // soron belüli átnevezés, amelynek a terve link-változást hoz: itt a terv
    bevitel?.focus();
    bevitel?.select();
  });

  // a terv megjelenésekor a mező (és a fókusz) eltűnik: a fókusz a párbeszédben marad (Esc, Tab-csapda)
  $effect(() => {
    if (terv && doboz && !doboz.contains(document.activeElement)) doboz.focus({ preventScroll: true });
  });

  const mappak = $derived(['', ...fajlok.mappak].filter((m) => !mappaMod || athelyezheto(regi, true, m) || m === mappa(regi)));
  const mappaIndex = $derived(new FuzzyIndex(mappak.map((m) => ({ ertek: m, nev: m || t('(a vault gyökere)'), ut: '' }))));
  const mappaTalalatok = $derived.by(() => {
    const q = mappaKereso.trim();
    if (!q) return mappak.slice(0, 30);
    return mappaIndex.keres(q, { limit: 30 }).map((t) => t.ertek);
  });
  let mappaAktiv = $state(0);
  $effect(() => {
    void mappaTalalatok;
    mappaAktiv = 0;
  });

  function ujUt(mappaNev: string | null): string {
    if (nevMod) {
      let n = nev.trim();
      if (kiterjesztes && n.toLowerCase().endsWith(kiterjesztes.toLowerCase())) n = n.slice(0, -kiterjesztes.length).trimEnd();
      const m = mappa(regi);
      return `${m ? m + '/' : ''}${n}${kiterjesztes}`;
    }
    return `${mappaNev ? mappaNev + '/' : ''}${alapNev}`;
  }

  function bezar() {
    felulet.atfedes = null;
    felulet.atnevezes = null;
  }

  function hibaSzoveg(e: unknown): string {
    return e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e);
  }

  async function terveznel(mappaNev: string | null = null) {
    const uj = ujUt(mappaNev);
    folyamat = 'terv';
    hiba = null;
    try {
      terv = await atnevezesTerv(regi, uj);
    } catch (e) {
      terv = null;
      hiba = hibaSzoveg(e);
    } finally {
      folyamat = '';
    }
  }

  async function vegrehajt() {
    if (!terv?.ok) return;
    folyamat = 'vegrehajtas';
    hiba = null;
    try {
      const r = await atnevezesVegrehajt(terv.regi, terv.uj, terv.terv_hash);
      bezar();
      atnevezesErtesites(r, felulet);
    } catch (e) {
      folyamat = '';
      if (e instanceof ApiHiba && e.adat.valtozott) {
        await terveznel(nevMod ? null : mappa(terv.uj));
        hiba = t('A vault közben megváltozott — az új terv alább látható, nézd át.');
      } else hiba = hibaSzoveg(e) + (e instanceof ApiHiba && Array.isArray(e.adat.proba_hibak) ? `\n${(e.adat.proba_hibak as string[]).join('\n')}` : '');
    } finally {
      folyamat = '';
    }
  }

  function nevBillentyu(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.isComposing && nev.trim()) {
      e.preventDefault();
      void terveznel();
    }
  }

  function mappaBillentyu(e: KeyboardEvent) {
    if (e.isComposing) return;
    const n = mappaTalalatok.length;
    if (e.key === 'ArrowDown') mappaAktiv = n ? (mappaAktiv + 1) % n : 0;
    else if (e.key === 'ArrowUp') mappaAktiv = n ? (mappaAktiv - 1 + n) % n : 0;
    else if (e.key === 'Enter' && n) {
      e.preventDefault();
      void terveznel(mappaTalalatok[mappaAktiv]);
    } else return;
    e.preventDefault();
  }
</script>

<Atfedes cimke={cimSzoveg} nev="atnevezes" onbezar={bezar}>
  <div class="doboz" bind:this={doboz} tabindex="-1">
    <h2 class="cim">{cimSzoveg}</h2>
    <p class="regi" title={regi}>{regi}</p>

    {#if !terv}
      {#if nevMod}
        <label class="mezo">
          <span>{t('Új név')}</span>
          <input bind:this={bevitel} bind:value={nev} onkeydown={nevBillentyu} spellcheck="false" autocomplete="off" aria-describedby="atn-seg" />
        </label>
        <p id="atn-seg" class="seg">
          {t('A linkek a vaultban átíródnak; előtte lista a módosuló fájlokról.')}{mappaMod ? ` ${t('A mappa a jegyzeteivel együtt mozog.')}` : ''}
        </p>
        <div class="gombok">
          <button type="button" class="m-gomb semleges masodlagos" onclick={bezar}>{t('Mégse')}</button>
          <button type="button" class="m-gomb elso" disabled={!nev.trim() || folyamat !== ''} onclick={() => terveznel()}>
            {folyamat === 'terv' ? t('Tervezés…') : t('Tovább')}
          </button>
        </div>
      {:else}
        <label class="mezo">
          <span>{t('Új mappa')}</span>
          <input
            bind:this={bevitel}
            bind:value={mappaKereso}
            onkeydown={mappaBillentyu}
            role="combobox"
            aria-expanded="true"
            aria-controls="atn-mappak"
            aria-activedescendant={`atn-m${mappaAktiv}`}
            placeholder={t('Mappa keresése…')}
            spellcheck="false"
            autocomplete="off"
          />
        </label>
        <ul id="atn-mappak" class="mappak gorgeto" role="listbox" aria-label={t('Mappák')}>
          {#each mappaTalalatok as m, i (m)}
            <li
              id={`atn-m${i}`}
              role="option"
              aria-selected={i === mappaAktiv}
              class:aktiv={i === mappaAktiv}
              class:jelenlegi={m === mappa(regi)}
            >
              <button type="button" tabindex="-1" onclick={() => terveznel(m)}>{m || t('(a vault gyökere)')}</button>
            </li>
          {:else}
            <li class="ures">{t('Nincs ilyen mappa.')}</li>
          {/each}
        </ul>
      {/if}
    {:else}
      <p class="uj">→ <strong>{terv.uj}</strong></p>
      {#if terv.blokkolok.length}
        <ul class="blokkolok" role="alert">
          {#each terv.blokkolok as b (b)}<li>{b}</li>{/each}
        </ul>
      {:else}
        <p class="osszegzes" aria-live="polite">
          {#if terv.mappa && terv.mozgo_fajlok !== undefined}
            <strong>{tp('{n} jegyzet', terv.mozgo_fajlok)}</strong> {t('mozog a mappával.')}
          {/if}
          {#if terv.fajlok.length}
            <strong>{t('{n} fájlban {db} link', { n: terv.fajlok.length, db: terv.modositott_linkek })}</strong> {t('módosul (a vault {osszes} linkjéből).', { osszes: terv.osszes_link })}
          {:else}
            {t('Nincs link, amely átírást igényelne.')}
          {/if}
          {#if terv.uj_feloldott}
            {tp('{n} eddig feloldatlan link mostantól erre a fájlra mutat.', terv.uj_feloldott)}
          {/if}
        </p>
        {#if terv.figyelmeztetesek?.length}
          <ul class="figyelmeztetesek" role="status" aria-label={t('Átnézendő adatbázis-kifejezések')}>
            {#each terv.figyelmeztetesek as w, i (i)}
              <li>
                <strong>{w.ut}</strong> · <code>{w.hely}</code>: {w.uzenet}
              </li>
            {/each}
          </ul>
        {/if}
        <div class="fajlok gorgeto">
          {#each terv.fajlok as f (f.ut)}
            <details>
              <summary><span class="fnev">{f.ut}</span><span class="db">{f.darab}</span></summary>
              <ul>
                {#each f.linkek as l, i (i)}
                  <li>
                    <span class="sor">{l.sor}.</span>
                    <span class="regi-sor">{l.regi.trim()}</span>
                    <span class="uj-sor">{l.uj.trim()}</span>
                  </li>
                {/each}
                {#if f.linkek.length >= 200}<li class="tobb">{t('… a további sorok nem látszanak')}</li>{/if}
              </ul>
            </details>
          {/each}
        </div>
        <p class="seg">{t('Egy pillanatkép készül, utána a teljes vault minden linkjét újra ellenőrzöm; hiba esetén minden visszaáll.')}</p>
      {/if}
      {#if hiba}<p class="hiba" role="alert">{hiba}</p>{/if}
      <div class="gombok">
        <button type="button" class="m-gomb semleges masodlagos" disabled={folyamat !== ''} onclick={() => ((terv = null), (hiba = null))}>{t('Vissza')}</button>
        <button type="button" class="m-gomb elso" disabled={!terv.ok || folyamat !== ''} onclick={vegrehajt}>
          {folyamat === 'vegrehajtas' ? (nevMod ? t('Átnevezés…') : t('Áthelyezés…|folyamat')) : nevMod ? t('Átnevezés') : t('Áthelyezés')}
        </button>
      </div>
    {/if}
    {#if hiba && !terv}<p class="hiba" role="alert">{hiba}</p>{/if}
  </div>
</Atfedes>

<style>
  .doboz:focus {
    outline: none; /* a programozott fókusz (terv megjelenésekor) nem kap gyűrűt */
  }

  .doboz {
    display: flex;
    flex-direction: column;
    gap: var(--t-3);
    padding: var(--t-4) var(--t-5);
    max-height: min(80vh, 40rem);
    overflow: hidden;
  }

  .cim {
    margin: 0;
    font-size: var(--betu-h4);
  }

  .regi {
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--szoveg-halvany);
    font-size: var(--betu-ui);
  }

  .uj {
    margin: 0;
    overflow-wrap: anywhere;
  }

  .mezo {
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
    font-size: var(--betu-ui);
    color: var(--szoveg-masodlagos);
  }

  .mezo input {
    padding: var(--t-2) var(--t-3);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
  }

  .seg {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .gombok {
    display: flex;
    justify-content: flex-end;
    gap: var(--t-2);
  }

  .mappak {
    margin: 0;
    padding: 0;
    max-height: 16rem;
    list-style: none;
    border: 1px solid var(--keret);
    border-radius: var(--kerekites);
  }

  .mappak button {
    display: block;
    width: 100%;
    padding: var(--t-1) var(--t-3);
    text-align: left;
    font-size: var(--betu-ui);
  }

  .mappak li.aktiv {
    background: var(--hatter-kijelolt);
  }

  .mappak li.jelenlegi button {
    color: var(--szoveg-halvany);
  }

  .ures {
    padding: var(--t-2) var(--t-3);
    color: var(--szoveg-halvany);
    font-size: var(--betu-ui);
  }

  .blokkolok {
    margin: 0;
    padding: var(--t-2) var(--t-4);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
    font-size: var(--betu-ui);
  }

  .figyelmeztetesek {
    margin: 0;
    padding: var(--t-2) var(--t-4);
    border-radius: var(--kerekites);
    background: var(--figyelmeztetes-hatter);
    color: var(--figyelmeztetes);
    font-size: var(--betu-ui);
  }

  .figyelmeztetesek code {
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
  }

  .osszegzes {
    margin: 0;
    font-size: var(--betu-ui);
  }

  .fajlok {
    min-height: 0;
    max-height: 18rem;
    border: 1px solid var(--keret);
    border-radius: var(--kerekites);
  }

  details {
    border-bottom: 1px solid var(--keret);
  }

  details:last-child {
    border-bottom: 0;
  }

  summary {
    display: flex;
    gap: var(--t-2);
    padding: var(--t-1) var(--t-3);
    cursor: pointer;
    font-size: var(--betu-ui);
  }

  .fnev {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .db {
    color: var(--szoveg-halvany);
  }

  details ul {
    margin: 0;
    padding: var(--t-1) var(--t-3) var(--t-2);
    list-style: none;
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
  }

  details li {
    display: grid;
    grid-template-columns: 3.5em 1fr;
    gap: 0 var(--t-2);
    padding: 2px 0;
  }

  .sor {
    grid-row: span 2;
    color: var(--szoveg-halvany);
    text-align: right;
  }

  .regi-sor {
    color: var(--hiba);
    overflow-wrap: anywhere;
  }

  .uj-sor {
    color: var(--siker);
    overflow-wrap: anywhere;
  }

  .tobb {
    color: var(--szoveg-halvany);
  }

  .hiba {
    margin: 0;
    white-space: pre-wrap;
    color: var(--hiba);
    font-size: var(--betu-ui);
  }
</style>
