---
name: read-marks
description: Read what the owner has drawn or written on a house's markup page and turn it into changes to the house file. Use when the user says they have marked up, drawn on, annotated or scribbled on a plan, or asks you to look at their marks.
---

# Reading marks on a plan

**Marks come first.** Before building or changing any sheet of a house,
read its open marks and act on them — even when the owner asked for
something else. A tool that changes a house answers with `open_marks`
while any are open; when it does, stop and read them.

The page saves every stroke and comment to `houses/<house>/marks.json` in
the workspace, in metres, tagged with its sheet and the time. A comment is
a numbered pin (a click) or a box (a drag) with words; its words are
listed beside the pictures, not written over them. When a comment is
made, what it is on — its room, and the doors, walls and fittings at the
pin or inside the box — is read off the plan and kept with it, with the
version of the house file it was made on. The owner never picks these
out; you are given them as `on:` and the version under each comment. Lay them out with
the `marks` tool (in a terminal: `flawlessplan marks <house>`).

It returns a brief. For each cluster of ink there is one picture of two
panels — the drawing as it is, and the same view with the ink — and under
it the strokes in the order drawn, each with its path, its time and the ink
nearest it. Magenta is the owner's ink and nothing else. Blue is what the
brief adds: a dot and number where a stroke starts, a ring where it ends,
metre ticks round both panels. The brief says when the house file has been
edited since the marks were made; then the ink was drawn on an older
drawing and may already be dealt with.

Only the marks still open come back. Each has an id, in backticks after
its number. `include_resolved` adds the ones already dealt with, in grey,
with how; `sheet` keeps it to one sheet's marks when there are many.

The tool lays the marks out. Reading them is your job, and the order
matters.

0. **Read what each comment is on, and its version, before acting.** The
   `on:` line is the plan's own names for what is at the pin or in the
   box. Where the comment was made on a version that is not the file's
   now, the brief says so and the picture sets the drawing it was made on
   beside the drawing as it is: check that what it is about is still
   there before you change anything for it.
1. **Look at the pictures first, and read the ink as signs** before you
   look at where it is. Strokes drawn seconds apart and touching are
   usually one sign. The first time this was used, a shaft and a V drawn
   two seconds apart were taken for "something in this area" when they
   were an arrow at one small thing.
2. **Decide what each sign is about** — an arrow its tip, a ring its
   inside, a cross the thing under it — and only then ask the plan what is
   there, with the `at` tool (`flawlessplan at <house> <sheet> 1.97 8.14`):
   a point, a point and a radius, or a box. It answers in the house file's
   own names.
3. **Look closer.** Read the place off the ticks and render a metre or
   less of it with the `crop` tool, marks on (`flawlessplan crop <house>
   <sheet> X0 Y0 X1 Y1 --marks`). A fault a wider view hides shows up.
4. **Say back what you take each mark to mean before changing anything.**
   A mark says where and what, never why. List the marks, your reading of
   each, and the change you would make; ask where the plan does not settle
   it. Do not guess a distance the owner did not give: put the figure in
   `survey` or `lines` with a comment that it is yours, and the choice in
   the sheet's `unconfirmed` notes.
5. Make each agreed change in `houses/<house>/house.yaml`, then `check`
   and read what it says — rooms come back measured, problems are named —
   before you look at a picture. A change made with the tools redraws
   the owner's pages itself; after editing the file by hand, call `show`
   so they are redrawn.
6. **Show the owner what you built beside what they drew**: the `crop`
   tool with `mark_ids` (`flawlessplan crop <house> <sheet> --ids ID ...`)
   sets those marks on the sheet as it is now, framed round them — once
   for each sheet the change was made on. `show` with the `sheet` gives
   the address that opens their page on it.
7. **Before resolving, read the source again for the area the mark
   covers** — not only your edit — and look at what you built: `crop` the
   place or `check` the house after the change. Each answers with a look
   id.
8. **Reply to each mark in the same turn**, with the `resolve_marks` tool
   (`flawlessplan resolve <house> ID ... --note "..."`): its ids, one line,
   and what the reply says it is.
   - `resolved` (the default): built in. It needs `checked`, the look id
     from step 7; a look taken before the change is refused.
   - `blocked`: it needs the engine changed or information nobody has
     given. Say which.
   - `question`: you need the owner to tell you something. Ask it.

   Blocked marks and questions stay where the owner sees them. A reply
   from the owner to any of the three opens it again, and the brief shows
   both replies: theirs is what they still want. `sheets` is per mark —
   `{ID: [ground, option-a]}` — for a mark meant for more than the sheet it
   was drawn on; left out, it is that sheet. Never delete a mark: that is
   the owner's, on the page.
9. **An error the owner did not mark**: put it right only if the source
   shows it plainly, and name it in your reply. Otherwise ask.

Never add code or rules that guess what a mark means.
