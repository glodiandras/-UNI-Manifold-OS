# Search

Manifold searches the text of your notes, file names and paths, PDF pages and video transcripts. The search index lives on your Mac and rebuilds itself from your notes if it is ever damaged.

## Ways to search

| Tool | Use it to | Open with |
|---|---|---|
| **Quick switcher** | Jump to a note by name or alias, or create a note that does not exist yet | ⌘O |
| **Search** | Look through the whole workspace | ⇧⌘F |
| **Search in the sidebar** | The same search, docked next to your notes so the results stay while you work | the *Search* view in the left sidebar, or *Dock search in sidebar* in the command palette |
| **Find in note** | Look for text in the note you are editing | ⌘F |

Search results open with ↩. Add ⌘ to open in a new tab or ⌥⌘ to open in a split. ⌥↩ inserts a link to the selected result into the note you are editing, and ⌘G shows or hides the excerpts.

Results refresh while you work. The docked search keeps your query, results and scroll position when you switch to another view.

## The search language

| Write | To find |
|---|---|
| `word word` | notes that contain both words, ignoring accents and capital letters |
| `"exact phrase"` | the words one after the other |
| `a OR b` | either word |
| `-word` | notes without the word |
| `(a OR b) c` | grouping with parentheses |
| `path:folder` | matches in the path; `file:name` matches in the file name |
| `tag:#tag` | notes with the tag or a nested tag |
| `line:(a b)` | both words on the same line |
| `section:(a b)` | both words in the same section, from a heading to the next heading of the same or higher level |
| `task:word` | inside a task line; `task-todo:` for open tasks, `task-done:` for finished ones |
| `[property]` | notes that have the property; `[property:value]` matches its value |
| `match-case:(…)` | case- and accent-sensitive matching inside the parentheses; `ignore-case:(…)` switches back |
| `*word` | the word anywhere inside a longer word; `substring:(…)` applies it to every word in the parentheses |
| `/regular expression/` | a regular expression on the note's text |

A word matches the beginning of words by default, so `hous` finds "house" and "houses". The toolbar above the results has the switches **Match case**, **Inside words** and **More context** (extra lines around each match), and a **Sort** menu: relevance, file name A–Z or Z–A, modified newest or oldest first.

To search a single folder, right-click it in the file tree and choose **Search in this folder**.

## Search inside a note

Add a code block with the language `query` to show live search results inside a note:

````
```query
tag:#project task-todo:review
```
````

The block updates as your notes change.

## Search by meaning

The **By meaning** switch next to the search field adds results that are close in meaning to your words, not just in spelling. It uses a local model and needs the models listed under "Search by meaning" in [AI & models](AI-AND-MODELS.md). Without them, search stays word-based.

## Ask your workspace

*Ask your workspace…* (command palette) answers a question using only your notes. The answer arrives sentence by sentence and each sentence shows the note and section it came from. If nothing in your notes supports an answer, Manifold does not make one up. Answers are not written into your workspace. This feature needs a language model; see [AI & models](AI-AND-MODELS.md).

## Related pages

- [Properties & tags](PROPERTIES-AND-TAGS.md)
- [Links & backlinks](LINKS-AND-BACKLINKS.md)
- [Hotkeys](HOTKEYS.md)
