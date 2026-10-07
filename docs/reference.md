# Flawlessplan reference

The [README](../README.md) is what Flawlessplan is for and how a plan is
made with it. This is the rest: the workspace, the command line, the page,
marks, what is sent and hosted, the tools an agent has, and working on
Flawlessplan itself. Every key of a house file is in
[house-file.md](../flawlessplan/assets/house-file.md).

## The workspace

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

## The page

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

## Marks

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
is how a house is started: the procedure, every key of a house file and the
two examples whole.

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

## Working on flawlessplan itself

```
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # Python 3.10 or later
python3 build.py             # the two examples -> build/
.venv/bin/python -m pytest -q tests
```

Agents working in this repo: read [CLAUDE.md](../CLAUDE.md) first. Procedures
for reading marks and starting a house are skills in `plugin/skills/`.

## Tests

```
.venv/bin/python -m pytest -q tests
```

`tests/test_engine.py` covers the engine on small made-up plans.
`tests/test_houses.py` holds every house to the `expected.json` beside it:
areas, each room as measured, where every opening is and how wide.
`tests/test_mcp.py` drives the agent tools.

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
