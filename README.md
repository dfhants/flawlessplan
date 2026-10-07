# Flawlessplan

Floor plans you make and change by talking to Claude.

Give Claude a sketch, a photo of a plan or the measurements you took
yourself, and it draws the house to scale, a sheet for every floor. The
plan opens as a page beside the conversation. Say what should change, or
draw on the plan — a wall out, a door moved, an extension on — and it is
redrawn while you are still talking about it.

<https://flawlessplan.app> has the installer and two example houses to look at.

## Why

Getting a design right is mostly the early going round: try it, look at
it, change it, show someone, change it again. Floor plan programs make
each of those turns slow. They have to be learned, every wall and door is
placed by hand, and a change someone asks for across the table becomes
something you go away and do.

Flawlessplan is for doing it live. You are with a client, a partner or a
builder, the plan is on the screen, and they say "what if this wall came
out?" You say so, or ring the wall on the page, and a minute later you are
both looking at it: drawn to scale, every room measured again, the old
layout still on its own tab to compare.

## Who it is for

- **Anyone planning work on their own home**: try an extension or a new
  layout, and send the proposal to family, a builder or an architect.
- **Architects and designers** at the first-ideas stage: sketch options
  with a client in the room instead of after the meeting.
- **Builders and anyone else in construction** who needs a floor plan
  quickly, to talk over or to price from.

It is for the stage where a design is still being decided. The plans are
to scale and the room sizes are measured from the drawing, but they are
not construction drawings: once the layout is agreed, the drawings a
builder works from are still made the usual way.

## How it goes

**1. Start a house.** Tell Claude what you have: a photo of an estate
agent's plan, a sketch on paper, a list of room sizes, or just a
description. It asks for what is missing — which way is north, what was
really measured — and draws a first plan. Anything it had to guess it
marks as a guess, so you know what to take a tape to.

**2. Look at it.** Ask Claude to show the house and its page opens beside
the conversation: every floor on its own tab, to scale, each room with its
size and area, notes beside the sheet. Zoom and pan it like a map.

**3. Change it.** Either way works, and they mix:

- *Say it.* "The WC is smaller." "Bedroom 2 should be 4.15." "Take the
  wall out between the kitchen and the dining room."
- *Draw it.* Scribble and write on the plan — ring a wall, arrow a door to
  where it should be, sketch the outline of an extension — then say "I've
  marked it up". Claude reads what you drew, says back what it takes each
  mark to mean, and makes the change.

The page redraws itself after every change, on the sheet you were looking
at.

**4. Try a proposal.** An extension or a new layout is another tab, drawn
against the house as it is: the walls that come out are dashed red, the
floor gained is tinted and its area worked out. Keep several options side
by side, hide the ones that lost, and reorder the tabs by dragging them.

**5. Show someone.** The Share button gives one file with every sheet and
its notes. Mail it or drop it on a phone; it opens anywhere, needs no
account and nothing installed, and turns from sheet to sheet like slides.

## Install

Flawlessplan is made to be used with Claude. Your houses stay in a folder
on your own machine; nothing is uploaded.

### Claude Code

```
claude plugin marketplace add dfhants/flawlessplan
claude plugin install flawlessplan@flawlessplan
```

Open Claude Code in any folder and ask it to "set up a workspace here",
then "show my houses". You get two example houses to try things on. The
plugin is the tools plus two skills: starting a house, and reading what you
drew on one. Needs [uv](https://docs.astral.sh/uv/).

### Claude desktop app

Download `flawlessplan.mcpb` from <https://flawlessplan.app> and open it.
It asks for a folder to keep your houses in, puts the two examples in an
empty one, and adds the tools. Then ask Claude to "show my houses".

### On its own, from a terminal

```
uv tool install git+https://github.com/dfhants/flawlessplan@v0.8.1
flawlessplan init my-houses         # a workspace, with two example houses
cd my-houses
flawlessplan build --serve          # draw them and open http://localhost:8765
```

Needs [uv](https://docs.astral.sh/uv/) (or pipx) and Python 3.10 or later,
and nothing else. No Claude is required this way: a house is a plain text
file and can be written by hand.

## What is in a plan

Outside walls and partitions at their real thicknesses, straight, slanted
or curved; doors with their swings, windows, folding and sliding doors and
open archways; stairs with landings and winders, carried from one floor to
the next; what is built in — baths, showers, WCs, basins, kitchen worktops,
sinks, hobs, boilers, fitted wardrobes; rooflights; split levels; and any
number of floors and proposals. Every room is labelled with its size and
area, measured from the drawing. Lengths can be given in metres or in feet
and inches.

## Why the plans stay right

Changing a plan quickly is only useful if it is still right afterwards.
Behind each house is one text file, which Claude writes for you, and three
things about it keep the drawing honest:

- **A dimension is written down once.** Correct "the kitchen is 4.15, not
  4.10" and every wall, door and sheet that depends on it follows.
- **Room sizes are measured, never typed.** What a label says is what the
  drawing is.
- **It checks itself.** A door that runs off its wall, two rooms that are
  really one because a wall stops short, a room that does not come out at
  the size you were quoted: each is reported, to Claude and to you, and not
  quietly drawn wrong.

## What it does not do

- Construction or planning drawings: no sections, elevations, structure or
  services.
- Furniture, and 3D.
- Curved stairs and curved door leaves.
- Read a picture by itself. Claude reads your photo or sketch and writes
  the house from it; a plan taken from a photo is a set of good guesses
  until someone measures a room.

## More

- [docs/reference.md](docs/reference.md): the command line, everything the
  page does, marks, sharing and hosting, the tools an agent has, and
  working on Flawlessplan itself.
- [A house file](flawlessplan/assets/house-file.md): every key of the file
  behind a house, for writing or reading one by hand.
- [flawlessplan/examples/](flawlessplan/examples/): the two example houses.
- [CLAUDE.md](CLAUDE.md): for agents working in this repository.

## Licence

Free for any noncommercial use, such as drawing your own house, under the
[PolyForm Noncommercial License 1.0.0](LICENSE). The source is here to read
and change, and it is not open source: using it in or for a business needs a
commercial licence: [ask for one](https://flawlessplan.app/#licence).
