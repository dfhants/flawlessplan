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
