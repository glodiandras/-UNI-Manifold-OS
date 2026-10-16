# Files & explorer

The **Files** view in the left sidebar shows your workspace as a folder tree. Open it with ⌥⌘1, or from the ribbon.

## File types

Notes are Markdown files. Besides notes, the tree can hold canvases, Bases views, PDFs, images, audio and video, and source-code files for the [Code workbench](CODE-WORKBENCH.md). Files of other types are hidden by default. Turn on *Toggle showing all file types in the tree* in the command palette, or choose **Show all file types** from the empty-area menu, to see everything.

## Create

- ⌘N creates a note. Its folder follows **Settings › Files & links › New note folder**: empty means the workspace root, `.` means beside the current note, and a folder name puts new notes there.
- Right-click a folder and choose **New note here**, **New folder here**, **New note from template…**, **New Bases view here** or **New canvas here**.
- Typing a name in the quick switcher (⌘O) that matches no note offers to create it.
- Dragging files from Finder into the tree imports them into the workspace. Pictures and files you paste or drop into a note go to the attachment folder from **Settings › Files & links**.

## Rename, move, copy, delete

| To do this | Do this |
|---|---|
| Rename | Select the file and press F2, or right-click › **Rename…** |
| Move | Right-click › **Move…**, or drag it onto a folder |
| Make a copy | Right-click › **Make a copy**, or the command *Make a copy* |
| Delete | Right-click › **Move to Trash…** |
| Show in Finder | Right-click › **Reveal in Finder** |

Select several files with ⇧-click or ⌘-click to move them or send them to the Trash in one go.

- **Renaming and moving update links.** Before it rewrites anything Manifold shows how many files and links are affected. Each change gets its own snapshot, so it can be undone.
- **Delete uses the macOS Trash.** The file or folder can be restored from there. Links that pointed to it stay in your notes and show as unresolved.

## Sorting

Open the sort menu at the top of the Files view, or use the palette commands *Sort file tree: …*:

- file name A–Z or Z–A
- modified: newest first or oldest first
- created: newest first or oldest first

The creation order uses the date the file was created on disk. Files without a known creation date are listed last.

## Expand, collapse and follow

- *Expand all folders* and *Collapse all folders* are buttons at the top of the tree and commands in the palette.
- *Toggle auto-reveal of the active file* makes the tree follow the note you are editing.
- *Reveal in file tree* shows where the open note lives.

## Other views in the sidebar

The left sidebar also holds the **Tags**, **Properties** and **Search** views. See [Properties & tags](PROPERTIES-AND-TAGS.md) and [Search](SEARCH.md).

## Related pages

- [Layouts & tabs](LAYOUTS-AND-TABS.md)
- [Settings & modules](SETTINGS-AND-MODULES.md)
