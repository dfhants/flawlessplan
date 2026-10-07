# Starting a house

A house is `houses/<name>/house.yaml` in the workspace, and that file is
all there is to it. Make one with `write_house` (or by writing the file,
where you have the folder), change it with `edit_house`, and read it back
with `read_house`. Every key is under "A house file" below, and two whole
houses follow it: `cottage` (two storeys, plain numbers) and `bungalow`
(an L-plan in named measurements, with parts and a proposal that changes
the as-built).

## Before writing anything, find out

- Which way is north, and which side is the front.
- What was **measured** and what is a guess. Inside room sizes, outside
  faces, wall thicknesses — which of these does the owner actually have?
- Which should win when they disagree: the rooms or the outside figure.
- How many storeys, and where the stair is.
- Whether it is a real home. If so put `private: true` under `house:`, so
  it is never in a public build.

Ask for what is missing rather than inventing it. A plan from a photo is
all guesses until someone tapes a room: mark it so.

**A drawing that is "not to scale" has unreliable distances, not an
invented shape.** Keep what it shows — a wall that splays, a bay, a bow
or any curve (`rise:`), a projection, which range sits in from which side — and take the sizes from
its figures. Do not square a wall off because the walls that meet it are
then easier to write: the envelope takes any points, a wall, stair or
opening meets a slanted wall with `{y: YM, wall: east}`, and a wall drawn
wrong is harder to find later than one that took longer. If you do
simplify, ask first, not afterwards.

Say what you left out. Chimney breasts are `solids`, and are often why a
room reads wider than its figure; cupboards are walls and a room; a roof
over a bay or porch seen from the floor above is an `areas` of style
`below`. Anything on the drawing that is not in the file goes in
`unconfirmed`, by name. An owner who only
wants to see something drawn can be given one: say what you assumed, and
write every such figure as `{value: 2.6, status: assumed}`.

## Order of work

x runs east and y runs south, in metres. Do not write the whole house in
one go: each step below is a `write_house` or an `edit_house`, and each
answers with what `check` finds. A change that is several passages which
do not solve one at a time — a new name in `survey`, the line stepped off
it, the wall on that line; a part taken out and every `use` of it — is one
`edit_house` with `edits: [{old, new}, ...]`, kept or refused whole.

1. **`survey`**: every figure you were given, once, named for what it is
   (`kitchen_w`, not `A`) — every one, the ones no wall is stepped off
   too. Write feet and inches as they are (`sit_d: 14'10"`): do not
   convert them. A figure read off a drawing is `{value: 3.8, status:
   traced}`; a guess is `{value: 2.6, status: assumed}`.
2. **`lines`**: every wall line stepped off the survey. Nothing downstream
   should contain a number that could be one of these names.
3. **One sheet, envelope only.** Outer faces in order — an L is six
   points. Read what comes back, then `crop` with no box and set the whole
   sheet beside the drawing it came from: the same shape, the same way up?
   Do so again for each level.
4. **Walls**, then **rooms** (a name and a point inside). Give every room
   the figures it was quoted — `expect: {w: sit_w, h: sit_d}` — and the
   checks compare them; do not compare by eye. A room that does not read
   its size means the lines are wrong, or something is missing (a chimney
   breast), or the figure measures something else (into a bay). Find out
   which; leave the report standing where you cannot, and tell the owner.
   `report` with `brief` gives every room back measured.
5. **Openings**, by wall and position. Use the leaf names (`cloak`, `std`,
   `wide`). Then **fittings**: what the drawing shows built in — bath,
   WC, basin, shower, worktops, sink, hob — and no furniture.
6. **Stairs**, then the next level, reusing the stair with `ref`.
   **Rooflights** go on the sheet whose ceiling they are in, as
   `rooflights:` — never as an `areas` shape.
7. **Notes**: `unconfirmed` for everything assumed, `about` for what the
   reader needs. Sizes in notes come from names: `{KITCHEN_area:.1f}`.
8. A proposal is another sheet of the same level with `changes:`. Share
   what does not change through `parts` — an envelope too. Do not draw demolition or gained
   floor by hand; mark rooms out with `zones:`, not hand-drawn outlines.

## YAML traps

- A comma inside a flow list splits it: `[XR, op('wide', pair=True)/2]` is
  three items. Give the expression a name in `lines` and use the name.
- Quote any string containing `: `, `{` at the start, or `#`.
- `IW` is the whole partition thickness. Define `HW: IW/2` in `lines` and
  step off that.

## Getting to no errors

- "X and Y are the same space": a wall is missing or stops short.
- "a space ... has no room in it": name it, or split it with a divider.
- "no clear place for the label": `size: small`, `dims: false`, or
  `label: west` to stand it in the margin.
- "ends in the open" is information, not a fault.
- "stands inside one room", "leads from X into itself": two rooms were made
  one and a wall or a door that parted them is still there. Take it out, or
  put back what it met. A nib or a screen with no door is not reported.
  The edit that merged the rooms lists these as `still_standing`.

`crop` a metre or two to check anything small. Whole sheets hide detail.

## When it is right

Before saying a house is done, read `check` once more and repeat every
warning it still has to the owner as it stands. Do not sum up from memory
how well the rooms match: the report is the summary.

`show` gives the owner the address of its pages. Where there is a command
line, `flawlessplan snapshot <name>` writes `expected.json` beside the
house; from then on `check` reports anything that moves from it. If the
house has a story — an owner, decisions, things ruled out — it belongs in
`houses/<name>/context.md`.
