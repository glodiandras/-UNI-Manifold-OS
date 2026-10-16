# Privacy & data

Manifold is local-first. Your notes, your history and everything Manifold learns about how you work stay on your Mac. There is no account, no telemetry and no cloud AI.

> [!note] Still being finished
> The Privacy pages in Settings are being completed. This page describes how the app behaves today and what the pages are meant to show. Where a page does not exist yet, the same information is available in the places named below.

## Where your data lives

Everything is stored on this Mac. Nothing is uploaded. **Settings › Privacy › Data** shows where each kind of data lives.

| Data | What it is |
|---|---|
| **Your notes** | Your Markdown notes and attachments, in the workspace folder. Other apps can open this folder too. |
| **Snapshots** | Safety copies taken before each change so you can undo it |
| **Search index** | A fast lookup that rebuilds itself from your notes |
| **Task records** | Records of background tasks |
| **Caches** | Temporary files, such as resized images, that rebuild themselves |
| **AI models** | Downloaded models, which can be downloaded again |
| **Local backup** | Text backups of your workspace on this Mac |
| **Personal data** | Usage statistics and calendar information, stored on this Mac only |

Deleting the hidden `.manifold` folder of a workspace removes Manifold's data for it and leaves your notes untouched.

## Network

Manifold works offline. It uses the network only for things you start yourself:

- downloading AI models,
- installing extra tools, for example the C++ toolchain,
- downloading videos from links you give it,
- downloading an external image that you click **Download image** on.

These are never allowed: telemetry and analytics, cloud AI services, background syncing and background update checks. **Settings › Privacy › Network** shows whether offline mode is on and lists the downloads you started.

External images inside notes are never loaded automatically. Replacing the web link in the note with the downloaded copy is a separate, explicit choice.

## Assistant memory

The Assistant suggests links, tags and templates based on what you accept, and it learns on this Mac only. **Settings › AI › Memory** lists everything it learned; delete an item and it forgets it. Turn the Assistant off and it stops learning. See [AI & models](AI-AND-MODELS.md).

## Usage statistics

The **Tracker** keeps usage statistics on this Mac only. It stores which commands you use, how many edits you make, how long you are active and how quickly Manifold responds. It never stores the text of your notes. You can export the statistics or delete them in **Settings › Privacy › Telemetry** or in the **Usage** section of the Manifold panel (⇧⌘M), and you can turn the Tracker off in **Settings › Modules**. There is no remote telemetry.

## System permissions

macOS, not Manifold, grants access to notifications and to Calendar & Reminders. Manifold asks only when you use a feature that needs one.

- The Calendar & Reminders switch in Settings never asks for permission by itself. Permission is requested only when you choose **Request calendar access…** or use the calendar command.
- Permissions show as *Allowed*, *Denied*, *Limited*, *Write only* or *Not asked yet*. If access is denied, allow Manifold in the macOS system settings under Calendars (and Reminders).
- Manifold writes a calendar event only for a suggestion you approved.

**Settings › Privacy › Integrations** and **Permissions** let you choose which features may connect to other parts of macOS. Changes apply after you save.

## Keeping your data safe

- Every automated change takes a snapshot first, so it can be undone.
- Deleted files go to the macOS Trash.
- Code and math checks run in an isolated sandbox with strict time and memory limits, with no network, and can write only inside their own temporary folder.

## Related pages

- [Workspaces](WORKSPACES.md)
- [Health & troubleshooting](HEALTH-AND-TROUBLESHOOTING.md)
- [Settings & modules](SETTINGS-AND-MODULES.md)
