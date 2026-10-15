// A link adatai a szintaxisfából és a média-horgonyok (C10): wikilink/embed részei, a megjelenített felirat, a
// méret-alias (`|300x200`), a `t=` (másodperc, `mm:ss`, `hh:mm:ss`) és a `page=` horgony.

import { describe, expect, it } from 'vitest';
import { linkFelirat, mediaHorgony, meretAliasbol, wikilinkAdat } from '../src/szerkeszto/linkek/adat';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';

function linkek(szoveg: string) {
  const ki: ReturnType<typeof wikilinkAdat>[] = [];
  obsidianElemzo.parse(szoveg).iterate({
    enter(n) {
      const a = wikilinkAdat(n.node, (x, y) => szoveg.slice(x, y));
      if (a) ki.push(a);
    },
  });
  return ki;
}

describe('wikilinkAdat', () => {
  it('a cél, a horgony és az alias', () => {
    const [a, b, c, d] = linkek('[[Jegyzet]] [[Jegyzet#Fejezet|szöveg]] ![[kép.png|300]] [[#Csak fejezet]]');
    expect(a).toMatchObject({ cel: 'Jegyzet', alcel: null, alias: null, beagyazas: false });
    expect(b).toMatchObject({ cel: 'Jegyzet', alcel: 'Fejezet', alias: 'szöveg' });
    expect(c).toMatchObject({ cel: 'kép.png', alias: '300', beagyazas: true });
    expect(d).toMatchObject({ cel: '', alcel: 'Csak fejezet' });
  });

  it('a szóközök a célból és a horgonyból lekerülnek; a blokk- és a média-horgony `#` nélkül', () => {
    const [a, b, c] = linkek('[[ Név ]] [[Jegyzet#^abc123]] [[x.pdf#page=3]]');
    expect(a!.cel).toBe('Név');
    expect(b!.alcel).toBe('^abc123');
    expect(c!.alcel).toBe('page=3');
  });

  it('a hely a forrásbeli', () => {
    const sz = 'x [[A]] y';
    const [a] = linkek(sz);
    expect(sz.slice(a!.from, a!.to)).toBe('[[A]]');
  });
});

describe('linkFelirat', () => {
  it('az alias, különben a cél › horgony', () => {
    expect(linkFelirat({ cel: 'A', alcel: 'B', alias: null, beagyazas: false, from: 0, to: 0 })).toBe('A › B');
    expect(linkFelirat({ cel: 'A', alcel: 'B', alias: 'szöveg', beagyazas: false, from: 0, to: 0 })).toBe('szöveg');
    expect(linkFelirat({ cel: '', alcel: 'B', alias: null, beagyazas: false, from: 0, to: 0 })).toBe('B');
  });
});

describe('média-horgony és méret', () => {
  it('t= másodpercben', () => {
    expect(mediaHorgony('t=243')).toEqual({ t: 243 });
    expect(mediaHorgony('t=12:40')).toEqual({ t: 760 });
    expect(mediaHorgony('t=1:02:03')).toEqual({ t: 3723 });
    expect(mediaHorgony('t=MP')).toEqual({});
  });

  it('page=', () => {
    expect(mediaHorgony('page=12')).toEqual({ page: 12 });
    expect(mediaHorgony('page=0')).toEqual({});
    expect(mediaHorgony('Fejezet')).toEqual({});
    expect(mediaHorgony(null)).toEqual({});
  });

  it('a méret-alias', () => {
    expect(meretAliasbol('300')).toEqual({ szelesseg: 300, magassag: undefined });
    expect(meretAliasbol('300x200')).toEqual({ szelesseg: 300, magassag: 200 });
    expect(meretAliasbol(' 40 x 20 ')).toEqual({ szelesseg: 40, magassag: 20 });
    expect(meretAliasbol('felirat')).toBeNull();
    expect(meretAliasbol(null)).toBeNull();
  });
});
