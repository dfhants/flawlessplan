# Flawlessplan

Floor plans from a house file. Draws to-scale floor plans for any house from a YAML description of it:
named measurements, an outline, walls, openings, rooms and stairs. Room sizes
and areas are measured from the geometry, never typed in.

It is plans as code. A house file holds relationships, not coordinates:
change one measurement and every sheet that depends on it follows, a
proposal is drawn against the as-built it changes, and every build says
what is wrong. The editor is the file — by hand, or an agent working from
conversation and from what is drawn on the page.

<https://flawlessplan.app> has the installer and the two examples to look at.

## Install

```
uv tool install git+https://github.com/dfhants/flawlessplan@v0.8.0
flawlessplan init my-houses         # a workspace, with two example houses
cd my-houses
flawlessplan build --serve          # draw them and open http://localhost:8765
```

Needs [uv](https://docs.astral.sh/uv/) (or pipx) and Python 3.10 or later,
and nothing else: no Inkscape, no system libraries.

A **workspace** is a folder of your own that holds your houses and what is
drawn from them:

```
my-houses/houses/<name>/house.yaml   the houses, a folder each
my-houses/build/                     everything drawn; for this machine
my-houses/public/                    `build --public`: only this is ever hosted
```

Commands work in the workspace they are run in, or `--workspace DIR`, or
`$FLAWLESSPLAN_WORKSPACE`. A house is named by its folder: `flawlessplan
check cottage`.

The two examples `init` copies in are `cottage` — two storeys in plain
numbers, the smallest useful file — and `bungalow` — an L-plan and a
proposal that fills its corner in: named measurements, parts, and a sheet
that `changes` another. They live in `flawlessplan/examples/`.

## Commands

```
flawlessplan build [HOUSE ...] [--png]     # no house: all of them, and the index
flawlessplan check HOUSE
flawlessplan crop  HOUSE ground 2.8 10.5 5.4 14.3
flawlessplan crop  HOUSE ground --ids ID ...   # what was built, beside those marks as drawn
flawlessplan at    HOUSE ground 2.0 8.1
flawlessplan snapshot HOUSE                # rewrite its expected.json
flawlessplan serve                         # the pages, saving what is drawn on them
flawlessplan marks HOUSE [--all] [--sheet S]   # lay out what was drawn and is still open, for reading
flawlessplan resolve HOUSE ID ... --note HOW   # close marks that have been built in
flawlessplan share HOUSE                   # one file to send: every sheet, to be read
```

Each house gets one SVG per sheet with its notes beside it as `<sheet>.md`,
`report.json` (room sizes, openings, notes, problems found), and
`index.html` — every sheet on a tab, with a layer to draw and write on —
and `<house>-plans.html`, the file to send (below).
`build/index.html` lists the houses, and carries the icon and a web
manifest, so the site can be added to a home screen or a dock.

On the page each sheet sits in the window like a map: 100% is the whole
sheet, − / + step from 25% to 1600%, and a pinch or ctrl/cmd + wheel zooms
smoothly on the pointer. Scroll or the Pan tool shifts it. Marks drawn at
any zoom land in the same place on the plan.

The sheets are the tabs along the top, and on a served page they are yours
to arrange. Drag a tab along the row — or Alt + ← / → with it focused — to
put the sheets in another order. **Hidden**, at the end of the row, hides
the sheet you are on, and lists the hidden ones with Show to bring each
back. A hidden sheet has no tab and is left out of the file you send; it
stays in the house file, drawn and checked. Bin…, then Bin, on a hidden
sheet takes it out of the house file for good, which is refused while
another sheet `changes` it, `extends` it or shows its stair. Each of these
is a change to the house file — the order of `sheets:`, `hidden: true`, the
sheet's own lines — made the way an agent's tools make one: refused if the
file is no longer the one the page was drawn from, kept only if the house
still solves, and a sheet stays after the one it changes or extends. What
was drawn on a binned sheet stays in `marks.json`.

The tools float on the drawing: Draw,
Text (click the plan, type, Enter), Pan, then Undo, Redo and Clear — this
sheet or every sheet, and Undo brings a clear back. Keys: `D` `T` `H` for the
tools, Space held to pan, ⌘Z / ⇧⌘Z, `+` `−` `0` to zoom and fit, `1`–`9` for
the sheets.

Served by `flawlessplan serve`, what you draw and write on a page is saved
to `houses/<house>/marks.json` as you go and is still there after a reload
or a rebuild. `flawlessplan marks HOUSE` lays it out for reading — pictures
of two panels, the drawing and the drawing with the ink, and the strokes in
order. It does not interpret.

A mark has a life. It is open until whoever built it into the plan says so
(`flawlessplan resolve`, or the `resolve_marks` tool); then it is resolved:
kept in `marks.json` with when and how it was dealt with, but no longer laid
out by `marks` (`--all` brings resolved ones back, in grey; `--sheet` is one
sheet's) and no longer on the page. Under a sheet's notes the page lists its
marks; tick Show resolved and the ones dealt with are drawn in grey over the
plan as it is now, each with how it was dealt with and the sheets it was
applied to — a mark drawn on one option and meant for two shows on both.
`crop` with `--ids` (the tool's `mark_ids`) sets named marks, resolved or
not, on a sheet as it is now — the one they were drawn on or one they were
applied to: one picture of what was built beside what was drawn.
Delete… on any mark, then Delete, takes it out of `marks.json` for good;
Undo does not bring it back. Clear and Undo act on open marks only.

## Showing a house to someone

The Share button on a house's page downloads `<house>-plans.html`, which
every build writes beside it (`flawlessplan share HOUSE` makes it on its
own, in `build/<house>/`): one file
with every sheet and the notes beside it, to be read and not drawn on. The
fonts are inside it and it asks nothing of any server, so it can be mailed
or dropped onto a phone and opened there; drag to move a sheet, pinch or
`+` `−` to zoom. Where scripts do not run it reads down the page instead.

The sheets are the slides: ← and → go from one to the next, in the order
the house file has them. Each is drawn once, as it is on its own page — a
sheet that `changes` another already shows what comes out and what is
gained, so nothing is repeated to say so.

The file holds the whole plan. `private` keeps a house out of `public/`;
it does not stop you sending this to whoever you choose.

## Working on flawlessplan itself

```
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # Python 3.10 or later
python3 build.py             # the two examples -> build/
.venv/bin/python -m pytest -q tests
```

Agents working in this repo: read [CLAUDE.md](CLAUDE.md) first. Procedures
for reading marks and starting a house are skills in `plugin/skills/`.

## A house file

x runs east and y runs **south**, in metres, so north is up the page.

```yaml
house:    {name: Example, front: west}
defaults: {ext_wall: 0.30, int_wall: 0.10}

survey:                       # what was measured
  W: 8.0
  D: 6.0
  rise: {value: 2.6, status: assumed}
lines:                        # everything stepped off it
  MID: W/2

sheets:
  - id: ground
    envelope: [[0, 0], [W, 0], [W, D], [0, D]]      # outer faces
    walls:
      - {id: split, from: [MID, 0], to: [MID, D]}   # centreline, 100 thick
    openings:
      - {door: std, wall: split, at: centre, hinge: n, swing: e}
      - {window: 1.2, at: [2.0, 0]}                 # finds the wall it is on
    rooms:
      - {name: LIVING, at: [1, 1]}                  # a point inside it
      - {name: KITCHEN, at: [7, 1]}
```

Any number may be an expression over the names in `survey` and `lines`.
Plain numbers work too, so a plan copied off a drawing needs neither table.

A length may be written in feet and inches as it was given — `sit_d: 14'10"`
— and the file keeps the figure. `status:` on a survey figure says where it
came from: `given` (measured, or quoted to you; what a bare figure is),
`traced` (read off a drawing) or `assumed` (a guess).

Wherever a sheet takes a point it may be given by one coordinate and the
wall it lies on, so nothing has to be worked out against a wall that is
not square to the page:

```yaml
envelope: [[0, 0], {at: [W, 0], id: east}, [W - splay, D], [0, D]]
walls:
  - {id: mid, from: [0, YM], to: {y: YM, wall: east}}        # runs to the east wall, wherever it is at YM
stairs:                                                     # a flight along it, half its width clear of the face
  - {id: main, path: [{y: 0.5, wall: east, clear: HALF}, {y: 3.5, wall: east, clear: HALF}]}
```

On an outside wall (named by its `id`) the point is on the inside face, or
with `side: out` the outside one. On a partition — one written above — it
is on the centreline, or with `side: w` (any compass point) on that face.
`clear:` moves it that much further, square to the wall, so two points
with the same `clear` make a line parallel to it.

A wall is straight unless it says how it curves, in one of three ways:
`rise:` how far the middle of it stands off the straight line between its
ends, `radius:`, or `via:` a point it passes through.

```yaml
envelope:
  - [0, 0]
  - [W, 0]
  - [W, D]
  - {at: [BX1, D], id: bow, rise: 0.7}     # the wall leaving this point bows 700 out; a rise below zero bows in
  - [BX0, D]
  - [0, D]
walls:
  - {id: sweep, from: [6, YM], to: [6, D], rise: 0.8, toward: e}    # a partition says which way
openings:
  - {window: 2.0, wall: bow, at: centre}   # follows the curve; its width is measured along it
```

A curved wall is one wall: it has one name, openings sit in it by their
distance along it, and `{x: 3, wall: bow}` is a point on it. A round
building is two points and two curves, each a half:
`[{at: [0, R], rise: R}, {at: [2*R, R], rise: R}]`. A door's leaf is
straight, shut across its opening. In a wall `path:`, the point a leg
leaves says how it curves: `{at: [4, 3], rise: 0.5, toward: n}`.

What is built in — and only that; no furniture — is a `fittings:` entry:
its kind, the wall its back is against, and where along it.

```yaml
fittings:
  - {worktop: 3.6, wall: north, at: {from_start: 0}}     # 3.6 long, from the corner of the room
  - {sink: true, wall: north, at: [1.6, 0]}              # `true`: the usual size
  - {bath: 1.7, wall: north, at: [BX, 0], corner: w}     # the point is the west end of its back
  - {basin: true, wall: split, side: e, at: [BX, 2.6]}   # a partition has two sides: say which
  - {unit: true, wall: north, at: {from_end: 0}, label: FF}
  - {cylinder: true, at: [5.2, 3.5], facing: s}          # against no wall: a point and the way it faces
```

The kinds are `worktop`, `sink`, `hob`, `oven`, `bath`, `shower`, `wc`,
`basin`, `boiler`, `cylinder`, `wardrobe` (fitted) and `unit` (anything
else built in, with a `label:` — FF, WM). The value is the width along the
back; `depth:` is how far it stands out. `at:` is as for an opening —
`centre`, a point, `from_start`, `from_end` — but the last two are measured
from the corner of the room. `flip: true` turns a bath or sink end for
end. One that runs into a wall or out of the building is reported.

A house on split levels is drawn a level at a time, like any other: list
the half-levels in `levels:`, bottom up, and give each its own sheet.
Where a level's floor ends at a drop or a rise and not at a wall, the
envelope says `open: true` on the point that edge leaves; the flight
between is a stair with `cut_risers` on the lower sheet and a `ref` on the
upper, and an `areas` of style `below` shows the other level beside it.
A step or two inside one level is a stair with no `cut_risers`, drawn
whole, and a `dividers` line where the floor steps makes the two sides
separate rooms.

The order of `sheets:` is the order of the tabs, of the file that is sent
and of everything the tools list.

A **sheet** is one drawing of one level of the house. With more than one
storey, list them bottom up in `levels:`; a sheet draws the level its id
names unless it says `level:`. A proposal is another sheet of the same
level that names the one it `changes`:

```yaml
levels: [ground, first]
sheets:
  - id: ground
  - id: first
  - id: extended
    level: ground
    scheme: extension        # a tag: which proposal this sheet belongs to
    changes: ground          # demolition, gained floor and {gained} come from the two
```

From `changes` the engine works out the walls that come out (dashed red;
`demolition: false` hides them), the floor gained (tinted) and the names
`{gained}` and `{base_gross}` for notes.

A sheet that is another sheet with more done to it says `extends:`, and
what it does without says `omit:`:

```yaml
  - id: option-e
    extends: option-d        # everything option-d has: its parts, its envelope, what it changes
    omit: [living_hall, hall_leg, HALL]      # a wall, opening, room, stair or rooflight by its id; a room by its name
    walls:
      - {id: snug_s, from: [XS, YS], to: [XE, YS]}       # and its own, after option-d's
```

`extends` takes the earlier sheet as it was read — its parts in, what it
omits out — puts this sheet's lists after its lists, and lets anything else
this sheet says (`envelope`, `changes`, `level`) stand in place of what
that one said. A sheet's `title`, `tab`, `scheme` and `notes` are its own
and are not taken on. `omit` is applied last, to the sheet with its parts
in, so one wall of a part can come off one sheet without the part being
split: the wall takes the openings and fittings that name it with it, and
comes out as demolition against `changes` like any other. `{wall: x}`,
`{opening: x}`, `{room: x}`, `{stair: x}` or `{rooflight: x}` says which is meant where two
things share a name. An `omit` that names nothing on the sheet is an error.

| Key | What it holds |
|---|---|
| `envelope` | Outer faces in order. A point may be `{at: [x, y], t: 0.25, id: south}` — thickness and name of the wall leaving it, `rise:`, `radius:` or `via:` if it curves, and `open: true` where the floor ends and no wall stands. |
| `walls` | `from`/`to` on the centreline, optional `t`, `id`; `rise:` or `radius:` with `toward:`, or `via:`, for a curve. `path:` for a run of several: its legs are `id.0`, `id.1` … in order, and an opening names the leg it is in (`wall: id.1`) — or the path itself, with `at:` a point, and finds its leg. |
| `openings` | `door:` (a leaf — `cloak`, `std`, `wide` — or a width), `window:` or `opening:` a width. `at:` is `centre`, a point, `{from_start: d}` or `{from_end: d}`. `hinge:` and `swing:` take compass points, `start`/`end`, `left`/`right`, `in`/`out`. `face:` (the same words as `swing:`) hangs the leaf on that face of the wall instead of the one it opens to. `pair: true`; `style:` `fold`, `slide`, `frame`, `none`. |
| `rooms` | `name`, `at`; optional `sub` (footnote, may use `{area}`, `{w}`, `{h}`), `size: small`, `rot`, `dims: false`, `dx`/`dy`, `id`. `expect: {w: sit_w, h: sit_d}` (any of `w` east–west, `h` north–south, `area`) is the size the room was given: a room that does not read it, within 50 mm, is reported. `zone: true` draws the room as a dashed outline with its area — there, but not laid out. `label:` a side (`west`, `east`, `north`, `south`) sets the label in that margin with a line to the room; `false` leaves it off. |
| `zones` | Rooms marked out together as one region: `{name: PHASE 2, rooms: [HALL, WC], sub: ..., label: west}`. Outlined as one, measured, and the rooms stay as drawn. |
| `dividers` | Undrawn lines that split one open space into two rooms. |
| `stairs` | `path` foot to head, `width`, `treads` per leg, `turns` (`landing` or `{winders: n}`; `reach: true` makes the lowest winder take in a level run before it), `cut_risers`, `show: below/above/all`. The level above reuses one with `{ref: ground.main, show: above}`. |
| `fittings` | What is built in: `bath`, `shower`, `wc`, `basin`, `sink`, `hob`, `oven`, `worktop`, `boiler`, `cylinder`, `wardrobe`, `unit` — see above. |
| `rooflights` | Lights in the ceiling over this sheet's floor: `{at: [x, y], w: 0.8, h: 1.0}` — its middle, and how far it runs east–west and north–south — with `id`, `label` (written under it) and `rot` if wanted. Drawn dashed with a cross, as what is overhead is; room labels keep off it. With an `id`, notes may use `{id_w}`, `{id_h}` and `{id_area}`. One that is not over the building is reported. |
| `areas` | Shapes with a `style` saying what they are: `outdoor` (roofed or paved, outside the walls), `below` (a lower roof seen from above), `fitting` (a built-in shape that is none of the `fittings`; labels keep off), and `zone` and `new` for a region or a gain the engine cannot derive. |
| `solids`, `labels`, `gone`, `dims` | Filled masonry; free text (`style:` `name`, `small`, `mini`, `note`, `zone`); demolition lines drawn by hand; dimension lines. |
| `notes` | What is said about the sheet, by kind: `summary` (one line), then lists `decided`, `unconfirmed`, `needs`, `about`. A plain list is `about`. None of it is drawn — it goes in the panel beside the sheet and in `<sheet>.md` next to the image. One sentence per entry, unwrapped. Notes may use any name, `{gross}`, `{gained}`, and room figures such as `{KITCHEN_area}`. |
| `require` | Conditions that must hold: `{that: "landing >= width", message: ...}`. |
| `level`, `scheme`, `changes`, `demolition` | Which storey, which proposal, and the sheet this one alters — see above. |
| `unlabelled: ok` | Do not report spaces that have no room in them. |
| `extends`, `omit` | The earlier sheet this one is, with more; and what it leaves out, by id — see above. |
| `hidden: true` | The sheet has no tab and is not in the file that is sent. It is still drawn, still checked, and other sheets may still change or extend it. |
| `use` | Parts to draw first — see below. |

`parts:` at the top level holds named groups of the same keys — any key of
a sheet, its `envelope` included. A sheet lists
the parts it is built from with `use:`, and a part may use others. Sheets
that share half a house share it through a part, so they cannot drift apart.

`outline:` configures the dimensioned outline sheet: `sheets:` it shows (by
default every sheet whose outline differs) and its `notes:`.

## What gets checked

Every build reports: an opening that runs off its wall or overlaps another;
a room seeded in a wall; two rooms that are really one space (a wall is
missing or stops short); a space with no room in it; a room that does not read
the size it was given (`expect`); a label with nowhere to go; a wall that ends in the open; a wall or a door left standing inside one room; a `require` that fails. Errors fail the
build.

## Hosting

`build/` holds every house and is for your own machine. To put plans on the
web, build the public set and host only that folder:

```
flawlessplan build --public     # -> public/, emptied first
npx vercel deploy --prod --cwd public
```

A house whose file says `house: {private: true}` is left out. `public/`
carries a `vercel.json` that asks search engines not to index it and sets a
content security policy. A hosted page is read-only: drawing on it is not
saved, and the page says so. Marks are only saved by the local server,
which answers only to its own pages on this machine.

## The website

The website is its own repository, `flawlessplan-site`, kept beside this
one. Its `build.py` makes the install page, the desktop installer to
download and the two examples as live pages, all from this repository as
it was last released. Publishing a release here deploys it.

## Releasing

`python3 packaging/release.py X.Y.Z` writes the version everywhere it is
repeated and prints the rest: commit, tag `vX.Y.Z`, push, build the
installer and publish the release, which deploys the website. The plugin
and the install line fetch that tag, so nobody is handed a commit that was
not released.

## Tests

```
.venv/bin/python -m pytest -q tests
```

`tests/test_engine.py` covers the engine on small made-up plans.
`tests/test_houses.py` holds every house to the `expected.json` beside it:
areas, each room as measured, where every opening is and how wide.
`tests/test_mcp.py` drives the agent tools.

## For agents

For Claude Code there is a plugin — the tools below and two skills, for
starting a house and for reading what was drawn on one:

```
claude plugin marketplace add dfhants/flawlessplan
claude plugin install flawlessplan@flawlessplan
```

It works in whichever project folder Claude Code is opened in, and needs
[uv](https://docs.astral.sh/uv/).

For the Claude desktop app there is a one-file installer:
`python3 packaging/mcpb/build.py` makes `dist/flawlessplan.mcpb`. Opening
it asks for a houses folder, fills an empty one with the two examples, and
adds the tools below. It runs with uv, which fetches what it needs.


`flawlessplan mcp` serves a workspace's houses as tools over the Model
Context Protocol (stdio; `flawlessplan init` writes the `.mcp.json` that
registers it): `list_houses`, `init_workspace`, `check`, `report`,
`measurements`, `at`,
`crop`, `marks` — the marks still open; `include_resolved` and `sheet` for more or fewer — `resolve_marks`, which closes the ones built in, `share` — the file to send, above — `show` — which draws everything and serves the pages from
the tool's own process, for an owner with no terminal, and with a `sheet` gives the address that opens on that tab (`…/bungalow/#infill`); a page that is open
is redrawn and loads itself again after every change the tools make — and `guide`, which
is how a house is started: the procedure, the keys below and the two
examples whole.

Each tool that changes a house file answers with what moved and what check
finds, and — where the change made one room of two — `still_standing`: the
walls and doors that parted them and are still there, inside the room —
and `check_subs`: rooms the change resized whose `sub` holds a figure
written by hand ("plus 3.00 × 2.75 return"), which may no longer hold.

Eight write. `order_sheets` puts the sheets in another order and
`hide_sheet` hides one or shows it again, as the page does; `list_houses`
says which are hidden. Binning a sheet is the owner's, on the page.
`set_measurement` changes one value in `survey` where it is
written, and `settle_note` moves a note from `unconfirmed` to `decided`.
Anything structural is an edit to the house file, and for an agent with no
folder to write in — a chat in the desktop app — four tools are that
edit: `read_house`, `write_house` (a new house, or the whole file of one
that is there), `edit_house` (one passage of it — or, with `edits`, several
at once: made in order, solved once at the end and kept or refused whole,
for a change no one passage of which solves alone) and `add_to_house` (one
more entry at the end of a list — a wall, a room, a note — without
quoting what is there). A file that does not solve is not kept, and each
answers with what `check` finds. `read_house` gives the file's `version`,
and so does every change: a tool given the version it is writing over
refuses if the file is no longer that, so a call that timed out can be
tried again without being made twice.

## Not built

Curved stairs, curved door leaves, furniture that is not built in, 3D, and reading a plan off an image.

## Licence

Free for any noncommercial use, such as drawing your own house, under the
[PolyForm Noncommercial License 1.0.0](LICENSE). The source is here to read
and change, and it is not open source: using it in or for a business needs a
commercial licence: [ask for one](https://flawlessplan.app/#licence).
