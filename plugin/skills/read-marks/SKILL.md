---
name: read-marks
description: Read what the owner has drawn or written on a house's markup page and turn it into changes to the house file. Use when the user says they have marked up, drawn on, annotated or scribbled on a plan, or asks you to look at their marks.
---

# Reading marks on a plan

The page saves every stroke and note to `houses/<house>/marks.json` in the
workspace, in metres, tagged with its sheet and the time. Lay them out with
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
7. **Close each mark you have built in, in the same turn**, with the
   `resolve_marks` tool (`flawlessplan resolve <house> ID ... --note
   "..."`): its ids, and one line saying how it was dealt with. Where the
   owner drew on one sheet and meant others too — an option that another
   option extends — give `sheets`, every sheet the change was made on. A
   mark you have not acted on, or have a question about, stays open. Never
   delete a mark: that is the owner's, on the page.

Never add code or rules that guess what a mark means.
