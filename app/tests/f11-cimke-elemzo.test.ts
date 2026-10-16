import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { Cimke, cimkeAdat, cimkeErtek, cimkeSzoveg } from '../src/szerkeszto/markdown/cimke';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';

function cimkeLista(doc: string): { cimke: string; from: number; to: number }[] {
  const ki: { cimke: string; from: number; to: number }[] = [];
  obsidianElemzo.parse(doc).iterate({ enter(n) {
    if (n.name === 'Hashtag') ki.push({ cimke: cimkeAdat(n.node, (a, b) => doc.slice(a, b))!, from: n.from, to: n.to });
  } });
  return ki;
}

describe('F11: címke-elemző core paritása', () => {
  const esetek = [
    '#tag #Tag/Sub #1 #12a #123/ #_ #- #/ #/// #a/// tail',
    '#é #e\u0301cole #中文 #हिन्दी #𝕏 #😀 #ab😀tail',
    '#١٢ #１２ #١a #² #Ⅳ #¼ #１２/² #123-456',
    'word#bad (#bad) [#bad] ##bad \\#bad \t#good\n#next\u0085#nel\u001c#fs\ufeff#bom',
    '#slash/path// #/leading #double//middle #under_score #hy-phen',
  ];

  it('a tényleges Python _CIMKE + Nd/non-slash feltétel és a Lezer ugyanazokat a címkéket látja', () => {
    const script = 'import json,re,sys\nsys.path.insert(0,"..")\nfrom core.index.elemzo import _CIMKE\nprint(json.dumps([[c for m in _CIMKE.finditer(txt) if (c:=m.group(1).rstrip("/")) and re.search(r"[^\\d/]",c)] for txt in json.loads(sys.argv[1])],ensure_ascii=False))';
    const python = process.env.MOS_PYTHON || join((import.meta as unknown as { dirname: string }).dirname, '../../var/venv/bin/python');
    const elvart = JSON.parse(execFileSync(python, ['-B', '-c', script, JSON.stringify(esetek)], { encoding: 'utf8' }));
    expect(esetek.map((s) => cimkeLista(s).map((c) => c.cimke))).toEqual(elvart);
    expect(esetek.map((s) => cimkeLista(s).map((c) => s.slice(c.from, c.to)))).toEqual(elvart.map((s: string[]) => s.map((c) => '#' + c)));
  });

  it('a csomópontok külön jelet és címkét tartalmaznak; az utolsó / közönséges szöveg marad', () => {
    expect(Cimke.defineNodes).toHaveLength(3);
    const doc = 'Text #Ékezet/ág/// tail';
    const fa = obsidianElemzo.parse(doc);
    const c = fa.topNode.getChild('Paragraph')!.getChild('Hashtag')!;
    expect(cimkeAdat(c, (a, b) => doc.slice(a, b))).toBe('Ékezet/ág');
    expect(c.getChild('HashtagMark')!.to - c.getChild('HashtagMark')!.from).toBe(1);
    expect(cimkeAdat(c.getChild('HashtagLabel')!, (a, b) => doc.slice(a, b))).toBe('Ékezet/ág');
    expect(doc.slice(c.to)).toBe('/// tail');
  });

  it('védett kód, YAML, matek, megjegyzés és linkcél nem tartalmaz beágyazott Hashtag csomópontot', () => {
    const doc = '---\ntitle: "#yaml"\n---\n\n```md\n#code\n```\n\n    #indented\n\n` #inline` $x #math$ $$x #display$$\n\n$$\n#blockmath\n$$\n\n%% #comment %%\n\n%%\n#blockcomment\n%%\n\n[[Note #wiki]] ![[Note #embed]]\n\n[label](<https://example.com/ #destination>)\n\n#visible';
    expect(cimkeLista(doc).map((c) => c.cimke)).toEqual(['visible']);
  });

  it('kézzel beírt érték validálása elutasítja a régi hibás tageket; érvényes címke alakja megmarad', () => {
    for (const [nyers, elvart] of [[' #Topic/Sub/// ', 'Topic/Sub'], ['#_', '_'], ['#²', '²'], ['#١٢', null], ['#1/', null], ['#has space', null], ['#a\u0301', null], ['##bad', null], ['#a.b', null], ['\ufeff#tag', null]] as const) expect(cimkeErtek(nyers), nyers).toBe(elvart);
    expect(cimkeSzoveg('#Topic/Sub')).toBe('Topic/Sub');
    expect(cimkeSzoveg('#Topic/')).toBeNull();
    expect(cimkeAdat({ name: 'URL', from: 0, to: 4 }, () => '#tag')).toBeNull();
  });
});
