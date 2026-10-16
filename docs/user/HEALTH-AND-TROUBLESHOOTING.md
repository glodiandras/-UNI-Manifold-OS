# Health & troubleshooting

Manifold can check its own state and tell you, in plain words, whether something needs attention. The checks only read your data. A fix runs only when you choose it, and every fix can be undone or rebuilds itself.

## Open the health check

- **Settings › General › Check app health**, or
- the command *Open app health check* in the command palette, or
- the message **The search index has a problem. Open diagnostics.** in the status bar, if one appears.

## What the checks do

Each check shows a status, in words and with an icon (never colour alone):

| Status | Meaning |
|---|---|
| **Healthy** | Nothing to do |
| **Note** | Something worth knowing, no action needed |
| **Needs attention** | Manifold works, but a problem is building up |
| **Problem** | Something is wrong and needs your attention |

Open a check to see three things:

- **Diagnose**: the facts the check found, such as the number of indexed files or the free space on a drive.
- **Fix**: what a safe automatic fix would do, with a **Fix automatically** button, or the steps to take by hand when no automatic fix exists.
- **Learn more**: what the check looks at and why it matters.

Use **Check again** after you fix something. The sections below are the same explanations as in the app.

## Search index

The search index is a fast lookup built from your notes. It is never the only copy of anything: if it is damaged, Manifold rebuilds it from your Markdown files.

**Fix automatically** sets the damaged index aside, keeping it as a copy, and rebuilds it from your notes. Search may be incomplete for a moment. If this keeps happening, close and reopen the workspace and check that the disk is not full.

## Snapshots

Before each change Manifold stores a snapshot so you can undo it. Snapshots live in a separate safety store next to your notes. A leftover lock from an interrupted save blocks new snapshots until it is cleared.

**Fix automatically** sets an old leftover lock aside (renamed, not deleted), only if nothing is saving. Snapshots work again right away. If Apple's Command Line Tools are missing, install them by running `xcode-select --install` in Terminal and then reopen Manifold.

## Locks

Locks prevent two parts of Manifold from using the AI engine at once. If the engine crashes it can leave a lock file behind, which is safe to set aside once nothing is using it.

**Fix automatically** sets the leftover lock file aside (renamed, not deleted). The AI engine creates a new one when it starts. If the lock is still in use, wait for the running task to finish and check again.

## Disk space

Snapshots, backups and the search index grow over time. When the disk is nearly full, saving can fail, so Manifold warns you early. Free up space by removing files you no longer need, or move the workspace to a larger drive.

The image cache can be cleared with **Fix automatically**. It rebuilds itself when needed, and your notes and attachments are not touched.

## AI models

AI models are optional and are downloaded only when you ask. Installed models are checked against the exact version Manifold was tested with. If a model is incomplete or different, open **Settings**, then **AI** and **Models**, to repair or reinstall it. That page is still being finished; see [AI & models](AI-AND-MODELS.md) for the current state.

## Workspace

The workspace is the folder that holds your notes. Manifold keeps a small settings file in it and a list of known workspaces on this Mac. External drives must be connected to open their workspace.

If the folder cannot be found, reconnect the drive that holds the workspace, or reopen the workspace from the workspace window. Do not move the folder while Manifold is running.

**Fix automatically** can tidy the workspace list: it saves a copy, then forgets the entries whose folders no longer exist. No notes or folders are touched, and the saved copy can be restored.

## Background services

Manifold runs a small background service on this Mac. It starts the AI engine only when a feature needs it. If something is wrong, quit and reopen Manifold. If another program is using the same network port, quit that program first.

## Installation

When Manifold is built, it records a checksum for every file in the app. This check compares the installed app with that record, so a damaged or partly replaced installation is noticed. It never reads your notes.

If files were changed, added or removed after the build, reinstall Manifold. Your notes and settings are not part of the app and stay where they are. When Manifold runs from a developer folder, the check does not apply and only shows a note.

## Common situations

**"Something else changed this file."** If another program, a sync tool or an automated task writes to a note while you have unsaved edits, Manifold keeps your version on screen and does not overwrite the other one. Copy what you need, then reopen the note.

**Manifold stopped or restarted.** Saving runs continuously while you edit. If the background process stops, Manifold offers to restart it on the same port and the editor retries saving. If you are asked to copy unsaved text, do that first.

**Settings changed elsewhere.** If the Settings window says the settings changed elsewhere, reload them and review the new values. Manifold never overwrites a newer change.

**A feature is missing, or a view says its module is turned off.** Turn the module on in **Settings › Modules**. Your data is kept.

**Calendar access.** If Calendar & Reminders is on but nothing appears, open the Manifold panel and check the calendar section. Permission is granted by macOS; see [Privacy & data](PRIVACY-AND-DATA.md).

**An old version of a note.** Open the note's **History** in the right sidebar to look at earlier versions and restore one.

## For advanced users: Developer mode

**Settings › About › Advanced information** has a **Developer mode** switch. It adds technical views: logs, diagnostics, the sandbox, model details and the snapshot folders. Turn it off for everyday use.

## Related pages

- [Workspaces](WORKSPACES.md)
- [Privacy & data](PRIVACY-AND-DATA.md)
- [Settings & modules](SETTINGS-AND-MODULES.md)
