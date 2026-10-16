import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import Olvaso from '../src/szerkeszto/Olvaso.svelte';
import { Dokumentum } from '../src/szerkeszto/dokumentum/dokumentum.svelte';
import { szerkesztoTelepit } from '../src/szerkeszto';
import { szerkesztok, type SzerkesztoPeldany } from '../src/szerkeszto/szerkesztok.svelte';

const nezetek: EditorView[] = [];
const takaritok: (() => void)[] = [];
afterEach(() => { cleanup(); nezetek.splice(0).forEach(v => v.destroy()); takaritok.splice(0).forEach(f => f()); szerkesztok.aktiv = null; vi.restoreAllMocks(); });

it('az Olvasó keresősávja Enter/ShiftEnter/Escape és kis/nagybetű opcióval működik, szövegírás nélkül', async () => {
  const szoveg = 'One **match**\n\nAnother MATCH';
  const view = new EditorView({ state: EditorState.create({ doc: szoveg }) }); nezetek.push(view);
  const dok = new Dokumentum({ olvas: vi.fn(), ir: vi.fn() }, { ut: 'Host.md', tartalom: szoveg, hash: 'base', jel: '', mtime: 0 });
  const ir = vi.spyOn(dok, 'valtozott');
  const { component, container } = render(Olvaso, { props: { view, dok, ut: 'Host.md', valtozat: 0 } });
  await component.keresesNyit();
  const mezo = screen.getByRole('textbox', { name: 'Keresés az olvasóban' });
  expect(document.activeElement).toBe(mezo);
  await fireEvent.input(mezo, { target: { value: 'match' } });
  await vi.waitFor(() => expect(screen.getByRole('status').textContent).toBe('1/2 találat'));
  await fireEvent.keyDown(mezo, { key: 'Enter' }); expect(screen.getByRole('status').textContent).toBe('2/2 találat');
  await fireEvent.keyDown(mezo, { key: 'Enter', shiftKey: true }); expect(screen.getByRole('status').textContent).toBe('1/2 találat');
  await fireEvent.click(screen.getByRole('checkbox', { name: 'Kis- és nagybetű megkülönböztetése' }));
  expect(screen.getByRole('status').textContent).toBe('1/1 találat');
  await fireEvent.keyDown(mezo, { key: 'Escape' });
  expect(screen.queryByRole('search')).toBeNull(); expect(container.querySelector('mark.olvaso-talalat')).toBeNull();
  expect(view.state.doc.toString()).toBe(szoveg); expect(dok.szoveg.toString()).toBe(szoveg); expect(ir).not.toHaveBeenCalled();
  expect(document.activeElement).toBe(container.querySelector('article'));
});

it('a meglévő Cmd+F parancs olvasó módban a Readerbe irányít, szerkesztőmód-váltás nélkül', async () => {
  const keresesNyit = vi.fn(), modValt = vi.fn();
  szerkesztok.aktiv = { ut: 'Host.md', mod: () => 'olvaso', nezet: () => null, keresesNyit, olvasoValt: modValt } as unknown as SzerkesztoPeldany;
  const reg = new Regiszter(); takaritok.push(szerkesztoTelepit(reg, new CoreKapcsolat('ws://fixture')));
  expect(reg.elerheto(reg.kap('szerkeszto.kereses')!)).toBe(true);
  await reg.futtat('szerkeszto.kereses', 'billentyu');
  expect(keresesNyit).toHaveBeenCalledTimes(1); expect(modValt).not.toHaveBeenCalled();
});
