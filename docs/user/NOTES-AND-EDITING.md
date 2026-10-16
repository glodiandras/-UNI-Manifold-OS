# Notes & editing

Manifold's editor works on plain Markdown. You can see your notes formatted while you write, switch to the raw text, or read them undisturbed.

## Three ways to view a note

| Mode | What it is | Switch with |
|---|---|---|
| **Live Preview** | Formatted text while you edit. The Markdown marks show only on the line you are working on. | ⇧⌘E toggles Live Preview and Source |
| **Source mode** | The raw Markdown text. | ⇧⌘E |
| **Reading view** | Formatted and read-only. | ⌘E toggles Reading and editing |

The mode new notes open in is set in **Settings › Editor › Default editing mode**.

## Saving

Manifold saves as you type. ⌘S saves immediately. If another program changes the same file while you have unsaved edits, Manifold does not overwrite the other version. It keeps yours on screen, unsaved, so you can compare and decide.

To go back to an earlier version, open the note's **History** in the right sidebar, or run **Note history** from the command palette. The command **Snapshot of the note** records a version on demand.

## Formatting

| Action | How |
|---|---|
| Bold, italic, highlight | ⌘B, ⌘I, ⇧⌘H |
| Strikethrough, inline code | Command palette: *Strikethrough*, *Code* |
| Set or edit a link | ⌘K |
| Toggle a task | ⌘↩ on a line such as `- [ ] Call back` |
| Headings, lists, quotes | Type the Markdown, or use the palette commands *Set as heading 1–6*, *Toggle bullet list*, *Toggle numbered list*, *Toggle task list*, *Toggle quote*, *Clear formatting* |

Typing `*`, `_`, `~`, `=` or `$` around a selection wraps it in a pair, and brackets and quotes close themselves.

### The insert menu

Type `/` at the start of a line or after a space to open the insert menu. It offers headings, lists, tasks, quotes, callouts, collapsible callouts, code blocks, math, tables, dividers, function graphs, Mermaid diagrams, templates, embeds and Bases views. Keep typing to filter, press ↩ or Tab to insert, and Esc to close. You can turn the menu off in **Settings › Editor**.

### Moving blocks

The command palette also has block commands: *Block: move up*, *Block: move down*, *Block: duplicate*, *Block: delete* and *Block: copy link*. They work on the paragraph, list item or other block at the cursor.

## Folding

Headings and list items with children can be folded, in Live Preview, in Source mode and in Reading view. Use the command palette:

- *Toggle fold on the current line*
- *Fold all headings and lists* and *Unfold all headings and lists*
- *Fold more* and *Fold less*, which fold one level at a time

Folding is a view setting for the tab. It is never written into your note.

## Comments

Text between `%%` marks is a comment. It shows in the editor but is hidden in Reading view:

```
This is visible. %% This is a private remark. %% This is visible again.
```

A comment can span several paragraphs. An unterminated comment runs to the end of the note.

## Callouts, math, diagrams

- **Callouts**: start a quote with `> [!note]`. Other types such as tip or warning are in the insert menu. Add `-` after the type, as in `> [!note]- Title`, to make the callout collapsible.
- **Math**: write formulas between `$` marks, or in a block between lines of `$$`.
- **Diagrams**: a code block with the language `mermaid` is drawn as a diagram.
- **Function graphs**: a code block with the language `plot` draws a graph. Insert one from the menu to get a working example.
- **Tables** can be inserted from the insert menu and edited in place.

## Embeds

An embed shows another file inside the note. Write `!` before a link:

| Write | Shows |
|---|---|
| `![[Meeting notes]]` | the whole note |
| `![[Meeting notes#Decisions]]` | one section |
| `![[Meeting notes#^abc123]]` | one block that has an ID |
| `![[photo.png]]` or `![alt](photo.png)` | an image |
| `![[photo.png\|300]]` or `![[photo.png\|300x200]]` | an image with a width, or width and height |
| `![[paper.pdf#page=3]]` | a PDF page; add `&height=400` to set the height |
| audio and video files | a player |
| canvases and Bases views | the view itself |

Checkboxes inside an embedded note can be ticked and are saved to that note. The embed stays visible while your cursor is on its line.

**External images.** An image that points to a web address is never loaded automatically. Click **Download image** on it: Manifold fetches it over a secure connection, checks its size and type, and saves it to your attachment folder.

## Pasting

Pasting formatted text from a web page or another app converts it to Markdown. ⇧⌘V pastes plain text. Images you paste or drag into a note are saved in the attachment folder from **Settings › Files & links**.

## Spelling

Spellcheck follows the language you are writing, detected automatically as you type. Code and formulas are not treated as prose. You can turn spellcheck off in **Settings › Editor**.

## Finding text in a note

⌘F finds text in the note you are editing. It also works in Reading view: Enter jumps to the next match, ⇧Enter to the previous one, Esc closes the bar.

## Related pages

- [Links & backlinks](LINKS-AND-BACKLINKS.md)
- [Properties & tags](PROPERTIES-AND-TAGS.md)
- [Hotkeys](HOTKEYS.md)
