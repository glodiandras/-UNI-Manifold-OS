<!--
  A ⌘R eredménye a `.cpp` fül alján (C36a-UI): fejléc (fordítás, `n/m teszt átment`, mód, idő), a fordító
  diagnosztikája (kattintásra a sorra ugrik), tesztenként egy sor (állapot, idő, memória); a nem átment teszt
  kinyitva a bemenettel, a várt és a kapott kimenettel (sorszintű diff a motor `diff.sorok`-jából), a futási vagy
  sanitizer-jelentéssel. Futás közben Megszakítás (a fülben Esc is). Csak tokenből rajzol (25. döntés).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { locale, t, tk, tp } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { Check, ChevronDown, ChevronRight, CircleAlert, Square, X } from '../lib/ikon/ikonok';
  import { ALLAPOT_NEV, type Diagnosztika, type DiffSor, type Futas, type TesztEredmeny, type TesztLeiras } from './futas.svelte';

  let {
    futas,
    leirasok = [],
    onugras,
    onmegszakit,
  }: {
    futas: Futas;
    leirasok?: TesztLeiras[];
    onugras: (sor: number, oszlop?: number) => void;
    onmegszakit: () => void;
  } = $props();

  let nyitva = $state(true);
  let kinyitott = $state<Record<number, boolean>>({});
  let futasId = untrack(() => futas.futas);
  $effect(() => {
    if (futas.futas !== futasId) {
      futasId = futas.futas;
      kinyitott = {};
      nyitva = true;
    }
  });


  const fut = $derived(futas.allapot === 'fut');
  const fordit = $derived(futas.fordit);
  const atmentDb = $derived(futas.kesz?.atment_db ?? futas.tesztek.filter((te) => te.allapot === 'atment').length);
  const osszDb = $derived(futas.kesz?.tesztek_db ?? futas.tesztek_db);
  const elsoHibas = $derived(futas.tesztek.find((te) => te.allapot !== 'atment')?.sorszam ?? null);
  const diagnosztika = $derived((fordit?.diagnosztika ?? []).filter((d) => d.szint !== 'remark'));
  const leiras = $derived(new Map(leirasok.map((l) => [l.sorszam, l])));

  function mp(ms: number | undefined | null): string {
    if (ms === undefined || ms === null) return '';
    return ms < 1000 ? t('{n} ms', { n: Math.round(ms) }) : t('{n} s', { n: (ms / 1000).toLocaleString(locale(), { maximumFractionDigits: 1 }) });
  }

  function mb(x: number | null | undefined): string {
    return x ? t('{n} MB', { n: x.toLocaleString(locale(), { maximumFractionDigits: 1 }) }) : '';
  }

  const fazis = $derived.by(() => {
    if (futas.allapot === 'megszakitva') return t('Megszakítva');
    if (futas.allapot === 'hiba') return t('Az ellenőrzés nem futott le');
    if (!fut) return '';
    if (futas.megszakitasKerve) return t('Megszakítás…');
    if (!fordit) return t('Fordítás…');
    return t('Teszt {i}/{n}…', { i: Math.min(futas.tesztek.length + 1, Math.max(osszDb, 1)), n: osszDb });
  });

  function kinyit(te: TesztEredmeny) {
    kinyitott = { ...kinyitott, [te.sorszam]: !nyitottE(te) };
  }

  function nyitottE(te: TesztEredmeny): boolean {
    return kinyitott[te.sorszam] ?? (te.sorszam === elsoHibas && te.allapot !== 'atment');
  }

  function diagHely(d: Diagnosztika): string {
    return d.sor ? `${d.sor}${d.oszlop ? ':' + d.oszlop : ''}` : '';
  }

  const SZINT: Record<string, string> = { error: tk('hiba'), 'fatal error': tk('hiba'), warning: tk('figyelmeztetés'), note: tk('megjegyzés') };

  function diffJel(s: DiffSor): string {
    return s.tipus === 'torolt' ? t('várt') : s.tipus === 'beszurt' ? t('kapott') : '';
  }
</script>

<section class="kod-eredmeny" aria-label={t('Az ellenőrzés eredménye')} data-futas={futas.futas}>
  <header class="fejlec">
    <button type="button" class="osszecsuk" aria-expanded={nyitva} onclick={() => (nyitva = !nyitva)} title={nyitva ? t('Összecsukás') : t('Kinyitás')}>
      <Ikon ikon={nyitva ? ChevronDown : ChevronRight} meret={14} />
    </button>
    <div class="osszegzes" role="status" aria-live="polite">
      {#if fordit}
        <span class="jel" class:jo={fordit.ok} class:rossz={!fordit.ok}>
          <Ikon ikon={fordit.ok ? Check : X} meret={14} />
          {fordit.ok ? t('Fordítás kész') : t('Fordítás sikertelen')}{fordit.ms ? ` · ${mp(fordit.ms)}` : ''}
        </span>
        {#if fordit.figyelmeztetes_db > 0}
          <span class="jel figy">{tp('{n} figyelmeztetés', fordit.figyelmeztetes_db)}</span>
        {/if}
      {/if}
      {#if osszDb > 0 && (fordit?.ok || futas.tesztek.length)}
        <span class="jel" class:jo={!fut && atmentDb === osszDb} class:rossz={!fut && atmentDb < osszDb}>
          {t('{atment}/{ossz} teszt átment', { atment: atmentDb, ossz: osszDb })}
        </span>
      {:else if !fut && fordit?.ok && osszDb === 0}
        <span class="jel halvany">{t('Nincs teszt: csak a fordítás futott')}</span>
      {/if}
      {#if futas.mod === 'hibakereso'}<span class="jel halvany">{t('hibakereső mód')}</span>{/if}
      {#if fazis}<span class="jel halvany">{fazis}</span>{/if}
      {#if futas.kesz && !fut}<span class="jel halvany">{mp(futas.kesz.ms)}</span>{/if}
    </div>
    {#if fut}
      <button type="button" class="m-gomb semleges gomb" onclick={onmegszakit} disabled={futas.megszakitasKerve} title={t('Megszakítás (Esc)')}>
        <Ikon ikon={Square} meret={14} /> {t('Megszakítás')}
      </button>
    {/if}
  </header>

  {#if nyitva}
    <div class="test">
      {#if futas.hiba}
        <p class="uzenet rossz" role="alert">{futas.hiba.uzenet}</p>
      {/if}

      {#if fordit && !fordit.ok && fordit.uzenet}
        <p class="uzenet rossz">{fordit.uzenet}</p>
      {/if}
      {#if diagnosztika.length}
        <ul class="diagnosztika" aria-label={t('A fordító üzenetei')}>
          {#each diagnosztika as d, i (i)}
            <li class:hiba-sor={d.szint !== 'warning' && d.szint !== 'note'} class:figy-sor={d.szint === 'warning'}>
              {#if d.sajat && d.sor}
                <button type="button" class="diag-gomb" onclick={() => onugras(d.sor!, d.oszlop ?? undefined)}>
                  <span class="hely">{diagHely(d)}</span>
                  <span class="szint">{SZINT[d.szint] ? t(SZINT[d.szint]) : d.szint}</span>
                  <span class="szoveg">{d.uzenet}</span>
                </button>
              {:else}
                <span class="diag-gomb">
                  <span class="hely">{d.fajl ?? ''}{d.sor ? ':' + diagHely(d) : ''}</span>
                  <span class="szint">{SZINT[d.szint] ? t(SZINT[d.szint]) : d.szint}</span>
                  <span class="szoveg">{d.uzenet}</span>
                </span>
              {/if}
              {#if d.kodreszlet?.length}
                <pre class="reszlet">{d.kodreszlet.join('\n')}</pre>
              {/if}
            </li>
          {/each}
        </ul>
        {#if fordit?.levagva}<p class="halvany kicsi">{t('A fordító további üzenetei levágva.')}</p>{/if}
      {:else if fordit && !fordit.ok && fordit.kivonat}
        <pre class="kimenet">{fordit.kivonat}</pre>
      {/if}

      {#if futas.tesztek.length}
        <ul class="tesztek" aria-label={t('Tesztek')}>
          {#each futas.tesztek as te (te.sorszam)}
            {@const l = leiras.get(te.sorszam)}
            <li class="teszt" class:atment={te.allapot === 'atment'}>
              <button type="button" class="teszt-sor" aria-expanded={nyitottE(te)} onclick={() => kinyit(te)}>
                <span class="allapot-ikon" class:jo={te.allapot === 'atment'} class:rossz={te.allapot !== 'atment'}>
                  <Ikon ikon={te.allapot === 'atment' ? Check : te.allapot === 'hibas_teszt' ? CircleAlert : X} meret={14} />
                </span>
                <span class="teszt-nev">{te.sorszam}. {te.cim ?? l?.cim ?? t('teszt')}</span>
                <span class="teszt-allapot">{ALLAPOT_NEV[te.allapot] ? t(ALLAPOT_NEV[te.allapot]) : te.allapot}</span>
                <span class="meres">{mp(te.ido_ms)}</span>
                <span class="meres">{mb(te.csucs_mb)}</span>
              </button>
              {#if nyitottE(te)}
                <div class="reszletek">
                  {#if te.allapot !== 'atment' && (te.uzenet || te.hiba)}
                    <p class="uzenet">{te.hiba ?? te.uzenet}</p>
                  {/if}
                  {#if te.diff?.elteres?.ok}
                    <p class="halvany kicsi">
                      {t('Első eltérés:')} {te.diff.elteres.sor ? t('{n}. sor', { n: te.diff.elteres.sor }) : ''}{te.diff.elteres.oszlop
                        ? ', ' + t('{n}. oszlop', { n: te.diff.elteres.oszlop })
                        : ''}{te.diff.elteres.token ? ', ' + t('{n}. szó', { n: te.diff.elteres.token }) : ''} — {te.diff.elteres.ok}{te.diff.mod && te.diff.mod !== 'alap'
                        ? ' ' + t('(összevetés: {mod})', { mod: te.diff.mod })
                        : ''}
                    </p>
                  {/if}
                  {#if l && l.bemenet}
                    <div class="blokk"><span class="blokk-cim">{t('Bemenet')}</span><pre class="kimenet">{l.bemenet}</pre></div>
                  {/if}
                  {#if te.diff && te.diff.sorok.length}
                    <div class="blokk">
                      <span class="blokk-cim">{t('Várt és kapott kimenet')}</span>
                      <div class="diff" role="table" aria-label={t('A várt és a kapott kimenet eltérése')}>
                        {#each te.diff.sorok as s, i (i)}
                          {#if s.tipus === 'kihagyva'}
                            <div class="diff-sor kihagyva" role="row">{s.db === undefined ? t('… egyező sorok …') : tp('… {n} egyező sor …', s.db)}</div>
                          {:else if s.tipus === 'csere'}
                            <div class="diff-sor torolt" role="row"><span class="dj">{t('várt')}</span><span class="ds">{s.vart_sor}</span><code>{s.vart}</code></div>
                            <div class="diff-sor beszurt" role="row"><span class="dj">{t('kapott')}</span><span class="ds">{s.kapott_sor}</span><code>{s.kapott}</code></div>
                          {:else}
                            <div class="diff-sor {s.tipus}" role="row">
                              <span class="dj">{diffJel(s)}</span><span class="ds">{s.vart_sor ?? s.kapott_sor}</span><code>{s.vart ?? s.kapott}</code>
                            </div>
                          {/if}
                        {/each}
                        {#if te.diff.levagva}<div class="diff-sor kihagyva" role="row">{t('… a diff levágva …')}</div>{/if}
                      </div>
                    </div>
                  {:else if l && te.allapot !== 'atment'}
                    <div class="blokk"><span class="blokk-cim">{t('Várt kimenet')}</span><pre class="kimenet">{l.kimenet}</pre></div>
                  {/if}
                  {#if te.allapot !== 'atment' && te.stdout_kivonat && !te.diff?.sorok.length}
                    <div class="blokk"><span class="blokk-cim">{t('Kapott kimenet (kivonat)')}</span><pre class="kimenet">{te.stdout_kivonat}</pre></div>
                  {/if}
                  {#if te.jelentes}
                    <p class="uzenet">
                      {te.jelentes.leiras}{#if te.jelentes.fuggveny}{` · ${te.jelentes.fuggveny}`}{/if}
                      {#if te.jelentes.sajat && te.jelentes.sor}
                        <button type="button" class="link-gomb" onclick={() => onugras(te.jelentes!.sor!, te.jelentes!.oszlop ?? undefined)}>
                          {t('{n}. sor', { n: te.jelentes.sor })}
                        </button>
                      {/if}
                    </p>
                  {/if}
                  {#if te.stderr_kivonat && te.allapot !== 'atment'}
                    <div class="blokk"><span class="blokk-cim">{t('Hibakimenet (kivonat)')}</span><pre class="kimenet">{te.stderr_kivonat}</pre></div>
                  {/if}
                  {#if te.jel}
                    <p class="halvany kicsi">{t('Jel: {jel}', { jel: te.jel })}</p>
                  {:else if te.kilepes !== null && te.kilepes !== 0}
                    <p class="halvany kicsi">{t('Kilépési kód: {kod}', { kod: te.kilepes })}</p>
                  {/if}
                </div>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</section>

<style>
  .kod-eredmeny {
    flex: none;
    display: flex;
    flex-direction: column;
    max-height: 45%;
    min-height: 0;
    border-top: 1px solid var(--keret);
    background: var(--hatter-emelt);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg);
  }

  .fejlec {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--t-2);
    min-height: var(--magassag-fejlec);
    padding: 0 var(--t-3) 0 var(--t-2);
  }

  .osszecsuk,
  .gomb,
  .teszt-sor,
  .diag-gomb,
  .link-gomb {
    font: inherit;
    color: inherit;
    background: none;
    border: none;
    cursor: pointer;
  }

  .osszecsuk {
    display: grid;
    place-items: center;
    width: var(--magassag-gomb);
    height: var(--magassag-gomb);
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-halvany);
  }

  .osszecsuk:hover,
  .gomb:hover,
  .teszt-sor:hover,
  button.diag-gomb:hover {
    background: var(--hatter-hover);
  }

  .osszecsuk:focus-visible,
  .gomb:focus-visible,
  .teszt-sor:focus-visible,
  .diag-gomb:focus-visible,
  .link-gomb:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav-befele);
  }

  .osszegzes {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--t-2);
  }

  .jel {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    padding: 2px var(--t-2);
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-masodlagos);
  }

  .jel.jo {
    color: var(--siker);
    background: var(--siker-hatter);
  }

  .jel.rossz {
    color: var(--hiba);
    background: var(--hiba-hatter);
  }

  .jel.figy {
    color: var(--figyelmeztetes);
    background: var(--figyelmeztetes-hatter);
  }

  .halvany {
    color: var(--szoveg-halvany);
  }

  .kicsi {
    font-size: var(--betu-kicsi);
  }

  .gomb {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    padding: 0 var(--t-2);
  }

  .test {
    min-height: 0;
    overflow: auto;
    padding: 0 var(--t-3) var(--t-3);
  }

  .uzenet {
    margin: var(--t-1) 0;
  }

  .uzenet.rossz {
    color: var(--hiba);
  }

  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .diagnosztika {
    margin-bottom: var(--t-2);
  }

  .diag-gomb {
    display: flex;
    gap: var(--t-2);
    width: 100%;
    text-align: left;
    padding: 2px var(--t-2);
    border-radius: var(--kerekites-kicsi);
  }

  .hely {
    flex: none;
    min-width: 4ch;
    font-family: var(--betu-mono);
    color: var(--szoveg-halvany);
  }

  .szint {
    flex: none;
    color: var(--szoveg-masodlagos);
  }

  .hiba-sor .szint {
    color: var(--hiba);
  }

  .figy-sor .szint {
    color: var(--figyelmeztetes);
  }

  .szoveg {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .teszt-sor {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto auto auto;
    align-items: center;
    gap: var(--t-2);
    width: 100%;
    min-height: var(--magassag-lista-sor);
    padding: 0 var(--t-2);
    text-align: left;
    border-radius: var(--kerekites-kicsi);
  }

  .allapot-ikon {
    display: inline-flex;
  }

  .allapot-ikon.jo {
    color: var(--siker);
  }

  .allapot-ikon.rossz {
    color: var(--hiba);
  }

  .teszt-nev {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .teszt-allapot {
    color: var(--szoveg-masodlagos);
  }

  .meres {
    min-width: 7ch;
    text-align: right;
    font-variant-numeric: tabular-nums;
    color: var(--szoveg-halvany);
  }

  .reszletek {
    padding: var(--t-1) var(--t-2) var(--t-2) var(--t-6);
  }

  .blokk {
    margin-top: var(--t-2);
  }

  .blokk-cim {
    display: block;
    font-size: var(--betu-kicsi);
    color: var(--szoveg-halvany);
    margin-bottom: 2px;
  }

  pre.kimenet,
  pre.reszlet {
    margin: 0;
    padding: var(--t-1) var(--t-2);
    max-height: 12em;
    overflow: auto;
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
    background: var(--hatter-kod);
    border-radius: var(--kerekites-kicsi);
    white-space: pre;
  }

  pre.reszlet {
    margin: 2px 0 var(--t-1) calc(4ch + var(--t-2) * 2);
  }

  .diff {
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
    background: var(--hatter-kod);
    border-radius: var(--kerekites-kicsi);
    max-height: 16em;
    overflow: auto;
    padding: 2px 0;
  }

  .diff-sor {
    display: grid;
    grid-template-columns: 7ch 5ch minmax(0, 1fr);
    padding: 0 var(--t-2);
    white-space: pre;
  }

  .diff-sor code {
    font: inherit;
    overflow-wrap: normal;
  }

  .dj,
  .ds {
    color: var(--szoveg-halvany);
  }

  .ds {
    text-align: right;
    padding-right: var(--t-2);
  }

  .diff-sor.torolt {
    background: var(--hiba-hatter);
  }

  .diff-sor.beszurt {
    background: var(--siker-hatter);
  }

  .diff-sor.kihagyva {
    display: block;
    color: var(--szoveg-halvany);
    font-style: italic;
  }

  .link-gomb {
    padding: 0;
    color: var(--akcent-szoveg);
    text-decoration: underline;
  }
</style>
