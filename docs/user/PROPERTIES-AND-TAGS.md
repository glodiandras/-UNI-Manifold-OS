# Properties & tags

Properties and tags describe your notes so you can group, filter and find them. Both are stored as plain text in the note itself.

## Properties

Properties are `key: value` pairs in the YAML block at the very top of a note:

```
---
status: draft
due: 2026-11-01
tags: [project, planning]
aliases: [Q4 plan]
---
```

In the editor this block appears as a **Properties** panel at the top of the note. Add a property with **New property**, edit values in place, and fold the panel with the command *Show / collapse properties*.

### Property types

Each property key has a type, and the type applies to every note that uses the key:

- Text
- Number
- Date
- Date and time
- Checkbox
- List

Choose a type from the icon beside a property name. Saving a type does not convert any values. If a note holds a value that does not fit the type, the value is kept in the note's source as it is. The types are saved in the workspace's `.obsidian/types.json` file, so Obsidian reads the same choices. The built-in `tags` and `aliases` properties have a fixed type.

### Aliases

List other names for a note under `aliases`. The quick switcher (⌘O) matches them.

### All properties

Open the **Properties** view in the left sidebar (or run *Properties (all properties)* from the command palette) to see every property key in the workspace with a count. Sort the list by name or by count. Turn the **Properties** module off in **Settings › Modules** to hide the panel and the view.

## Tags

A tag is a label that starts with `#`, such as `#project` or `#class/physics`. You can write tags:

- in the body of a note: `This needs a reply #todo`,
- in the `tags` property, without the `#`.

Tags can be nested with `/`. A search for `#class` also finds notes tagged `#class/physics`.

### Work with tags

- Typing `#` in a note offers tags that already exist in the workspace.
- Clicking a tag, in the editor, in Reading view or in the properties panel, searches the workspace for it.
- The **Tags** view in the left sidebar shows the tag tree with note counts. Click a tag to list its notes. Sort the tree by name or by count.

The **Tags** module turns tag handling on or off in **Settings › Modules**.

## Find notes by property or tag

The search language understands both:

| Search for | Finds |
|---|---|
| `tag:#project` | notes with the tag, and its nested tags |
| `[status]` | notes that have a `status` property |
| `[status:draft]` | notes whose `status` contains "draft" |

More operators are in [Search](SEARCH.md). The **Bases** module can show properties as a table, board or cards: add a Bases view from the insert menu (`/`) or create one from the file tree.

## Related pages

- [Notes & editing](NOTES-AND-EDITING.md)
- [Links & backlinks](LINKS-AND-BACKLINKS.md)
