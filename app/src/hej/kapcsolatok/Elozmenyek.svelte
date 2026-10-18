<!--
  Jegyzet-előzmények (C11b): a jegyzet pillanatképei, a legújabb elöl — melyik kör, milyen forrás (szerkesztés, átnevezés,
  gépi lánc, kézi változás, visszaállítás). Kattintásra a változat diffje nyílik, onnan állítható vissza egy verzióra
  (revert-commitként: a mostani szöveg az előzményekben marad, és a visszaállítás is visszavonható). A napló a core-é
  (`/api/vault/elozmeny`): `.md`, `.canvas` és `.base` fájlnak van (13-palette-06), lapokban töltődik (a lapméret a core
  `[elozmeny]` konfigurációja; „Régebbi változatok” a végén — 13-palette-05), és csak a megnyitott szakasznál töltődik. Törölt
  jegyzet visszahozása: „Törölt jegyzet visszahozása…” (13-palette-04, `ToroltVisszahozas.svelte`).
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import { onMount, tick, untrack } from 'svelte';
  import { ApiHiba, kerdez } from '../../lib/core/api';
  import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
  import Ikon from '../../lib/ikon/Ikon.svelte';
  import { TriangleAlert } from '../../lib/ikon/ikonok';
  import { kornyezet } from '../../lib/kornyezet';
  import { elozmenyApi, elozmenyesUt, elozmenyIdo, type ElozmenyBejegyzes } from '../../lib/vault/elozmeny';
  import { szerkesztok } from '../../szerkeszto/szerkesztok.svelte';
  import ElozmenyDiff from './ElozmenyDiff.svelte';

  let { ut, nyitva }: { ut: string | null; nyitva: boolean } = $props();
  const { kapcsolat, felulet } = kornyezet();

  let lista = $state.raw<ElozmenyBejegyzes[]>([]);
  let hiba = $state<string | null>(null);
  let betolt = $state(false);
  let megnyitott = $state.raw<ElozmenyBejegyzes | null>(null);
  let tovabb = $state(false);
  let kovetkezo = $state<string | null>(null);
  let tobbBetolt = $state(false);
  let tobbHiba = $state<string | null>(null);
  let listaElem: HTMLUListElement | undefined = $state();
  let sorszam = 0;
  let idozito: ReturnType<typeof setTimeout> | null = null;

  const md = $derived(elozmenyesUt(ut));

  /** Az első lap (újratöltésnél a már betöltött régebbi lapok megmaradnak: az új bejegyzések elé kerülnek). */
  async function tolt() {
    const en = ++sorszam;
    if (!ut || !md || !nyitva) {
      lista = [];
      hiba = null;
      tovabb = false;
      kovetkezo = null;
      return;
    }
    betolt = true;
    try {
      const d = await elozmenyApi.naplo(ut);
      if (en !== sorszam) return;
      const utolso = d.bejegyzesek.at(-1);
      const j = utolso ? lista.findIndex((b) => b.sha === utolso.sha) : -1;
      if (j >= 0 && j + 1 < lista.length) {
        lista = [...d.bejegyzesek, ...lista.slice(j + 1)];        // a betöltött régebbi lapok megmaradnak
      } else {
        lista = d.bejegyzesek;
        tovabb = d.tovabb;
        kovetkezo = d.kovetkezo;
      }
      tobbHiba = null;
      hiba = null;
    } catch (e) {
      if (en !== sorszam) return;
      lista = [];
      tovabb = false;
      kovetkezo = null;
      hiba = e instanceof ApiHiba && e.statusz === 404 ? t('Az előzmények nem érhetők el (nincs pillanatkép-tároló).') : e instanceof Error ? e.message : String(e);
    } finally {
      if (en === sorszam) betolt = false;
    }
  }

  /** A következő (régebbi) lap a lista végére; a fókusz az első új bejegyzésre kerül, a görgetés nem ugrik. */
  async function tobbetTolt() {
    if (!ut || !kovetkezo || tobbBetolt) return;
    const en = sorszam;
    const kurzor = kovetkezo;
    tobbBetolt = true;
    tobbHiba = null;
    try {
      const d = await elozmenyApi.naplo(ut, kurzor);
      if (en !== sorszam) return;
      const elso = d.bejegyzesek[0]?.sha;
      lista = [...lista, ...d.bejegyzesek.filter((b) => !lista.some((x) => x.sha === b.sha))];
      tovabb = d.tovabb;
      kovetkezo = d.kovetkezo;
      await tick();
      if (elso) listaElem?.querySelector<HTMLElement>(`[data-sha="${elso}"]`)?.focus({ preventScroll: true });
    } catch (e) {
      if (en === sorszam) tobbHiba = e instanceof Error ? e.message : String(e);
    } finally {
      tobbBetolt = false;
    }
  }

  // másik jegyzetre váltva a lista újraindul (a régebbi lapok az előző jegyzeté voltak)
  let utoljaraBetoltott: string | null = null;
  $effect(() => {
    void ut;
    void nyitva;
    untrack(() => {
      if (ut !== utoljaraBetoltott) {
        lista = [];
        tovabb = false;
        kovetkezo = null;
        tobbHiba = null;
        utoljaraBetoltott = ut;
      }
      void tolt();
    });
  });

  // új pillanatkép, visszavonás, átnevezés vagy külső változás: a napló újratölt (lassítva)
  onMount(() => {
    const utemez = () => {
      if (idozito) clearTimeout(idozito);
      idozito = setTimeout(() => void tolt(), 600);
    };
    const le = [
      kapcsolat.figyel('vault_iras', (e) => {
        if (e.ut === ut && e.pillanat) utemez();
      }),
      kapcsolat.figyel('visszavonas', utemez),
      kapcsolat.figyel('vault_atnevezes', utemez),
      kapcsolat.figyel('vault_valtozas', (e) => {
        if (e.kulso && (!ut || ((e.kulso as string[]) ?? []).includes(ut))) utemez();
      }),
    ];
    return () => {
      le.forEach((f) => f());
      if (idozito) clearTimeout(idozito);
    };
  });

  // ------------------------------------------------------------------ visszaállítás

  /** A nyitott dokumentum mentése (pillanatképpel) a visszaállítás előtt, a visszaállítás, és a dokumentum újratöltése. */
  async function visszaallit(b: ElozmenyBejegyzes): Promise<boolean> {
    if (!ut) return false;
    const dok = szerkesztok.dokumentumok.kap(ut);
    if (dok) {
      if (dok.allapot === 'utkozes' || dok.allapot === 'eltunt' || dok.csakOlvashato) {
        ertesitesek.ertesit({
          szint: 'figyelmeztetes',
          cim: t('A visszaállítás előbb döntést kér'),
          szoveg: dok.csakOlvashato ?? t('A jegyzet ütközésben van vagy eltűnt: előbb azt kell lezárni.'),
        });
        return false;
      }
      const m = await dok.ment({ pillanat: true });
      if (!m.ok) {
        ertesitesek.ertesit({ szint: 'hiba', cim: t('A jegyzet mentése nem sikerült'), szoveg: t('A visszaállítás előtt a mostani szöveget el kell menteni.') });
        return false;
      }
    }
    try {
      const r = await elozmenyApi.visszaallit(ut, b.sha);
      await dok?.kulsoValtozas();
      ertesitesek.ertesit({
        szint: 'siker',
        cim: t('Visszaállítva'),
        szoveg: t('{ut} — {ido} állapota', { ut, ido: elozmenyIdo(b.datum) }),
        muvelet: { nev: t('Visszavonás'), futtat: () => void visszavon(r.sha) },
        idotartam: 15000,
      });
      void tolt();
      return true;
    } catch (e) {
      ertesitesek.ertesit({
        szint: 'hiba',
        cim: t('A visszaállítás nem sikerült'),
        szoveg: e instanceof ApiHiba ? e.message : String(e),
        idotartam: 0,
      });
      return false;
    }
  }

  async function visszavon(sha: string) {
    if (!ut) return;
    const dok = szerkesztok.dokumentumok.kap(ut);
    if (dok) await dok.ment({ pillanat: true });
    try {
      await kerdez('/api/pillanat/vault/visszavonas', { metodus: 'POST', torzs: { sha }, idokorlat: 60000 });
      await dok?.kulsoValtozas();
      ertesitesek.ertesit({ szint: 'siker', cim: t('A visszaállítás visszavonva'), szoveg: ut, idotartam: 4000 });
      void tolt();
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: t('A visszavonás nem sikerült'), szoveg: e instanceof ApiHiba ? e.message : String(e), idotartam: 0 });
    }
  }
</script>

{#if !ut}
  <p class="ures">{t('Nincs megnyitott jegyzet.')}</p>
{:else if !md}
  <p class="ures">{t('Az előzmények jegyzetekhez, canvasokhoz és adatbázis-nézetekhez állnak rendelkezésre.')}</p>
{:else if hiba}
  <p class="hiba" role="alert">{hiba}</p>
{:else if !lista.length}
  <p class="ures" role="status">{betolt ? t('Betöltés…') : t('Még nincs pillanatkép erről a jegyzetről.')}</p>
{:else}
  <ul class="lista" aria-label={t('A jegyzet pillanatképei')} bind:this={listaElem}>
    {#each lista as b, i (b.sha)}
      <li>
        <button type="button" class="elem" title={b.targy} data-sha={b.sha} onclick={() => (megnyitott = b)}>
          <span class="cimke">{b.cimke}{#if i === 0}<span class="jelenlegi">{t('jelenlegi')}</span>{/if}</span>
          <span class="ido">{elozmenyIdo(b.datum)}{b.kor ? ` · ${b.kor}` : ''}</span>
        </button>
      </li>
    {/each}
  </ul>
  {#if tobbHiba}
    <p class="hiba" role="alert"><Ikon ikon={TriangleAlert} meret={14} /> {t('A régebbi változatok nem töltődtek be: {hiba}', { hiba: tobbHiba })}</p>
  {/if}
  {#if tovabb}
    <button type="button" class="tovabb" disabled={tobbBetolt} aria-busy={tobbBetolt} onclick={() => void tobbetTolt()}>
      {tobbBetolt ? t('Betöltés…') : t('Régebbi változatok')}
    </button>
  {:else}
    <p class="ures" role="status">{t('Ez az összes pillanatkép ({n}).', { n: lista.length })}</p>
  {/if}
{/if}

<button type="button" class="tovabb" onclick={() => (felulet.atfedes = 'torolt')}>{t('Törölt jegyzet visszahozása…')}</button>

{#if megnyitott && ut}
  <ElozmenyDiff
    {ut}
    bejegyzes={megnyitott}
    legujabb={lista[0]?.sha === megnyitott.sha}
    onbezar={() => (megnyitott = null)}
    onvisszaallit={visszaallit}
  />
{/if}

<style>
  .ures,
  .hiba {
    margin: 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
  }

  .hiba {
    color: var(--hiba);
  }

  .lista {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .elem {
    display: flex;
    flex-direction: column;
    gap: 1px;
    width: 100%;
    padding: var(--t-1) var(--t-2);
    border-radius: var(--kerekites-kicsi);
    text-align: left;
  }

  .elem:hover {
    background: var(--hatter-hover);
  }

  .elem:focus-visible {
    outline-offset: var(--fokusz-tav-befele);
  }

  .cimke {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    color: var(--szoveg);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
  }

  .tovabb {
    display: block;
    width: 100%;
    margin-top: var(--t-1);
    padding: var(--t-1) var(--t-2);
    border-radius: var(--kerekites-kicsi);
    text-align: left;
    color: var(--akcent-szoveg);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .tovabb:hover:not(:disabled) {
    background: var(--hatter-hover);
  }

  .tovabb:disabled {
    color: var(--szoveg-halvany);
  }

  .tovabb:focus-visible {
    outline-offset: var(--fokusz-tav-befele);
  }

  .hiba {
    display: flex;
    align-items: flex-start;
    gap: var(--t-1);
  }

  .jelenlegi {
    padding: 0 var(--t-1);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter-kijelolt);
    color: var(--akcent-szoveg);
    font-size: var(--betu-kicsi);
  }

  .ido {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-variant-numeric: tabular-nums;
  }
</style>
