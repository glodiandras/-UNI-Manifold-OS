<!--
  Törölt jegyzet visszahozása (13-palette-04): a pillanatkép-tárolóból a már nem létező (törölt) jegyzetek, canvasok és nézetek
  listája (a legújabb törlés elöl, ékezetfüggetlen szűréssel), a törlés előtti szöveg előnézete, és a visszahozás ÚJ FÁJLKÉNT —
  az eredeti helyre (ha ott már áll valami, nem ír, hanem magyarázatot ad) vagy új néven. A visszaállítás a core-é
  (`/api/vault/elozmeny/visszahoz`, egy `Mos-Visszaallit` pillanatkép-commit); maga is visszavonható az értesítésből.
-->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { ApiHiba, hibaUzenet, kerdez } from '../lib/core/api';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { fajlIkon } from '../lib/ikon/fajlIkon';
  import { RotateCcw, TriangleAlert } from '../lib/ikon/ikonok';
  import { kornyezet } from '../lib/kornyezet';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import ListaValaszto from '../lib/ui/ListaValaszto.svelte';
  import { elozmenyApi, elozmenyIdo, type ElozmenyValtozat, type ToroltBejegyzes } from '../lib/vault/elozmeny';
  import { fajlNev, mappa } from '../lib/vault/fajlok.svelte';

  const ELONEZET_MAX = 20000;
  const { felulet } = kornyezet();

  let lekerdezes = $state('');
  let elemek = $state.raw<ToroltBejegyzes[]>([]);
  let betolt = $state(true);
  let listaHiba = $state<string | null>(null);

  let valasztott = $state.raw<ToroltBejegyzes | null>(null);
  let valtozat = $state.raw<ElozmenyValtozat | null>(null);
  let elonezetVerzio = 0;
  let el = true;
  let elonezetHiba = $state<string | null>(null);
  let nev = $state('');
  let dolgozik = $state(false);
  let hiba = $state<string | null>(null);
  let utkozes = $state(false);
  let nevMezo: HTMLInputElement | undefined = $state();

  // ------------------------------------------------------------------ a lista
  let ido: ReturnType<typeof setTimeout> | null = null;
  let vezerlo: AbortController | null = null;
  $effect(() => {
    const kerdes = lekerdezes.trim();
    if (ido) clearTimeout(ido);
    ido = setTimeout(() => void toltLista(kerdes), kerdes ? 150 : 0);
  });
  onDestroy(() => {
    el = false;
    elonezetVerzio++;
    if (ido) clearTimeout(ido);
    vezerlo?.abort();
  });

  async function toltLista(kerdes: string) {
    vezerlo?.abort();
    const v = (vezerlo = new AbortController());
    betolt = true;
    try {
      const d = await elozmenyApi.torolt(kerdes, v.signal);
      if (v.signal.aborted) return;
      elemek = d.torolt;
      listaHiba = null;
    } catch (e) {
      if (v.signal.aborted) return;
      elemek = [];
      listaHiba = e instanceof ApiHiba && e.statusz === 404 ? t('Az előzmények nem érhetők el (nincs pillanatkép-tároló).') : hibaUzenet(e);
    } finally {
      if (!v.signal.aborted) betolt = false;
    }
  }

  const ures = $derived(
    listaHiba ?? (betolt ? t('Betöltés…') : lekerdezes.trim() ? t('Nincs törölt jegyzet erre: „{kif}”', { kif: lekerdezes.trim() }) : t('Nincs törölt jegyzet.')),
  );

  // ------------------------------------------------------------------ az előnézet és a visszahozás
  function kivalaszt(b: ToroltBejegyzes) {
    const verzio = ++elonezetVerzio;
    valasztott = b;
    valtozat = null;
    elonezetHiba = null;
    hiba = null;
    utkozes = false;
    nev = `${fajlNev(b.ut)} ${t('(visszaállítva)')}`;
    elozmenyApi.toroltValtozat(b.ut, b.sha).then(
      (v) => { if (verzio === elonezetVerzio) valtozat = v; },
      (e) => { if (verzio === elonezetVerzio) elonezetHiba = hibaUzenet(e); },
    );
  }

  function vissza() {
    elonezetVerzio++;
    valasztott = null;
    valtozat = null;
    hiba = null;
  }

  const kiterjesztes = $derived(valasztott ? (valasztott.ut.match(/\.[^./]+$/)?.[0] ?? '') : '');
  const elonezet = $derived.by(() => {
    if (!valtozat) return '';
    if (valtozat.szoveg_ok === 'kodolas') return t('A változat nem érvényes UTF-8, az előnézet nem érhető el.');
    if (valtozat.szoveg_ok === 'nagy') return t('A változat túl nagy az előnézethez.');
    const sz = valtozat.szoveg ?? '';
    return sz.length > ELONEZET_MAX ? `${sz.slice(0, ELONEZET_MAX)}\n…` : sz;
  });

  async function visszahoz(mod: 'eredeti' | 'uj') {
    const b = valasztott;
    if (!b || dolgozik) return;
    dolgozik = true;
    hiba = null;
    try {
      const r = await elozmenyApi.visszahoz(b.ut, b.sha, mod, mod === 'uj' ? nev.trim() + kiterjesztes : undefined);
      ertesitesek.ertesit({
        szint: 'siker',
        cim: t('Visszahozva'),
        szoveg: r.ut,
        muvelet: r.sha ? { nev: t('Visszavonás'), futtat: () => void visszavon(r.sha as string, r.ut) } : undefined,
        idotartam: 15000,
      });
      if (el && felulet.atfedes === 'torolt') {
        felulet.atfedes = null;
        felulet.munkaterulet.megnyit(r.ut, 'ujful');
      }
    } catch (e) {
      if (!el || felulet.atfedes !== 'torolt') {
        ertesitesek.ertesit({ szint: 'hiba', cim: t('A visszahozás nem sikerült'), szoveg: hibaUzenet(e), idotartam: 0 });
      } else if (e instanceof ApiHiba && e.kod === 'elozmeny.visszahoz_utkozes') {
        utkozes = true;
        hiba = e.message;
        queueMicrotask(() => nevMezo?.focus());
      } else {
        hiba = hibaUzenet(e);
      }
    } finally {
      dolgozik = false;
    }
  }

  async function visszavon(sha: string, ut: string) {
    try {
      await kerdez('/api/pillanat/vault/visszavonas', { metodus: 'POST', torzs: { sha }, idokorlat: 60000 });
      ertesitesek.ertesit({ szint: 'siker', cim: t('A visszahozás visszavonva'), szoveg: ut, idotartam: 4000 });
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: t('A visszavonás nem sikerült'), szoveg: hibaUzenet(e), idotartam: 0 });
    }
  }

  function bezar() {
    felulet.atfedes = null;
  }
</script>

<Atfedes cimke={t('Törölt jegyzet visszahozása')} nev="torolt" onbezar={bezar} szeles={!!valasztott}>
  {#if !valasztott}
    <ListaValaszto
      {elemek}
      kulcs={(b) => `${b.ut}\0${b.sha}`}
      bind:lekerdezes
      helyorzo={t('Törölt jegyzet keresése…')}
      cimke={t('Törölt jegyzet keresése')}
      {ures}
      onvalaszt={(b) => kivalaszt(b)}
      onbezar={bezar}
    >
      {#snippet sor(b: ToroltBejegyzes)}
        <span class="ikon"><Ikon ikon={fajlIkon(b.ut.toLowerCase().endsWith('.canvas') ? 'canvas' : b.ut.toLowerCase().endsWith('.base') ? 'base' : 'md')} /></span>
        <span class="nev">{fajlNev(b.ut)}</span>
        <span class="ut">{mappa(b.ut) || '/'}</span>
        <span class="ido">{elozmenyIdo(b.datum)}</span>
      {/snippet}
      {#snippet lablec()}
        {#if listaHiba}<span role="alert" class="hiba-sor"><Ikon ikon={TriangleAlert} meret={14} /> {listaHiba}</span>{/if}
        <span><kbd>↑↓</kbd> {t('választás')}</span>
        <span><kbd>↩</kbd> {t('előnézet')}</span>
        <span><kbd>esc</kbd> {t('bezárás')}</span>
      {/snippet}
    </ListaValaszto>
  {:else}
    <div class="reszlet">
      <header class="fej">
        <h2>{fajlNev(valasztott.ut)}</h2>
        <p>{valasztott.ut} · {t('törölve: {ido}', { ido: elozmenyIdo(valasztott.datum) })}</p>
      </header>

      <textarea class="elonezet" readonly aria-label={t('A törlés előtti szöveg')} value={valtozat ? elonezet : elonezetHiba ? '' : t('Betöltés…')}></textarea>
      {#if elonezetHiba}<p class="hiba" role="alert"><Ikon ikon={TriangleAlert} meret={14} /> {elonezetHiba}</p>{/if}

      {#if valasztott.ut_van && !utkozes}
        <p class="figy" role="status"><Ikon ikon={TriangleAlert} meret={14} /> {t('Az eredeti helyen ({ut}) most már áll egy fájl, ezért új néven állítható vissza.', { ut: valasztott.ut })}</p>
      {/if}
      {#if hiba}<p class="hiba" role="alert"><Ikon ikon={TriangleAlert} meret={14} /> {hiba}</p>{/if}

      <div class="nev-sor">
        <label for="torolt-nev">{t('Új név')}</label>
        <input id="torolt-nev" type="text" bind:value={nev} bind:this={nevMezo} autocomplete="off" spellcheck="false" disabled={dolgozik} />
        <span class="kit">{kiterjesztes}</span>
      </div>

      <footer class="gombok">
        <button type="button" class="m-gomb semleges gomb" disabled={dolgozik} onclick={vissza}>{t('Vissza a listához')}</button>
        <button type="button" class="m-gomb semleges gomb" disabled={dolgozik || !nev.trim() || !valtozat} onclick={() => void visszahoz('uj')}>
          {t('Visszahozás új néven')}
        </button>
        <button
          type="button"
          class="m-gomb elsodleges gomb"
          disabled={dolgozik || !valtozat || valasztott.ut_van || utkozes}
          title={valasztott.ut_van ? t('Az eredeti helyen már áll egy fájl.') : undefined}
          onclick={() => void visszahoz('eredeti')}
        >
          <Ikon ikon={RotateCcw} meret={14} /> {t('Visszahozás az eredeti helyre')}
        </button>
      </footer>
    </div>
  {/if}
</Atfedes>

<style>
  .ikon {
    color: var(--szoveg-halvany);
  }

  .nev {
    flex: 0 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .ut {
    flex: 1 1 0;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: right;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .ido {
    flex: none;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    font-variant-numeric: tabular-nums;
  }

  .hiba-sor {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    color: var(--hiba);
  }

  kbd {
    color: var(--szoveg-masodlagos);
  }

  .reszlet {
    display: flex;
    flex-direction: column;
    gap: var(--t-3);
    flex: 1;
    min-height: 0;
    padding: var(--t-5);
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

  .elonezet {
    resize: none;
    flex: 1;
    min-height: 160px;
    margin: 0;
    padding: var(--t-3);
    overflow: auto;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    border: var(--keret-vastag) solid var(--keret);
    border-radius: var(--kerekites);
    background: var(--hatter);
    color: var(--szoveg);
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    user-select: text;
    -webkit-user-select: text;
  }

  .hiba,
  .figy {
    display: flex;
    align-items: flex-start;
    gap: var(--t-1);
    margin: 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .hiba {
    color: var(--hiba);
  }

  .figy {
    color: var(--figyelmeztetes);
  }

  .nev-sor {
    display: flex;
    align-items: center;
    gap: var(--t-2);
  }

  .nev-sor label {
    flex: none;
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-kicsi);
  }

  .nev-sor input {
    flex: 1;
    min-width: 0;
    height: var(--magassag-mezo);
    padding: 0 var(--t-3);
    border: var(--keret-vastag) solid var(--keret);
    border-radius: var(--kerekites);
    background: var(--hatter);
    color: var(--szoveg);
    user-select: text;
    -webkit-user-select: text;
  }

  .kit {
    color: var(--szoveg-halvany);
  }

  .gombok {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: var(--t-2);
  }

  .gomb {
    display: inline-flex;
    align-items: center;
    gap: var(--t-2);
  }
</style>
