# Settings & modules

Open Settings with ⌘, or with **Settings…** in the app menu. Settings are saved per workspace.

## Settings sections

The sidebar of the Settings window groups the pages like this:

| Group | Pages |
|---|---|
| **Options** | General, Editor, Files & links, Appearance, Hotkeys, Modules |
| **AI** | Models, Calibration, Memory, Assistant, Performance |
| **Learning** | Cards, Quiz, Readiness |
| **Backup** | Snapshots, Local backup, External backup, Restore |
| **Privacy** | Network, Telemetry, Data, Integrations, Permissions |
| **Developer** | Technical views: logs, diagnostics, the sandbox, model details, the test runner and snapshot storage (shown when Developer mode is on) |
| **About** | About Manifold |

Changes are applied when you choose **Save changes**. If you close the window with unsaved changes, Manifold asks whether to keep editing or discard them. If the settings were changed elsewhere in the meantime, Manifold asks you to reload instead of overwriting the newer values.

### General

- **Content language hint**: Automatic (recommended), Hungarian or English. The editor detects the language of each note by itself; this hint only guides templates and generated content. The interface stays in English.
- **On startup**: open the last workspace, or show the workspace picker.
- **Run setup again** repeats the first-run setup.
- **Check app health** opens the health check. See [Health & troubleshooting](HEALTH-AND-TROUBLESHOOTING.md).

### Editor

- **Default editing mode**: Live Preview or Source mode.
- **Readable line length**.
- **Spellcheck with automatic language detection**.
- **Tab size**: a whole number from 1 to 8.
- **Slash menu**: turns the `/` insert menu on or off.

### Files & links

- **New note folder**, **Attachment folder**, **Templates folder** and **Daily note path**. Paths are relative to the workspace. Leave a folder empty for the workspace root, use `.` for the folder of the current note, and `./Assets` for a subfolder beside it. Existing notes and folders are not moved.
- The daily note path takes date tokens such as `YYYY-MM-DD`, with literal folder names in brackets: `[Daily]/YYYY-MM-DD`. The `.md` extension is added for you.
- **New link format** and **Use `[[Wikilinks]]`**. See [Links & backlinks](LINKS-AND-BACKLINKS.md).

### Appearance

- **Theme**: System, Light or Dark.
- **Editor font size**: 12 to 28.
- **Quiet mode**: hides interface elements you do not need. Errors and unsaved changes stay visible.

Burgundy is Manifold's accent colour.

### Hotkeys

Lists every command with its shortcut so you can change it. See [Hotkeys](HOTKEYS.md).

### Pages that point elsewhere for now

> [!note] Still being finished
> The AI pages (Models, Calibration, Performance), the Learning pages and the Backup pages are not final yet. For now they explain what is available and open the existing controls: model status and the Models table are in the Manifold panel (⇧⌘M), and **Snapshots** and **Restore** open the note history. Guided model installation and testing are planned. See [AI & models](AI-AND-MODELS.md).

The Privacy pages are described in [Privacy & data](PRIVACY-AND-DATA.md).

## Modules

Modules are the tools of Manifold. Turn a module off in **Settings › Modules** and its commands and tools disappear. Your notes and the module's data stay in the workspace, and opening a file that belongs to a disabled module tells you which module to enable.

During setup you chose an experience (Student, Knowledge worker, Developer, Research or Custom). That only set the starting selection of modules. You can change any module at any time.

| Module | What it does |
|---|---|
| **Backlinks** | Backlinks, unlinked mentions and outgoing links for the open note |
| **Outline** | The headings of the open note |
| **Properties** | The properties panel and the *All properties* view |
| **Quick switcher** | Open or create a note by name or alias (⌘O) |
| **Search** | Workspace search, in a window or docked in the sidebar |
| **Slash commands** | The `/` insert menu |
| **Tags** | The tag tree, tag completion and tag search |
| **Templates** | Insert a template, or start a note from one |
| **Daily notes** | Open today's note (⇧⌘D) |
| **Canvas** | Boards where you arrange notes, images and text freely |
| **Bases** | Table, board and card views over your notes' properties |
| **Graph** | The workspace graph and the local graph of a note |
| **PDF reader** | Read PDFs and insert highlights as quotes |
| **Media player** | Audio and video, with time codes you can insert into a note |
| **Cards** | Review cards on a spaced-repetition schedule; make cards from a note (needs AI) |
| **Quiz** | Multiple-choice quizzes made from a note (needs AI) |
| **Summaries** | Summaries of a note or a folder (needs AI) |
| **Math** | Solve problems and check derivations in a sandbox |
| **Code workbench** | Check solutions against tests in a sandbox. See [Code workbench](CODE-WORKBENCH.md) |
| **Notebook photos** | Turn photos of handwritten pages into notes (needs AI) |
| **Video & transcripts** | Add videos from links you give and get transcripts (needs network and AI) |
| **Ask your vault** | Ask questions that are answered from your notes (needs AI). The command is called *Ask your workspace…* |
| **Assistant** | Suggestions for links, tags and templates, learned on this Mac |
| **Calendar & Reminders** | Connect to macOS Calendar and Reminders (off until you allow it) |
| **Readiness** | An estimate of how prepared you are for exams, from your calendar, cards and quizzes |
| **Tracker** | Usage statistics kept on this Mac only |

"Needs AI" means the feature works only when a suitable local model is installed. Everything else works without any model.

## Related pages

- [AI & models](AI-AND-MODELS.md)
- [Privacy & data](PRIVACY-AND-DATA.md)
- [Getting started](GETTING-STARTED.md)
