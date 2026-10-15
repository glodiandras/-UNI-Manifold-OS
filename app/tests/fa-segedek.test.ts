// A tesztek szintaxisfa-segédje (T009): a teljes fát adja, vagy egyértelműen hibázik.
import { EditorState } from '@codemirror/state';
import { describe, expect, it } from 'vitest';
import { markdownNyelv } from '../src/szerkeszto/beallitas';
import { teljesFa } from './notion-segedek';

describe('teljesFa', () => {
  it('a kész szintaxisfát adja: a táblázat megvan', () => {
    const s = EditorState.create({ doc: '| a | b |\n|---|---|\n| 1 | 2 |\n', extensions: [markdownNyelv()] });
    const nevek = new Set<string>();
    teljesFa(s).iterate({ enter: (n) => void nevek.add(n.name) });
    expect(nevek.has('Table')).toBe(true);
  });

  it('ha az elemzés nem készül el az időn belül, egyértelmű hibát dob, nem a részleges fát adja', () => {
    const sor = '| a | b | c |\n';
    const doc = sor + '|---|---|---|\n' + '| 1 | 2 | 3 |\n'.repeat(40_000);
    const s = EditorState.create({ doc, extensions: [markdownNyelv()] });
    expect(() => teljesFa(s, 0)).toThrow(/nem készült el/);
  }, 30_000);
});
