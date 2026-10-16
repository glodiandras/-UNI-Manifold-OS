<!--
  A gráf vezérlőpanelje (C13): szűrők (lekérdezés, mellékletek, árvák, nyilak), színcsoportok (az Obsidian graph.json-jából
  indul, szerkeszthető), erők (csúszkák). A módosítások a `Felulet.graf` felülírásokba kerülnek (tartósak); ami nincs
  felülírva, a graph.json értékét kapja. A graph.json-ba a 2.0 nem ír vissza.
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import { Plus, RotateCcw, X } from '../lib/ikon/ikonok';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { EROK_KULCSOK, EROK_TARTOMANY, MAX_LEKERDEZES, MAX_SZINCSOPORT, type ErokKulcs, type GrafEffektiv, type GrafJson } from '../lib/graf/beallitasok';
  import type { GrafAdat, SzuroEredmeny } from '../lib/graf/modell';
  import { kornyezet } from '../lib/kornyezet';

  let {
    eff,
    adat,
    szuro,
    szinTamogatott,
    json,
  }: { eff: GrafEffektiv; adat: GrafAdat; szuro: SzuroEredmeny; szinTamogatott: boolean[]; json: GrafJson | null } = $props();
  const { felulet } = kornyezet();

  const felulirt = $derived(Object.keys(felulet.graf).length > 0);

  function beallit(valtozas: Partial<typeof felulet.graf>) {
    felulet.graf = { ...felulet.graf, ...valtozas };
  }

  function erokBeallit(kulcs: ErokKulcs, ertek: number) {
    beallit({ erok: { ...(felulet.graf.erok ?? {}), [kulcs]: ertek } });
  }

  function csoportModosit(i: number, valtozas: Partial<{ lekerdezes: string; szin: string }>) {
    const lista = eff.szincsoportok.map((c, j) => (j === i ? { ...c, ...valtozas } : { ...c }));
    beallit({ szincsoportok: lista });
  }

  function csoportTorol(i: number) {
    beallit({ szincsoportok: eff.szincsoportok.filter((_, j) => j !== i).map((c) => ({ ...c })) });
  }

  function csoportUj() {
    if (eff.szincsoportok.length >= MAX_SZINCSOPORT) return;
    beallit({ szincsoportok: [...eff.szincsoportok.map((c) => ({ ...c })), { lekerdezes: '', szin: '#c23a52' }] });
  }

  function visszaallit() {
    felulet.graf = {};
  }

  const forras = $derived(
    eff.szincsoportForras === 'graph.json' ? t('Az Obsidian graph.json-ból; a módosítás saját listát indít.') : eff.szincsoportForras === 'sajat' ? t('Saját lista.') : json?.van ? t('A graph.json-ban nincs színcsoport.') : t('Nincs graph.json; a színek a fájltípust követik.'),
  );
</script>

<aside class="vezerlo gorgeto" aria-label={t('Gráf beállításai')}>
  <section aria-labelledby="gv-szuro">
    <h3 id="gv-szuro">{t('Szűrők')}</h3>
    <label class="mezo-cimke" for="gv-lek">{t('Lekérdezés')}</label>
    <input
      id="gv-lek"
      class="mezo"
      type="text"
      spellcheck="false"
      autocomplete="off"
      maxlength={MAX_LEKERDEZES}
      placeholder={t('path:mappa  tag:#címke  [kulcs:érték]')}
      aria-describedby="gv-lek-sugo"
      value={eff.lekerdezes}
      oninput={(e) => beallit({ lekerdezes: e.currentTarget.value })}
    />
    <p id="gv-lek-sugo" class="sugo">
      {t('A fájlnévben vagy útban keres;')} <code>path:</code>, <code>file:</code>, <code>tag:#a</code>, <code>{t('[kulcs:érték]')}</code>, <code>OR</code>, <code>-</code>, {t('zárójel.')}
    </p>
    {#if szuro.nemTamogatott}
      <p class="figy" role="status">{t('A(z) „{elem}” elem a gráfban nem támogatott, ezért a lekérdezés nem szűr.', { elem: szuro.nemTamogatott })}</p>
    {/if}
    <label class="kapcsolo"><input type="checkbox" checked={eff.mellekletek} onchange={(e) => beallit({ mellekletek: e.currentTarget.checked })} />{t('Mellékletek (kép, PDF, média)')}</label>
    <label class="kapcsolo"><input type="checkbox" checked={eff.arvak} onchange={(e) => beallit({ arvak: e.currentTarget.checked })} />{t('Árva csúcsok (kapcsolat nélkül)')}</label>
    <label class="kapcsolo"><input type="checkbox" checked={eff.nyilak} onchange={(e) => beallit({ nyilak: e.currentTarget.checked })} />{t('Nyilak az élek irányával')}</label>
    <p class="sugo">{t('{db} / {n} csúcs látszik.', { db: szuro.csucsDb, n: adat.n })}</p>
  </section>

  <section aria-labelledby="gv-szin">
    <h3 id="gv-szin">{t('Színcsoportok')}</h3>
    <p class="sugo">{forras} {t('Az első illeszkedő csoport színez.')}</p>
    <ul class="csoportok" role="list">
      {#each eff.szincsoportok as c, i (i)}
        <li class="csoport">
          <input class="szin" type="color" aria-label={t('A(z) {n}. csoport színe', { n: i + 1 })} value={c.szin} onchange={(e) => csoportModosit(i, { szin: e.currentTarget.value })} />
          <input
            class="mezo"
            type="text"
            spellcheck="false"
            autocomplete="off"
            aria-label={t('A(z) {n}. csoport lekérdezése', { n: i + 1 })}
            aria-invalid={!szinTamogatott[i]}
            value={c.lekerdezes}
            onchange={(e) => csoportModosit(i, { lekerdezes: e.currentTarget.value })}
          />
          <button type="button" class="ikon" aria-label={t('A(z) {n}. csoport törlése', { n: i + 1 })} title={t('Csoport törlése')} onclick={() => csoportTorol(i)}><Ikon ikon={X} meret={14} /></button>
          {#if !szinTamogatott[i]}<p class="figy sor">{t('Nem támogatott lekérdezés: nem színez.')}</p>{/if}
        </li>
      {/each}
    </ul>
    <button type="button" class="m-gomb semleges gomb" disabled={eff.szincsoportok.length >= MAX_SZINCSOPORT} onclick={csoportUj}><Ikon ikon={Plus} meret={14} />{t('Új csoport')}</button>
  </section>

  <section aria-labelledby="gv-erok">
    <h3 id="gv-erok">{t('Erők')}</h3>
    {#each EROK_KULCSOK as k (k)}
      {@const ta = EROK_TARTOMANY[k]}
      <div class="csuszka">
        <label for={`gv-erok-${k}`}>{ta.nev}</label>
        <output for={`gv-erok-${k}`}>{eff.erok[k].toFixed(2)}</output>
        <input id={`gv-erok-${k}`} type="range" min={ta.min} max={ta.max} step={ta.lepes} value={eff.erok[k]} oninput={(e) => erokBeallit(k, Number(e.currentTarget.value))} />
      </div>
    {/each}
  </section>

  <button type="button" class="m-gomb semleges gomb" disabled={!felulirt} onclick={visszaallit}>
    <Ikon ikon={RotateCcw} meret={14} />{json?.van ? t('Visszaállítás a graph.json értékeire') : t('Alapértékek')}
  </button>
</aside>

<style>
  .vezerlo {
    position: absolute;
    top: calc(var(--t-2) + 28px + var(--t-2));
    right: var(--t-2);
    bottom: calc(var(--t-5) + var(--t-2));
    z-index: 1;
    display: flex;
    flex-direction: column;
    gap: var(--t-4);
    width: 288px;
    max-width: calc(100% - var(--t-4));
    padding: var(--t-3);
    border: 1px solid var(--keret-eros);
    border-radius: var(--kerekites-nagy);
    background: var(--hatter-emelt);
    color: var(--szoveg-masodlagos);
  }

  section {
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
  }

  h3 {
    margin: 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-weight: var(--suly-kozepes);
    color: var(--szoveg);
  }

  .mezo-cimke {
    font-size: var(--betu-kicsi);
    color: var(--szoveg-halvany);
  }

  .mezo {
    width: 100%;
    height: var(--magassag-sor);
    padding: 0 var(--t-2);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: var(--hatter);
    color: var(--szoveg);
  }

  .mezo:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: 0;
  }

  .mezo[aria-invalid='true'] {
    border-color: var(--hiba);
  }

  .sugo {
    margin: 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
  }

  .figy {
    margin: 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--figyelmeztetes);
  }

  .figy.sor {
    grid-column: 1 / -1;
  }

  code {
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
  }

  .kapcsolo {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    min-height: var(--magassag-sor);
    color: var(--szoveg-masodlagos);
  }

  .csoportok {
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
    margin: 0;
  }

  .csoport {
    display: grid;
    grid-template-columns: 28px 1fr 20px;
    align-items: center;
    gap: var(--t-1);
  }

  .szin {
    width: var(--magassag-gomb);
    height: var(--magassag-sor);
    padding: 2px;
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: var(--hatter);
  }

  .ikon {
    display: grid;
    place-items: center;
    width: var(--magassag-gomb-kicsi);
    height: var(--magassag-gomb-kicsi);
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-halvany);
  }

  .ikon:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .gomb {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    align-self: flex-start;
    padding: 0 var(--t-2);
  }

  .csuszka {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 2px var(--t-2);
  }

  .csuszka label {
    color: var(--szoveg-masodlagos);
  }

  .csuszka output {
    font-variant-numeric: tabular-nums;
    color: var(--szoveg-halvany);
  }

  .csuszka input {
    grid-column: 1 / -1;
    width: 100%;
    accent-color: var(--akcent);
  }
</style>
