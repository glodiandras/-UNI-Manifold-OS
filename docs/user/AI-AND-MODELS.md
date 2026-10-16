# AI & models

AI in Manifold is optional. Writing, links, search, tabs, history and all the other basics work without any model. AI features run on models stored on your Mac, and they are held to a simple rule: only a model that has been measured for a task may change your notes.

## What uses AI

| Feature | Where you find it |
|---|---|
| Cards from a note | *Cards from this* |
| Quiz from a note | *Quiz from this* |
| Summary of a note or folder | *Summary*, *Summary from folder* |
| Ask your workspace | *Ask your workspace…* |
| Search by meaning | the **By meaning** switch in Search |
| Writing assistant | ⌘J completes at the cursor or expands the selection, ⇧⌘J summarises it |
| Notebook photos | *Add notebook photos…* |
| Formula recognition | *Formula from the clipboard (OCR)* (⌥⌘L) |
| Math solver | *Solve*, *Check derivation* |
| Code assistant | see [Code workbench](CODE-WORKBENCH.md) |
| Video import | transcripts and matching a video to your notes, in the Manifold panel |
| Test feedback | in [Readiness](SETTINGS-AND-MODULES.md#modules) |

Cards and quizzes that Manifold makes are saved in separate companion notes next to the note they came from. Every automated change is recorded, so you can undo it.

## Everything stays on your Mac

- Models run locally. No note text is sent to a cloud service. Cloud AI services are never used (see [Privacy & data](PRIVACY-AND-DATA.md)).
- A model is downloaded only when you ask for it, over a secure connection to the model host and nowhere else. After that it works offline.
- Models are large files, roughly 1 to 7 GB each. Manifold checks every installed model against the exact version it was tested with, and the health check reports a model that is incomplete or different.
- Manifold starts its AI engine only when a feature needs it, and it keeps two memory budgets: a smaller one for use while you work and a larger one for when the Mac has been idle for a long while.

## Trial and calibrated models

A model is **calibrated** for a task when it has been measured on a fixed set of reference examples for that task and reached the quality Manifold requires. Calibration is per task: a model can be calibrated for summaries and not for quizzes.

| | Calibrated | Trial |
|---|---|---|
| What it means | Measured for this task and good enough | Not measured for this task |
| Used automatically | Yes | No |
| What it may do | Run for real: its result is saved to your workspace as an undoable change, after the source checks | Only suggest, or work on a trial copy of your workspace |
| Label | none | **Trial** |

In **trial mode** you see the label, and either the result is only a suggestion, or the write goes to a clone of the workspace rather than to the workspace itself, so your notes do not change. This needs the workspace disk to be APFS; on other disks trial copies are unavailable (see [Workspaces](WORKSPACES.md)).

When no model is calibrated for a task, the feature says so (for example "No calibrated model") and does not run for real.

Quality checks apply on top of this. Answers must come with a source from your notes, and generated cards and quizzes must pass a check against the source text before they are saved.

### Where to see the state of your models

The **Models** section of the Manifold panel (⇧⌘M) lists each task, the model chosen for work and for idle time, and a check mark where the model is calibrated and current. A measurement made against an older reference set is marked outdated.

## Measuring a model

Measuring means running a model on the reference examples for a task and comparing the result with the required quality. The measurement belongs to you: it runs on your Mac, with your models, ideally while the machine is otherwise idle.

> [!note] Still being finished
> The guided flow is not part of this release yet. It is planned as **Settings › AI › Models** (install recommended models with progress and cancel, remove a model) and **Calibration** (a **Test this model** button that shows progress and the result against the required quality). Until then the AI pages in Settings only show what exists, the Models section of the Manifold panel shows the current state, and the measuring commands are available in Developer mode.

## Assistant and memory

The **Assistant** suggests links, tags and templates based on what you accept. It learns on this Mac only. **Settings › AI › Memory** lists everything it learned. Delete an item and it forgets it. When the Assistant is off, it does not learn.

Assistant completions in the editor appear as a suggestion. Press Tab to accept it as a single step that ⌘Z undoes.

## Related pages

- [Privacy & data](PRIVACY-AND-DATA.md)
- [Settings & modules](SETTINGS-AND-MODULES.md)
- [Health & troubleshooting](HEALTH-AND-TROUBLESHOOTING.md)
