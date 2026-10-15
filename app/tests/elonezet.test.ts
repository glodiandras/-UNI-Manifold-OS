// A lebegő link-előnézet (C10): csak ⌘ (vagy ⌃) nyomva jelenik meg, ~300 ms késleltetéssel; a ⌘ utólagos lenyomására is;
// a ⌘ elengedése a még meg nem jelentet visszavonja; az egér elhagyása 250 ms után zár, a popoverre lépve nyitva
// marad; Esc azonnal zár; a tartalom ugyanaz a renderelő, mint a beágyazásé (core-kérés a forrással).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { linkek } from '../src/lib/vault/linkek.svelte';
import { ELONEZET_KESLELTETES, ELONEZET_ZARAS, domCel, elonezet, elonezetKapcsol } from '../src/szerkeszto/linkek/elonezet';

let kerelmek: string[];
let le: () => void;
let link: HTMLElement;
let gyoker: HTMLElement;

beforeEach(() => {
  vi.useFakeTimers();
  linkek.mediaToken = 'tok';
  kerelmek = [];
  vi.stubGlobal('fetch', async (url: string) => {
    kerelmek.push(url);
    return new Response(JSON.stringify({ tipus: 'jegyzet', ut: 'Cél.md', szoveg: '# Cél\n\nTartalom.\n' }), { status: 200 });
  });
  gyoker = document.createElement('div');
  gyoker.innerHTML = '<p>szöveg <span class="wikilink" data-cel="Cél" data-forras="Fő.md">cél</span> <span class="kulso">más</span></p>';
  document.body.appendChild(gyoker);
  link = gyoker.querySelector('.wikilink')!;
  le = elonezetKapcsol(gyoker, (t) => domCel(t));
});

afterEach(() => {
  le();
  elonezet.zar();
  gyoker.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const mozog = (el: Element, meta: boolean) => el.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, metaKey: meta }));
const popover = () => document.querySelector<HTMLElement>('.link-elonezet');

describe('a lebegő előnézet', () => {
  it('⌘ nélkül nem jelenik meg', () => {
    mozog(link, false);
    vi.advanceTimersByTime(ELONEZET_KESLELTETES * 3);
    expect(popover()).toBeNull();
  });

  it('⌘ nyomva: a késleltetés után megjelenik, a tartalom a core-ból, a forrással', async () => {
    mozog(link, true);
    vi.advanceTimersByTime(ELONEZET_KESLELTETES - 10);
    expect(popover()).toBeNull();
    vi.advanceTimersByTime(20);
    expect(popover()).not.toBeNull();
    expect(popover()!.getAttribute('aria-label')).toBe('Link előnézete');
    await vi.waitFor(() => expect(popover()!.querySelector('h1')?.textContent).toBe('Cél'));
    expect(kerelmek[0]).toContain('forras=F%C5%91.md');
    expect(kerelmek[0]).toContain('cel=C%C3%A9l');
    expect(popover()!.querySelector('.beagyazas-cim')).toBeNull(); // kompakt: fejléc nélkül
  });

  it('a ⌘ utólagos lenyomása is megjeleníti; elengedése a még meg nem jelentet visszavonja', () => {
    mozog(link, false);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Meta' }));
    window.dispatchEvent(new KeyboardEvent('keyup', { key: 'Meta' }));
    vi.advanceTimersByTime(ELONEZET_KESLELTETES * 2);
    expect(popover()).toBeNull();
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Meta' }));
    vi.advanceTimersByTime(ELONEZET_KESLELTETES + 5);
    expect(popover()).not.toBeNull();
  });

  it('az egér elhagyása késleltetve zár; a popoverre lépve nyitva marad', () => {
    mozog(link, true);
    vi.advanceTimersByTime(ELONEZET_KESLELTETES + 5);
    const p = popover()!;
    mozog(gyoker.querySelector('.kulso')!, true);
    p.dispatchEvent(new MouseEvent('mouseenter'));
    vi.advanceTimersByTime(ELONEZET_ZARAS * 3);
    expect(popover()).toBe(p);
    p.dispatchEvent(new MouseEvent('mouseleave'));
    vi.advanceTimersByTime(ELONEZET_ZARAS + 5);
    expect(popover()).toBeNull();
  });

  it('Esc azonnal zár; a gyökér elhagyása is zár', () => {
    mozog(link, true);
    vi.advanceTimersByTime(ELONEZET_KESLELTETES + 5);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(popover()).toBeNull();
    mozog(link, true);
    vi.advanceTimersByTime(ELONEZET_KESLELTETES + 5);
    expect(popover()).not.toBeNull();
    gyoker.dispatchEvent(new MouseEvent('mouseleave'));
    vi.advanceTimersByTime(ELONEZET_ZARAS + 5);
    expect(popover()).toBeNull();
  });

  it('egyszerre egy popover van; a billentyűzetes `mutat` azonnal nyit', () => {
    const cel = domCel(link)!;
    elonezet.mutat(cel);
    elonezet.mutat(cel);
    expect(document.querySelectorAll('.link-elonezet')).toHaveLength(1);
    expect(elonezet.nyitva).toBe(true);
    elonezet.zar();
    expect(elonezet.nyitva).toBe(false);
  });

  it('a nem link elem fölött nincs cél', () => {
    expect(domCel(gyoker.querySelector('.kulso'))).toBeNull();
    expect(domCel(link)).toMatchObject({ forras: 'Fő.md', link: { cel: 'Cél', alcel: null } });
  });
});
