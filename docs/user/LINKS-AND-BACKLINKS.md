# Links & backlinks

Links turn separate notes into a connected workspace. Manifold keeps track of every link in both directions.

## Create a link

Type `[[` and start typing a note name. Manifold suggests matching notes; press ↩ to accept. A few forms:

| Write | Links to |
|---|---|
| `[[Project plan]]` | the note called Project plan |
| `[[Project plan\|the plan]]` | the same note, shown as "the plan" |
| `[[Project plan#Budget]]` | a heading inside the note |
| `[[Project plan#^abc123]]` | a block that has an ID |
| `[[#Budget]]` | a heading in the current note |

Ordinary Markdown links work too: `[the plan](Project%20plan.md)` and relative paths such as `[notes](../Archive/Old.md)` open the note.

Which style Manifold writes when it inserts a link for you is set in **Settings › Files & links**:

- **New link format**: shortest unique path, relative path, or absolute path in the workspace.
- **Use `[[Wikilinks]]`**: turn it off to have links written as `[text](path.md)`.

These settings apply to links inserted from then on. Existing links keep their style, also when a note is renamed.

## Open a link

- Click a link to open it in the current tab.
- ⌘-click, or a middle click, opens it in a new tab. ⌘⌥-click opens it in a split.
- Hold ⌘ while hovering a link to preview the target without leaving the note. The command *Preview link at the cursor* does the same from the keyboard, and *Open link at the cursor* (⌥↩) follows it.

A link to a note that does not exist yet is shown dimmed. Clicking it creates the note.

## Rename and move safely

When you rename or move a note or folder, Manifold shows the list of files whose links would change before it rewrites anything. A rename can be undone.

## Backlinks and other connections

Open the right sidebar (⌥⌘2) while a note is active. It has these sections:

- **Backlinks**: the notes that link here. A filter box narrows the list.
- **Unlinked mentions**: notes that mention this note's name without linking to it. Choose a mention to turn it into a link.
- **Outgoing links**: the links in this note.
- **Outline**: the headings of the note.
- **History**: earlier versions of the note.
- **Similar notes**: notes that resemble this one.

The status bar shows how many backlinks the note has, and clicking the count opens the Backlinks section. The **Backlinks** module controls the backlinks, unlinked mentions and outgoing links sections, and the **Outline** module controls the outline. Both can be turned off in **Settings › Modules**.

## Aliases

A note can list other names for itself in its `aliases` property. The quick switcher (⌘O) finds the note by any of them. See [Properties & tags](PROPERTIES-AND-TAGS.md).

## The graph

The **Graph** module draws your notes and their links. Use *Open graph view* for the whole workspace or *Local graph from this note* for the neighbourhood of the note you are reading. Both are in the command palette.

## Related pages

- [Search](SEARCH.md)
- [Files & explorer](FILES-AND-EXPLORER.md)
