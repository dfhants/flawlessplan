# Working in this repo

Flawlessplan: floor plans drawn from a house file. `flawlessplan/` is the
engine: it reads a YAML description of a house and emits one SVG per sheet,
PNGs, a report and a markup page. `houses/` holds the houses, a folder each. The README has
the schema. Nothing in the engine knows about any one house.

A house is corrected conversationally — "the WC is smaller", "bedroom 2
should be 4.15" — and each correction is a change to its `house.yaml`.
Expect many small iterations, not one big pass. **Before working on a
house, read the `CLAUDE.md` and `context.md` in its folder if it has them**:
what its owner wants, what is decided, what is open.

## Build

```bash
python3 build.py          # every house -> build/<name>/
python3 build.py --png    # also rasterise every sheet
.venv/bin/python -m flawlessplan --houses flawlessplan/examples check cottage
.venv/bin/python -m pytest -q tests
```

Set up once with `/opt/homebrew/bin/python3.13 -m venv .venv &&
.venv/bin/pip install -e ".[dev]"` (Python 3.10 or later; everything is a
pip package, PNGs included — no Inkscape). `build.py` uses `.venv` when it
is there. `build/` is generated. **Edit `flawlessplan/`, never
`build/`.** Serve with the `flawlessplan` launch config (`build.py --serve`),
which draws the two examples.

This repo holds no houses of its own beyond the two examples in
`flawlessplan/examples/`, which `build.py` draws into `build/`. People's
houses live in workspaces — their own folders, made by `flawlessplan init`. Anything that needs to know where houses live or where drawings go
asks `workspace.Workspace` — never a path written into the engine.

## Files

```
flawlessplan/expr.py        arithmetic over named measurements; nothing else evaluates
flawlessplan/model.py       reads a house file, merges parts, resolves every number
flawlessplan/geom.py        one sheet's geometry: walls as polygons, openings, rooms as faces, the checks
flawlessplan/stairs.py      flights, landings, winders, the cut
flawlessplan/fittings.py    what is built in: the kinds, their usual sizes, each one's symbol
flawlessplan/labels.py      where each room's label goes
flawlessplan/solve.py       a house solved once: every sheet, what it changes, its labels, its notes
flawlessplan/render.py      a solved sheet as SVG; the drawing styles. Works nothing out
flawlessplan/outline.py     the dimensioned outline sheet
flawlessplan/report.py      a solved house as figures; snapshots and how they differ
flawlessplan/query.py       what a sheet has at a point or in a box
flawlessplan/marks.py       what was drawn on a page, laid out for reading; a mark's life: open, resolved
flawlessplan/page.py        the markup page, from flawlessplan/assets/page.{html,css,js}; the page that is
                            sent, from share.{html,css,js}. Both zoom with assets/view.js
flawlessplan/icons.py       the icon's PNG sizes, remade from assets/icon.svg when it changes
flawlessplan/workspace.py   where a person's houses are kept and drawings go; `init`
flawlessplan/examples/      cottage and bungalow: copied into a new workspace, and held to their snapshots
flawlessplan/edit.py        a house file changed, by a tool or by the page: version checked, kept only if it
                            solves, redrawn; and the sheets put in order, hidden, binned, as changes to its text
flawlessplan/server.py      serves build/, saves what is drawn on the pages, and takes what the page does to the sheets
flawlessplan/mcp_server.py  the same things as tools for an agent (`flawlessplan mcp`, .mcp.json),
                            and the house file read and written for one with no folder
flawlessplan/cli.py         build / check / crop / at / marks / resolve / share / snapshot / serve / mcp
plugin/                  the Claude Code plugin: the tools (run from this repo by uvx) and the skills
.claude-plugin/          the marketplace file that lists it: `claude plugin marketplace add dfhants/flawlessplan`
packaging/release.py     sets the version everywhere it is repeated, and prints the steps to release it
../flawlessplan-site/    the website, its own repository: its `build.py` makes it from this one as it stands
packaging/mcpb/          the Claude Desktop extension: manifest, entry point, `build.py` -> dist/flawlessplan.mcpb
pyproject.toml           the package: `flawlessplan` on the command line
houses/<name>/           this workspace's houses: house.yaml; expected.json (what the tests hold it to);
                         marks.json (what was drawn on its page; not in git);
                         CLAUDE.md and context.md where the house has a story
tests/                   the engine on made-up plans; every house against its snapshot; the tools;
                         the command line, the server, and what a broken or hostile house file is told
```

Everything downstream of `solve.solve(path)` takes the `Solved` it returns
or one of its `Sheet`s. If an output needs a fact, work it out in `solve`
and let every output read it; do not re-derive it in a renderer. `solve`
hands back the same `Solved` while the file reads as it did, so an output
reads it and never changes it.

## The one rule that matters

**A dimension is written down once.** In a house file `survey` is what was
measured and `lines` is every wall line stepped off it; walls, openings and
rooms refer to those names. Change a measurement and every sheet follows.

Never write a number that can be derived. Real bugs this has caused:

- A door was placed at a literal `y=4.60`. A later change moved the wall it
  sat in, and the door ended up straddling two rooms.
- The stairwell was positioned from bedroom 4's east wall. Extending
  bedroom 4 collapsed the stairwell to zero width and it vanished.

The same goes for what one sheet does to another. A sheet that `changes`
another has its demolition, its gained floor and `{gained}` worked out from
the two; a room marked `zone: true` is outlined from its own face. `gone`,
`areas` and `dims` are there for what cannot be derived, not as the first
thing to reach for.

## Sheets, levels, schemes

`levels` lists the storeys bottom up. A sheet is one drawing of one level:
as built, or as one proposal would leave it. It says which with `level:`
(its own id by default), may carry a `scheme:` tag, and names the sheet it
`changes`. Options that should not show what comes out say `demolition:
false`. The outline sheet (`outline:`) is drawn first when there is more
than one sheet.

A sheet that `extends` an earlier one is that sheet as `model` read it —
parts in, omissions out (`Loader.flat`) — with its own lists after and its
own scalars in place; title, tab, scheme and notes are never taken on.
`omit:` takes walls, openings, rooms and stairs off a sheet by id once its
parts are merged, so a part need not be split to lose one wall on one
sheet. Both are settled in `model`: nothing downstream knows a sheet was
written that way, and what is omitted is demolition because it is no
longer there.

## How the engine draws

**Coordinates** Metres; x east, y south, north up the page. 100 SVG units
to the metre.

**Walls** The envelope is given by its outer faces and each external wall is
drawn inward by its own thickness, so the outside dimensions stay true.
Partitions sit on their centrelines. Walls are real polygons, unioned. A
wall that curves (`rise:`, `radius:` or `via:`) is turned into short
straight pieces by `model` — `geom.arc`, 5° each — and stays one wall: one
`Host`, whose line is a run of points and whose places are distances along
it. Nothing may assume a wall has one direction: ask `Host.frame(s0, s1)`
for the direction and the way in where an opening is, and `Host.run` for a
line along it. A
partition end runs on past its meeting point only at a corner — by half the
other wall's thickness when square, less off a chamfer — and not where it
carries straight on or dies into a wall passing through. An end on the
inside face of an outside wall runs on into it and is cut off with the rest
outside, so it leaves no gap against a face that is not square to it. `butt: true` on a wall stops it running on at all.

**Points on a wall** Any point in a sheet may be `{y: YM, wall: east}` (or
`x:`): where that wall is at that coordinate — its inside face if it is an
outside wall, its centreline if a partition, `side:` for another face and
`clear:` for a distance square off it. `model` turns it into a plain point
against the walls read so far, so nothing downstream knows. It is how
anything meets or runs along a wall that is not square to the page; never
interpolate along a slanted wall in `lines`. `on` and `off` would have
been the words, and YAML reads both as booleans.

**Openings** belong to a wall and sit at a position along it, so they move
with it. A `frame` beside a door is drawn in the door's plane, on the face
the leaf is hung on, so the two meet. A leaf hangs on the face it opens to
unless the door says `face:` — a door that opens in but sits flush with
the outside. Each is cut out of its own wall and no wider. Leaves are drawn 60°
open, hung on the face they open to. Use the leaf names — `cloak` 686,
`std` 762, `wide` 838, each plus an 80 mm frame — rather than inventing a
width.

**Fittings** are what a sales plan shows built in — bath, shower, WC,
basin, sink, hob, oven, worktop, boiler, cylinder, fitted wardrobe, and
`unit` for anything else with a label — and never furniture. A fitting's
back is against a wall, on a face, at a place along it (`from_start` and
`from_end` from the corner of the room, not the end of the wall's line);
`geom` stands it there and reports one that runs into a wall. Each symbol
is written once in `fittings.py`, in the fitting's own terms, and `render`
sets it down. Labels keep off them. They are in the report and in what an
edit says it changed, not in a snapshot.

**Rooflights** are `rooflights:` on the sheet whose ceiling they are in:
a middle, a width and a depth, read by `model`, set over a room by `geom`
(`Plan.rooflights`), drawn dashed with a cross over everything on the
floor. Labels keep off them and off their own label; with an `id` their
size is a name for notes. Like fittings they are in the report and in what
an edit says it changed, not in a snapshot. Never fake one as an `areas`
entry of style `zone`.

**Split levels** are levels: half-levels are listed in `levels` and drawn
a sheet each. `open: true` on an envelope point makes the wall leaving it
no wall — the floor's edge, drawn thin — which is where a half-level meets
the one beside it or a gallery looks down.

**Rooms** are a name and a seed point. The engine finds the face of the plan
the point is in — with every door shut — and measures it: a rectangle reads
its two sides; a round room its diameter; anything else its overall size —
the longest a tape reads across it each way (`geom.across`), over a chimney
breast and down each leg of an L, which is the figure a survey gives. It is
taken square to the page or to one of the room's own walls, so a room
between slanted walls reads its clear width. The true area is alongside.
All sizes are clear internal. `expect:` on a room is the size
it was given, in survey names; one that does not read it is reported, so
nobody compares a report with a survey by eye. `dividers` split an open space
into separately labelled rooms.

**Zones** mark rooms out as one region: not laid out yet, or to be dealt
with later. `zone: true` on a room is a zone of that room. `zones:` on a
sheet names several — `{name: PHASE 2, rooms: [HALL, WC]}` — and they are
outlined together, the walls between taken in, with their floor area as
`{PHASE2_area}`. The rooms stay drawn and labelled as they are. Never draw
a zone's outline by hand.

**Labels** place themselves: largest layout that fits, inside the room, off
door swings, stairs, fittings and demolition. This happens when a sheet is
solved, so `check` reports a label with nowhere to go. Glyph advances (`CH`
in `labels.py`) were measured off a render; remeasure if a font or size
changes. `dx`/`dy` on a room moves its label by hand. `label: west` (or any
side) sets it in the margin on that side with a line to the room, for a
room too small or too busy to carry it; `label: false` leaves it off.

**Stairs** A stair is a walking line with a width: each leg a flight, each
corner a landing or winders. Counting along it every tread is one riser, a
landing one, n winders n, plus the last riser onto the floor above. A sheet
shows the stair up to `cut_risers`; the level above shows the rest with
`{ref: ground.main, show: above}`, so between them the flight appears
exactly once. The cut end is the zigzag itself.

**Parts** Sheets that share half a house share it through `parts`, so they
cannot drift apart. Split a part where several sheets will need one half
without the other; where one sheet needs a part less a wall, `omit` it.

**Styles** say what a thing is, never how it is drawn: an area is
`outdoor`, `below`, `fitting`, `zone` or `new`; free text is `name`,
`small`, `mini`, `note` or `zone`. The tables are `AREAS` and `TEXT` in
`render.py`. Do not put a CSS class in a house file.

## YAML traps

- A comma inside a flow list splits it: `[XR, op('wide', pair=True)/2]` is
  three items. Give the expression a name in `lines` and use the name.
- Quote any string containing `: `, `{` at the start, or `#`.
- `IW` is the whole partition thickness. Define `HW: IW/2` in `lines` and
  step off that.

## Notes are not drawn

A sheet carries one line of text under it: its title and gross area. What
is said about it lives in `notes:` in the house file, grouped — `summary`,
`decided`, `unconfirmed`, `needs`, `about` — and comes out in the panel
beside the sheet, in `build/<house>/<sheet>.md` and in `report.json`. Room
sizes there come from the geometry; never write a size into a note by hand
when a `{NAME_w}` or `{NAME_area}` will do. One sentence per entry, no
manual wrapping. A layout choice the owner has not agreed goes in
`unconfirmed` and moves to `decided` when they do.

## What the owner draws on the page

Served by the launch config, each house's page saves every stroke and note
to `houses/<house>/marks.json`, in metres, tagged with its sheet and the
time. Nothing tells you when they draw: they will say so. Then use the
`read-marks` skill (`plugin/skills/read-marks/`), which is the procedure:
`python -m flawlessplan marks houses/<name>`, pictures first, signs before
positions, say back before changing.

A mark has an id (its time, where the page gave it no other) and is open
or resolved. `marks` lays out the open ones; `resolve_marks` closes the
ones built in, in the same turn as the change, with a line saying how and
the sheets they were applied to. A resolved mark
stays in `marks.json` and the page shows it in grey when asked; only the
owner deletes one, on the page. The page sends its whole list back, so the
server keeps resolved what was resolved meanwhile (`marks.keep`).

After a change made from marks, `crop` with their ids sets them on the
sheet as it is now — what was built beside what was drawn — and `show` with
a sheet gives the address that opens on it: that is the say-back.

Do not add code that guesses what a mark means. A classifier was written
and removed: give the reader better pictures and better questions to ask.

A plain `http.server`, or the page opened as a file, does not save; the
page says so.

A served page follows its house. It asks the server for `<house>/stamp`,
which stands for the page as it is in `build/` now, and loads itself again
— same sheet, same view, never under a stroke — when that changes. Every
tool that writes a house file redraws the house's pages (`_redraw`, from
`_rewrite`), so nobody has to remember to. A file edited by hand is redrawn
by the next build or `show`.

## The tabs are the owner's to arrange

On a served page a tab is dragged to a new place, a sheet is hidden from
the Hidden menu and shown again from it, and a hidden sheet is binned
there, after a second asking. Each is a change to the house file — the
order of `sheets:`, `hidden: true`, the sheet's block taken out — and is
made by `edit.py`, which is also what every tool that writes goes through:
`edit.same` (the version), `edit.rewrite` (kept only if it solves, then
`edit.redraw`). The page posts to `<house>/sheets` with the version it was
drawn from; never add a second way to write a house file. `order_sheets`
and `hide_sheet` are the same two for an agent. There is no tool that bins:
that stays on the page, where the owner confirms it, and is refused while
`edit.depends` finds a sheet that `changes` it, `extends` it or shows its
stair by `ref`. The text is changed in place — a sheet's remarks go with
it — and read back as YAML before it is written; where sheets are not a
list of blocks the change is refused and left to be made by hand.

A hidden sheet (`Sheet.hidden`) is not in `Solved.shown()`, which is what
the page's tabs, the file that is sent, the index and the outline read. It
is still in `sheets`, `plans()`, the report and the checks.

## What is sent to someone else

Every build writes `<house>-plans.html` beside a house's page, and the
page's Share button downloads it; `flawlessplan share <house>` makes it on
its own. It is every
sheet and its notes in one file that needs nothing else and saves nothing.
Each sheet is in it once, exactly as `solve` drew it; ← and → turn them
like slides. A before / what changes / after stepper on every sheet that
`changes` another was built and removed: the base sheet is already a tab,
and the changed sheet already draws what goes and what is gained, so it
said everything twice. Do not bring it back. `build --public` writes it only for the
houses it builds, so a private house's is never in `public/`.

## Verifying a change

Renders are downsampled and small details are unreadable in them.

**1. Read the report.** Every build prints each room's measured size and
every problem found; `build/<house>/report.json` has the same plus every
opening's wall, centre and width. Faster and more certain than squinting.

**2. Crop.** `flawlessplan crop cottage first 2.8 4 6 7.5` renders that box, in metres, at high resolution. With no box it is the whole sheet: for its shape against a source drawing, not for detail.

**3. Run the tests.** `tests/test_houses.py` holds every house to the
`expected.json` beside it: areas, each room as measured, every opening. When
a house is changed on purpose, `python -m flawlessplan snapshot houses/<name>`
rewrites it — read the diff before committing, it is the change as figures.

## What may be hosted

Only `public/`, made by `python -m flawlessplan build --public`: it is
emptied first and leaves out every house marked `private: true` — a real
home should be. Never deploy `build/`, and never
take `private` off a house without its owner saying so. A house file is
treated as untrusted when it is drawn: sheet ids are checked, text is
escaped, expressions cannot run away. Keep it so: `tests/test_untrusted.py`
holds each of these, and whatever is wrong with a house file is a
`ConfigError` or a `ValueError` that says so in a line — never anything
else, which the command line does not catch. A value that reaches the
drawing as anything but text (a `rot:`, a `style:`) is a number or one of
a fixed list by the time `model` has read it.

## Agents without this repo

`python -m flawlessplan mcp` (registered in `.mcp.json`) gives the same
reading tools — `check`, `report`, `at`, `crop`, `marks`, `measurements`,
and `share` for the file to send — `guide`, which is how a house is
started, and the ones that write: `set_measurement` for one value in
`survey`, `settle_note` to move a note between groups, and `read_house`,
`write_house`, `edit_house` and `add_to_house`, which are the house file
itself for an agent with no folder to write in (a chat in the desktop app).
`order_sheets` and `hide_sheet` change the sheets themselves, as the page
does. Each takes the `version` that `read_house` and every change give, and
refuses to write over a file that is no longer that one. `edit_house` takes
one passage, or `edits`: several, made in order and solved once, all kept
or none — never make an agent find an order in which half a change solves. The transport
is the `mcp` SDK's (version 2, which needs Python 3.10 or later). Keep it an
adapter: a tool is one call into the engine. Structural edits stay edits to
the house file — those tools make them and guess nothing; a file that does
not solve is put back.

`guide` is `assets/new-house.md` (the procedure, written once: the
`new-house` skill only points to it), `assets/house-file.md` (the README's
"A house file", held to it by a test — change both) and the examples.

## Gotchas

- **"X and Y are the same space."** A wall is missing or stops short of what
  it should meet. This is the old orphaned-wall and missing-wall bug, now
  reported instead of silently drawn.
- **"Stands inside one room" / "leads from X into itself".** Two rooms
  were made one and something that parted them was left: `geom` lists
  every stretch of wall with one room on both faces (`Plan.inside`), warns
  of a door, and of a whole wall that is not a nib or a screen. An edit
  that merges rooms says what it left as `still_standing`
  (`report.standing`), partial stretches too: decide on each.
- **A wall "ends in the open"** is information, not an error: nibs and walls
  that stop at a divider are legitimate. Read the list when a boundary moves.
- **A `sub` with a figure in it** ("plus 3.00 × 2.75 return") is a number
  written twice. Use `{w}`, `{h}`, `{area}` or a name where one will do; an
  edit that resizes the room lists the rest as `check_subs`
  (`report.stale`), because nothing can tell whether they still hold.
- **Irregular rooms** read their overall size, so width times depth is more
  than the floor there is; the area is what to trust. A quoted figure taken
  some other way need not be matched, so long as the space itself is right.
- **Rotated labels** offset perpendicular to the text, not along it.

## Not built

Curved stairs, curved door leaves, furniture that is not built in, and reading a plan off an image. No
drag editor: the house file is the editor, and a dimension is written once.
