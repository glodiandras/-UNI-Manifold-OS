// UX-audit kapu (F7): normál módban a felületen nincs fejlesztői szó. Három őr:
//   1. STATIKUS: minden `t()/tk()/tp()` kulcs angol szövege (a core hibakód-tartalékai nélkül) — ha fejlesztői szót tartalmaz, a
//      `ux-audit.json` kivétel-listájában kell állnia indokkal. Az indok fajtája: `dev-gated` (csak Developer módban látszik),
//      `product` (a szó itt a termék része, pl. egy fájlformátum vagy egy munkamód neve), `legacy` (átírandó szöveg; a lista CSAK
//      csökkenhet: `legacy_max`). Új fejlesztői szó kivétel nélkül nem kerülhet be; az elavult kivétel is bukik.
//   2. RENDERELT: a Settings minden normál szakasza, a Health oldal (minden panelje kinyitva) és a Privacy-szakaszok szövege, címkéje
//      és tooltipje fejlesztői szó nélkül jelenik meg; Developer módban ugyanott megjelenik a technikai nézet.
//   3. PARANCSOK: a „Fejlesztő” kategóriájú parancsok mind a Developer módhoz kötöttek (és normál módban nem érhetők el).
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import BeallitasokAblak from '../src/beallitasok/Beallitasok.svelte';
import { beallitasAblak, SZAKASZOK, szakaszLathato } from '../src/beallitasok/allapot.svelte';
import Egeszseg from '../src/egeszseg/Egeszseg.svelte';
import { adatvedelem } from '../src/lib/adatvedelem/allapot.svelte';
import { BeallitasokTar, beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { FEJLESZTOI_PARANCSOK, fejlesztoiParancs } from '../src/lib/beallitasok/fejleszto';
import { parancsEngedelyezett } from '../src/lib/beallitasok/modulok';
import { alapBeallitasok, type BeallitasokValasz } from '../src/lib/beallitasok/tipusok';
import { egeszsegApi } from '../src/lib/egeszseg/api';
import { EgeszsegTar } from '../src/lib/egeszseg/allapot.svelte';
import type { EgeszsegSor } from '../src/lib/egeszseg/tipusok';
import { nyelv, szotarFajlok, tk } from '../src/lib/i18n';
import { regiszter } from '../src/lib/parancsok/regiszter';
import { beallitasokTelepit } from '../src/beallitasok';
import { elemez, forrasFajlok, rovidUt } from './i18n-keresok';

const JSON_UT = `${(import.meta as unknown as { dirname: string }).dirname}/ux-audit.json`;
interface AuditJson { _leiras: string; legacy_max: number; kivetelek: Record<string, string> }
const audit = JSON.parse(readFileSync(JSON_UT, 'utf8')) as AuditJson;

/** Fejlesztői szó: ami egy hétköznapi felhasználónak nem szól. A „core” itt a belső szolgáltatás neve. */
const FEJLESZTOI = /\b(developer|debug\w*|selftest|self-test|stderr|stdout|traceback|json|api|endpoints?|pids?|git|sandbox\w*|worker|localhost|xcode|asan|ubsan|v2(\.\d)?|checkout|regex|websocket|http|cli|latency|benchmark|fingerprints?|core)\b/i;
const FEJLESZTOI_RENDERELT = /\b(developer|debug\w*|selftest|stderr|stdout|traceback|json|api|endpoints?|pids?|git|sandbox\w*|worker|localhost|asan|ubsan|v2(\.\d)?|checkout|regex|websocket|cli|latency|benchmark|fingerprints?|core)\b/i;

const EN = new Map<string, string>(Object.entries(szotarFajlok()).filter(([ut]) => ut.startsWith('./en/')).flatMap(([, sz]) => Object.entries(sz)));

describe('statikus: a szótár szövegei', () => {
  const talalatok = new Map<string, string>(); // kulcs → angol szöveg
  for (const [ut, szoveg] of Object.entries(forrasFajlok())) {
    if (ut.endsWith('.d.ts') || ut.includes('/lib/i18n/')) continue;
    for (const k of elemez(ut, szoveg).kulcsok) {
      if (k.kulcs.startsWith('hiba.')) continue; // a core hibakód-tartalékai: nem felületi szöveg, a hibapanel mutatja a kód szövegét
      const en = EN.get(k.kulcs) ?? k.kulcs;
      if (FEJLESZTOI.test(en)) talalatok.set(k.kulcs, en);
    }
  }

  it('minden fejlesztői szót tartalmazó szöveg a kivétel-listán áll, indokkal', () => {
    const uj = [...talalatok].filter(([k]) => !(k in audit.kivetelek)).map(([k, en]) => `"${k}" → "${en}"`);
    expect(uj, 'új fejlesztői szó a felületen: írd át a szöveget, vagy (indokkal) vedd fel a tests/ux-audit.json-ba').toEqual([]);
  });

  it('a kivétel-lista nem tartalmaz elavult tételt, és minden indok fajtája ismert', () => {
    const elavult = Object.keys(audit.kivetelek).filter((k) => !talalatok.has(k));
    expect(elavult, 'ezek a szövegek már nem fejlesztői szavasak (vagy eltűntek): vedd ki őket a tests/ux-audit.json-ból').toEqual([]);
    const rossz = Object.entries(audit.kivetelek).filter(([, indok]) => !/^(dev-gated|product|legacy): \S/.test(indok));
    expect(rossz).toEqual([]);
  });

  it('a „legacy” (átírandó) kivételek száma csak csökkenhet', () => {
    const n = Object.values(audit.kivetelek).filter((i) => i.startsWith('legacy:')).length;
    expect(n).toBeLessThanOrEqual(audit.legacy_max);
    if (n < audit.legacy_max) console.info(`ux-audit: a legacy_max ${audit.legacy_max} → ${n}-re csökkenthető`);
  });
});

describe('parancsok', () => {
  it('a „Fejlesztő” kategóriájú parancsok mind a Developer módhoz kötöttek', () => {
    const idk: string[] = [];
    for (const [ut, szoveg] of Object.entries(forrasFajlok())) {
      if (ut.endsWith('.d.ts')) continue;
      for (const m of szoveg.matchAll(/id:\s*'([\w.-]+)'[^}]*?kategoria:\s*tk\('Fejlesztő'\)/gs)) idk.push(`${rovidUt(ut)}: ${m[1]}`);
    }
    expect(idk.length).toBeGreaterThan(0);
    for (const sor of idk) expect(fejlesztoiParancs(sor.split(': ')[1]), sor).toBe(true);
  });

  it('a kötött parancs normál módban nem érhető el, Developer módban igen', () => {
    beallitasok.fogad(valasz(false));
    for (const id of [...FEJLESZTOI_PARANCSOK, 'fejleszto.valami']) expect(parancsEngedelyezett(id), id).toBe(false);
    expect(parancsEngedelyezett('hej.paletta')).toBe(true);
    beallitasok.fogad(valasz(true));
    for (const id of FEJLESZTOI_PARANCSOK) expect(parancsEngedelyezett(id), id).toBe(true);
    beallitasok.adat = null;
  });
});

// --- renderelt felület --------------------------------------------------------------------------------------------------------

const valasz = (fejleszto = false): BeallitasokValasz => {
  const ertek = alapBeallitasok();
  ertek.fejleszto.mod = fejleszto;
  return { verzio: 1, rev: 'r1', ertek, munkater: { id: 'synthetic', nev: 'Synthetic workspace', vault: '/synthetic/vault' }, setup_szukseges: false, ujrainditas: [] };
};
const sor = (kod: string, allapot: EgeszsegSor['allapot'], javitas: string | null = null): EgeszsegSor =>
  ({ kod, cim: kod, allapot, uzenet_kod: `${kod}.x`, param: {}, uzenet: 'Some English message.', javitas, reszletek: [{ kulcs: 'fajl', ertek: 'x' }, { kulcs: 'worker', ertek: 'idle' }, { kulcs: 'core_port', ertek: 1 }], nyers: 'RAW' });
const json = (d: unknown) => new Response(JSON.stringify(d), { status: 200, headers: { 'Content-Type': 'application/json' } });

/** Az elem fölött látszó szöveg + a hozzáférhető nevek (aria-label, title, placeholder, alt). */
function lathatoSzovegek(gyoker: ParentNode): string {
  const reszek = [(gyoker as HTMLElement).textContent ?? ''];
  gyoker.querySelectorAll<HTMLElement>('[aria-label],[title],[placeholder],[alt]').forEach((e) => {
    for (const a of ['aria-label', 'title', 'placeholder', 'alt']) { const v = e.getAttribute(a); if (v) reszek.push(v); }
  });
  return reszek.join('\n');
}
/** A termék része, nem fejlesztői szó: a Developer-mód kapcsoló maga (a Settings › About › Advanced information alatt). */
const MEGENGEDETT_RENDERELT = [/Developer mode/g];
const megtisztit = (s: string) => MEGENGEDETT_RENDERELT.reduce((acc, re) => acc.replace(re, ''), s);

beforeEach(() => {
  nyelv.beallit('en');
  adatvedelem.adat = null;
  vi.stubGlobal('fetch', async (url: string) => {
    const u = new URL(url, 'http://127.0.0.1/');
    if (u.pathname === '/api/adatvedelem') return json({
      verzio: 1, mikor: '2026-10-16T10:00:00',
      halozat: { offline: true, engedett: [{ kod: 'models', elerheto: true }, { kod: 'runtime_tools', elerheto: true }, { kod: 'video_links', elerheto: true }], tiltott: ['telemetry', 'background_sync', 'cloud_ai', 'update_ping'], utolso_letoltesek: [] },
      modellek: { telepitve: [], ut: '/m', bajt: 0, hiba: null },
      adat: ['workspace', 'snapshots', 'index', 'personal', 'models', 'backup', 'caches', 'logs'].map((kod) => ({ kod, ut: `/data/${kod}`, bajt: 10, van: true, torolheto: false })),
      memoria: { kapcsolo: true, tetelek: { mintak: 0, muveletek: 0, elutasitott: 0, hangolas: 0 }, osszes: 0 },
      tracker: { be: true, ut: '/p', bajt: 1, van: true, tarol: ['active_time', 'edit_counts', 'command_usage', 'latency'], nem_tarol: ['note_text'] },
      integraciok: [{ kod: 'calendar', be: true, elerheto: false, utolso: null }],
      engedelyek: { naptar: { kapcsolo: true, esemeny: null, emlekezteto: null }, ertesitesek: { kapcsolo: true } },
    });
    if (u.pathname === '/api/asszisztens/tanult') return json({ kapcsolo: true, mintak: [], muveletek: [], hangolas: [], elutasitott: [] });
    if (u.pathname === '/api/rendszer/epites') return json({ ok: true, mag: 'm', reszek: [{ resz: 'felulet', azonosito: 'abc', friss: true }] });
    if (u.pathname === '/api/egeszseg') return json({ verzio: 1, zold: true, osszesen: { ok: 1, info: 0, figyelem: 0, hiba: 0 }, ellenorzesek: [sor('index', 'ok')] });
    if (u.pathname.startsWith('/api/tracker')) return json({});
    return new Response(JSON.stringify({ hiba: 'nincs' }), { status: 404, headers: { 'Content-Type': 'application/json' } });
  });
});
afterEach(() => { cleanup(); beallitasok.adat = null; beallitasAblak.szakasz = 'altalanos'; vi.unstubAllGlobals(); vi.restoreAllMocks(); nyelv.beallit('hu'); });

describe('renderelt: Settings', () => {
  function nyit(fejleszto: boolean) {
    const tar = new BeallitasokTar();
    tar.fogad(valasz(fejleszto));
    beallitasok.fogad(valasz(fejleszto));
    render(BeallitasokAblak, { props: { tar, onbezar: vi.fn(), onsetup: vi.fn(), onrendszer: vi.fn() } });
  }

  it('normál módban egyik szakasz sem mutat fejlesztői szót (a Developer mód kapcsolója kivételével)', async () => {
    // a Hotkeys listája a regiszter minden parancsát felsorolná: a fejlesztői parancsok normál módban kimaradnak
    const le = [
      regiszter.regisztral({ id: 'szerkeszto.gepeles-meres', nev: tk('Fejlesztő: gépelési késleltetés mérése'), kategoria: tk('Fejlesztő'), futtat: () => {} }),
      regiszter.regisztral({ id: 'hej.proba-nyitas', nev: 'Open a file', futtat: () => {} }),
      beallitasokTelepit(regiszter),
    ];
    nyit(false);
    const lathato = SZAKASZOK.filter((s) => szakaszLathato(s.id, false));
    expect(lathato.length).toBeGreaterThan(20);
    for (const s of lathato) {
      await fireEvent.click(screen.getByRole('button', { name: EN.get(s.cim) ?? s.cim }));
      await waitFor(() => expect(screen.getByRole('heading', { level: 2 }).textContent).toBe(EN.get(s.cim) ?? s.cim));
      if (s.id === 'nevjegy') document.querySelectorAll('details').forEach((d) => (d.open = true));
      await new Promise((r) => setTimeout(r, 0));
      const szoveg = megtisztit(lathatoSzovegek(document.body));
      expect(szoveg.match(FEJLESZTOI_RENDERELT), `${s.id}: ${szoveg.match(FEJLESZTOI_RENDERELT)}`).toBeNull();
      if (s.id === 'billentyuk') expect(szoveg).toContain('Open a file');                 // a lista él, csak a fejlesztői sorok hiányoznak
    }
    le.forEach((f) => f());
  });

  it('Developer módban megjelenik a Developer csoport és a technikai nézet', async () => {
    nyit(true);
    expect(screen.getByText('Developer')).toBeTruthy();
    for (const s of SZAKASZOK.filter((x) => x.id.startsWith('fejleszto_'))) expect(screen.getByRole('button', { name: EN.get(s.cim) ?? s.cim })).toBeTruthy();
  });
});

describe('renderelt: Health', () => {
  const ellenorzesek = ['index', 'pillanatkep', 'zarak', 'lemezhely', 'modellek', 'munkater', 'folyamatok'].map((k, i) =>
    sor(k, (['hiba', 'figyelem', 'figyelem', 'info', 'ok', 'figyelem', 'ok'] as const)[i], ['index', 'pillanatkep', 'zarak', 'lemezhely'].includes(k) ? ({ index: 'index_ujraepit', pillanatkep: 'git_zar_takarit', zarak: 'zar_takarit', lemezhely: 'gyorsitotar_torles' } as Record<string, string>)[k] : null));

  async function megnyit(fejleszto: boolean) {
    beallitasok.fogad(valasz(fejleszto));
    vi.spyOn(egeszsegApi, 'betolt').mockResolvedValue({ verzio: 1, zold: false, osszesen: { ok: 2, info: 1, figyelem: 3, hiba: 1 }, ellenorzesek });
    vi.spyOn(egeszsegApi, 'diagnosztika').mockImplementation(async (kod) => ({ verzio: 1, ellenorzesek: ellenorzesek.filter((s) => s.kod === kod) }));
    const tar = new EgeszsegTar();
    render(Egeszseg, { props: { tar, onbezar: vi.fn() } });
    await waitFor(() => expect(tar.adat).not.toBeNull());
  }

  it('normál módban minden panel kinyitva sem mutat fejlesztői szót, nyers JSON-t vagy ismeretlen kulcsot', async () => {
    await megnyit(false);
    for (const mod of ['Diagnose', 'Fix', 'Learn more']) {
      for (const gomb of screen.getAllByRole('button', { name: mod })) { await fireEvent.click(gomb); await new Promise((r) => setTimeout(r, 0)); }
      const szoveg = lathatoSzovegek(document.body);
      expect(szoveg.match(FEJLESZTOI_RENDERELT), `${mod}: ${szoveg.match(FEJLESZTOI_RENDERELT)}`).toBeNull();
    }
    expect(document.querySelector('[data-nyers]')).toBeNull();
    expect(document.body.textContent).not.toContain('RAW');
  });

  it('Developer módban ugyanott megjelenik a nyers diagnosztika', async () => {
    await megnyit(true);
    await fireEvent.click(screen.getAllByRole('button', { name: 'Diagnose' })[0]);
    await waitFor(() => expect(document.querySelector('[data-nyers]')).toBeTruthy());
    expect(document.querySelector('[data-nyers]')!.textContent).toContain('RAW');
  });
});

describe('renderelt: Privacy', () => {
  it('a Privacy-szakaszok normál módban nem mutatnak fejlesztői szót', async () => {
    const tar = new BeallitasokTar();
    tar.fogad(valasz(false));
    beallitasok.fogad(valasz(false));
    render(BeallitasokAblak, { props: { tar, onbezar: vi.fn(), onsetup: vi.fn(), onrendszer: vi.fn() } });
    for (const id of ['halozat', 'telemetria', 'adatok', 'integraciok', 'engedelyek', 'memoria', 'asszisztens']) {
      const s = SZAKASZOK.find((x) => x.id === id)!;
      await fireEvent.click(screen.getByRole('button', { name: EN.get(s.cim) ?? s.cim }));
      await waitFor(() => expect(document.querySelector(`[data-adatvedelem="${id}"]`)).toBeTruthy());
      await new Promise((r) => setTimeout(r, 20));
      const szoveg = lathatoSzovegek(document.body);
      expect(szoveg.match(FEJLESZTOI_RENDERELT), `${id}: ${szoveg.match(FEJLESZTOI_RENDERELT)}`).toBeNull();
    }
  });
});
