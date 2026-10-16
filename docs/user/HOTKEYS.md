# Hotkeys

Almost everything in Manifold is a command, and every command can be run from the **command palette** (⌘P). Many commands also have a keyboard shortcut. This page lists the default shortcuts.

## Using shortcuts

- ⌘P opens the command palette. Type part of a command name and press ↩. The palette shows each command's shortcut next to its name.
- ⌘O opens the quick switcher, ⇧⌘F opens search, and ⌘, opens Settings.
- In the symbols below, ⌘ is Command, ⌥ is Option, ⇧ is Shift and ⌃ is Control.
- A shortcut only works where it makes sense. For example, the formatting shortcuts need an editable note, and the code shortcuts need a source file open. Shortcuts of a module that you turned off do nothing.

## Changing a shortcut

Open **Settings › Hotkeys**.

1. Find the command with the search box.
2. Click its shortcut field and press the new combination.
3. Press Backspace in the field to remove the shortcut, or **Reset** to restore the original.
4. Save your changes.

Manifold checks the combination before saving. A shortcut must include ⌘, ⌃ or ⌥ (function keys are the exception), a shortcut that another command already uses is refused with a message that names that command, and a few shortcuts are reserved by the app (⌘, for Settings). Commands that have no default shortcut, such as the folding commands, can be given one here.

## Default shortcuts

The tables are grouped by the category shown in the command palette.

<!-- table:begin -->

### Code

| Shortcut | Command |
|---|---|
| ⌘R | Code: check (compile and tests) |
| ⇧⌘R | Code: check in debug mode (ASan, UBSan; C and C++) |
| ⌥⇧F | Code: format (clang-format, C++) |

### Editor

| Shortcut | Command |
|---|---|
| ⌘J | Assistant: complete at the cursor or expand the selection |
| ⇧⌘J | Assistant: summarise the selection |
| ⌘B | Bold |
| ⌘F | Find in note |
| ⌥⌘L | Formula from the clipboard (OCR) |
| ⇧⌘H | Highlight |
| ⌘I | Italic |
| ⇧⌘E | Live Preview / Source |
| ⌥↩ | Open link at the cursor |
| ⌘E | Reading / editing |
| ⌘S | Save now |
| ⌘K | Set link |
| ⌘↩ | Toggle task status |

### File

| Shortcut | Command |
|---|---|
| ⌘N | New note in file tree |
| F2 | Rename note… |

### Focus

| Shortcut | Command |
|---|---|
| F6 | Next region |
| ⇧F6 | Previous region |

### General

| Shortcut | Command |
|---|---|
| ⌘P | Command palette |

### Log

| Shortcut | Command |
|---|---|
| ⇧⌘D | Open daily note |

### Manifold

| Shortcut | Command |
|---|---|
| ⇧⌘M | Manifold panel |

### Media

| Shortcut | Command |
|---|---|
| ⇧⌘I | Insert into the note: highlight as a quote from the PDF / timecode from the player |

### Navigation

| Shortcut | Command |
|---|---|
| ⌥⌘← | Back to previous note |
| ⌥⌘→ | Forward to next note |

### Pane

| Shortcut | Command |
|---|---|
| ⌥⌘↓ | Split down |
| ⇧⌘2 | Split right |

### Quick switcher

| Shortcut | Command |
|---|---|
| ⌘O | Open file |

### Search

| Shortcut | Command |
|---|---|
| ⇧⌘F | Search the workspace |

### Settings

| Shortcut | Command |
|---|---|
| ⌘, | Open settings |

### Tab

| Shortcut | Command |
|---|---|
| ⌘W | Close tab |
| ⌘9 | Last tab |
| ⌘T | New tab |
| ⌃Tab | Next tab |
| ⌃⇧Tab | Previous tab |
| ⇧⌘T | Reopen closed tab |
| ⌘1 | Tab 1 |
| ⌘2 | Tab 2 |
| ⌘3 | Tab 3 |
| ⌘4 | Tab 4 |
| ⌘5 | Tab 5 |
| ⌘6 | Tab 6 |
| ⌘7 | Tab 7 |
| ⌘8 | Tab 8 |

### View

| Shortcut | Command |
|---|---|
| ⌘0 | Reset zoom |
| ⌥⌘2 | Show / hide right sidebar |
| ⌥⌘1 | Show / hide sidebar |
| ⌘= | Zoom in |
| ⌘- | Zoom out |

<!-- table:end -->

## Keys built into the editor

| Shortcut | What it does |
|---|---|
| ⌘Z | Undo |
| ⇧⌘Z | Redo |
| Tab and ⇧Tab | Indent and outdent the selected lines |

## Keys in other places

| Where | Key | What it does |
|---|---|---|
| Search results | ↑ and ↓ | Move through the results |
| Search results | ↩ | Open the result |
| Search results | ⌘↩ | Open the result in a new tab |
| Search results | ⌥⌘↩ | Open the result in a split |
| Search results | ⌥↩ | Insert a link to the result into the open note |
| Search results | ⌘G | Show or hide the excerpts |
| Search results | Esc | Close the search window |
| Card review | Space | Show the answer |
| Card review | 1 to 4 | Rate the card |
| Card review | ⌘Z | Undo the last rating |
| Insert menu (`/`) | ↑ and ↓, ↩ or Tab, Esc | Move, insert, close |
| Links | ⌘-click | Open in a new tab |
| Links | ⌘⌥-click | Open in a split |
| Links | hold ⌘ while hovering | Preview the target |

## Related pages

- [Settings & modules](SETTINGS-AND-MODULES.md)
- [Layouts & tabs](LAYOUTS-AND-TABS.md)
- [Notes & editing](NOTES-AND-EDITING.md)
