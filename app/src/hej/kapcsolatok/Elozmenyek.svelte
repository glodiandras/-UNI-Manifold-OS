<!--
  Jegyzet-előzmények (C11b): a jegyzet pillanatképei, a legújabb elöl — melyik kör, milyen forrás (szerkesztés, átnevezés,
  gépi lánc, kézi változás, visszaállítás). Kattintásra a változat diffje nyílik, onnan állítható vissza egy verzióra
  (revert-commitként: a mostani szöveg az előzményekben marad, és a visszaállítás is visszavonható). A napló a core-é
  (`/api/vault/elozmeny`); csak md-jegyzetnek van, és csak a megnyitott (nyitott) szakasznál töltődik.
-->
<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { ApiHiba, kerdez } from '../../lib/core/api';
  import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
  import { kornyezet } from '../../lib/kornyezet';
  import { elozmenyApi, elozmenyIdo, type ElozmenyBejegyzes } from '../../lib/vault/elozmeny';
  import { szerkesztok } from '../../szerkeszto/szerkesztok.svelte';
  import ElozmenyDiff from './ElozmenyDiff.svelte';

  let { ut, nyitva }: { ut: string | null; nyitva: boolean } = $props();
  const { kapcsolat } = kornyezet();

  let lista = $state.raw<ElozmenyBejegyzes[]>([]);
  let hiba = $state<string | null>(null);
  let betolt = $state(false);
  let megnyitott = $state.raw<ElozmenyBejegyzes | null>(null);
  let sorszam = 0;
  let idozito: ReturnType<typeof setTimeout> | null = null;

  const md = $derived(!!ut && ut.toLowerCase().endsWith('.md'));

  async function tolt() {
    const en = ++sorszam;
    if (!ut || !md || !nyitva) {
      lista = [];
      hiba = null;
      return;
    }
    betolt = true;
    try {
      const d = await elozmenyApi.naplo(ut);
      if (en !== sorszam) return;
      lista = d.bejegyzesek;
      hiba = null;
    } catch (e) {
      if (en !== sorszam) return;
      lista = [];
      hiba = e instanceof ApiHiba && e.statusz === 404 ? 'Az előzmények nem érhetők el (nincs pillanatkép-tároló).' : e instanceof Error ? e.message : String(e);
    } finally {
      if (en === sorszam) betolt = false;
    }
  }

  $effect(() => {
    void ut;
    void nyitva;
    untrack(() => void tolt());
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
          cim: 'A visszaállítás előbb döntést kér',
          szoveg: dok.csakOlvashato ?? 'A jegyzet ütközésben van vagy eltűnt: előbb azt kell lezárni.',
        });
        return false;
      }
      const m = await dok.ment({ pillanat: true });
      if (!m.ok) {
        ertesitesek.ertesit({ szint: 'hiba', cim: 'A jegyzet mentése nem sikerült', szoveg: 'A visszaállítás előtt a mostani szöveget el kell menteni.' });
        return false;
      }
    }
    try {
      const r = await elozmenyApi.visszaallit(ut, b.sha);
      await dok?.kulsoValtozas();
      ertesitesek.ertesit({
        szint: 'siker',
        cim: 'Visszaállítva',
        szoveg: `${ut} — ${elozmenyIdo(b.datum)} állapota`,
        muvelet: { nev: 'Visszavonás', futtat: () => void visszavon(r.sha) },
        idotartam: 15000,
      });
      void tolt();
      return true;
    } catch (e) {
      ertesitesek.ertesit({
        szint: 'hiba',
        cim: 'A visszaállítás nem sikerült',
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
      ertesitesek.ertesit({ szint: 'siker', cim: 'A visszaállítás visszavonva', szoveg: ut, idotartam: 4000 });
      void tolt();
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: 'A visszavonás nem sikerült', szoveg: e instanceof ApiHiba ? e.message : String(e), idotartam: 0 });
    }
  }
</script>

{#if !ut}
  <p class="ures">Nincs megnyitott jegyzet.</p>
{:else if !md}
  <p class="ures">Az előzmények a Markdown-jegyzetekhez állnak rendelkezésre.</p>
{:else if hiba}
  <p class="hiba" role="alert">{hiba}</p>
{:else if !lista.length}
  <p class="ures" role="status">{betolt ? 'Betöltés…' : 'Még nincs pillanatkép erről a jegyzetről.'}</p>
{:else}
  <ul class="lista" aria-label="A jegyzet pillanatképei">
    {#each lista as b, i (b.sha)}
      <li>
        <button type="button" class="elem" title={b.targy} onclick={() => (megnyitott = b)}>
          <span class="cimke">{b.cimke}{#if i === 0}<span class="jelenlegi">jelenlegi</span>{/if}</span>
          <span class="ido">{elozmenyIdo(b.datum)}{b.kor ? ` · ${b.kor}` : ''}</span>
        </button>
      </li>
    {/each}
  </ul>
{/if}

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
