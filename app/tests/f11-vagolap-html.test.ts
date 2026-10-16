import { describe, expect, it } from 'vitest';
import { htmlMarkdown } from '../src/szerkeszto/vagolap-html';
import { szerkezet } from './notion-segedek';

describe('F11: rich text vágólap → Markdown', () => {
  it('fejezet, bekezdés, inline formázás és sortörés közönséges Markdown marad', () => {
    expect(htmlMarkdown('<h4>Heading</h4><p>A <strong>bold</strong>, <em>italic</em>, <s>old</s> and <code>source_*</code>.<br>Next</p>'))
      .toBe('#### Heading\n\nA **bold**, *italic*, ~~old~~ and `source_*`.  \nNext');
  });

  it('kódkerítés nem törhető ki; a kód üres sorai, belső Markdownja és nyelve megmarad', () => {
    const ki = htmlMarkdown('<p>Before</p><pre><code class="language-js">first\n\n\n\n```\nlast\n</code></pre><p>After</p>')!;
    expect(ki).toBe('Before\n\n````js\nfirst\n\n\n\n```\nlast\n````\n\nAfter');
    expect(szerkezet(ki).db.FencedCode).toBe(1);
  });

  it('inline backtick tartalma biztonságos hosszúságú jelölőt kap', () => {
    expect(htmlMarkdown('<p><code>a`b</code> and <code>`edge`</code></p>')).toBe('``a`b`` and `` `edge` ``');
  });

  it('listák, sorszámozás, listába ágyazott lista és feladatállapot', () => {
    expect(htmlMarkdown('<ul><li>Alpha<ul><li>Child</li></ul></li><li>Beta</li></ul><ol start="3"><li>Third</li><li value="8">Eighth</li></ol>'))
      .toBe('- Alpha\n  - Child\n- Beta\n\n3. Third\n8. Eighth');
    expect(htmlMarkdown('<ul><li><input type="checkbox" checked>Done</li><li><input type="checkbox">Todo</li></ul>'))
      .toBe('- [x] Done\n- [ ] Todo');
  });

  it('idézetben a belső lista és üres sor is megmarad', () => {
    expect(htmlMarkdown('<blockquote><p>Quote</p><p>Second</p><ul><li>Item</li></ul></blockquote>'))
      .toBe('> Quote\n>\n> Second\n>\n> - Item');
  });

  it('kódblokk üres sorai idézetben és listában is a tárolón belül maradnak', () => {
    expect(htmlMarkdown('<blockquote><pre>a\n\n\nb</pre></blockquote>')).toBe('> ```\n> a\n> \n> \n> b\n> ```');
    expect(htmlMarkdown('<ul><li><pre>a\n\n\nb</pre></li></ul>')).toBe('- ```\n  a\n  \n  \n  b\n  ```');
  });

  it('linkek célja biztonságos és escape-elt; kép hivatkozás marad hálózati letöltés nélkül', () => {
    const elotte = document.body.innerHTML;
    expect(htmlMarkdown('<p><a href="https://example.com/a (b)">Link</a> <img src="https://example.com/image.png" alt="Image"></p>'))
      .toBe('[Link](https://example.com/a%20%28b%29) [Image](https://example.com/image.png)');
    expect(document.body.innerHTML).toBe(elotte);
    expect(htmlMarkdown('<a href="https://example.com"><img src="https://example.com/image.png" alt="Image"></a>'))
      .toBe('[Image](https://example.com)');
  });

  it.each(['javascript:alert(1)', 'java&#x73;cript:alert(1)', 'data:text/html,test', 'file:///private/example', 'vbscript:run', 'custom:run', '&#10;javascript:alert(1)'])('veszélyes URL nem kerül a Markdownba: %s', (href) => {
    expect(htmlMarkdown(`<p><a href="${href}">Text</a></p>`)).toBe('Text');
  });

  it('script, stílus, event handler és rejtett elem nem kerül a kimenetbe vagy az élő DOM-ba', () => {
    const ki = htmlMarkdown('<script>bad()</script><style>body{color:red}</style><p onclick="bad()">Safe <span hidden>secret</span><iframe src="https://example.com">bad</iframe></p>');
    expect(ki).toBe('Safe');
    expect(document.querySelector('script,iframe,[onclick]')).toBeNull();
  });

  it('táblázat igazítással, pipe és sortörés; hiányzó cellák kiegészítve', () => {
    expect(htmlMarkdown('<table><thead><tr><th align="left">Name</th><th style="text-align:right">Value</th></tr></thead><tbody><tr><td>A | B<br>C</td><td><strong>5</strong></td></tr><tr><td>Last</td></tr></tbody></table>'))
      .toBe('| Name | Value |\n| :--- | ---: |\n| A \\| B C | **5** |\n| Last |  |');
  });

  it('összevont cellák szövege egyszer marad meg; a rács nem írja felül a következő sort', () => {
    expect(htmlMarkdown('<table><tr><th rowspan="2">A</th><th>B</th></tr><tr><td>C</td></tr><tr><td colspan="2">D</td></tr></table>'))
      .toBe('| A | B |\n| --- | --- |\n|  | C |\n| D |  |');
  });

  it('a szövegként másolt Markdown-jelölők nem lesznek új listák, fejlécek vagy láthatatlan %% kommentek', () => {
    const ki = htmlMarkdown('<p># Heading</p><p>- Item</p><p>1. Item</p><p><span>2.</span> Item</p><p>%%literal%% and [brackets] and *stars*</p>')!;
    expect(ki).toBe('\\# Heading\n\n\\- Item\n\n1\\. Item\n\n2\\. Item\n\n\\%\\%literal\\%\\% and \\[brackets\\] and \\*stars\\*');
    const sz = szerkezet(ki);
    expect(sz.db.BulletList ?? 0).toBe(0);
    expect(sz.db.OrderedList ?? 0).toBe(0);
    expect(sz.db.ObsidianComment ?? 0).toBe(0);
    expect(sz.db.ATXHeading1 ?? 0).toBe(0);
  });

  it('méret, mélység, csomópontszám és táblázat-robbanás esetén text/plain fallbackot kér', () => {
    expect(htmlMarkdown('<p>' + 'x'.repeat(2 * 1024 * 1024) + '</p>')).toBeNull();
    expect(htmlMarkdown('<ul><li>'.repeat(80) + 'deep' + '</li></ul>'.repeat(80))).toBeNull();
    expect(htmlMarkdown('<span>x</span>'.repeat(11000))).toBeNull();
    expect(htmlMarkdown('<table><tr>' + '<td colspan="100" rowspan="100">A</td>'.repeat(5) + '</tr></table>')).toBeNull();
    expect(htmlMarkdown('')).toBeNull();
    expect(htmlMarkdown('<script>bad()</script>')).toBeNull();
  });
});
