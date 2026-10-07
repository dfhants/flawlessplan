---
name: new-house
description: Start a new house from measurements, a sketch, a photo of a plan or a description, and get it drawing without errors. Use when the user wants to add a house, draw a new floor plan, or model a building that is not yet in the workspace.
---

# Starting a house

Call the `guide` tool and follow it. It is the procedure — what to find
out first, the order of work, how to get to no errors — with every key of
a house file and two whole houses to copy from. It is written down there
once, so that an agent with only the tools reads the same thing.

A house is `houses/<name>/house.yaml` in the workspace. Where you have the
folder, write and edit that file directly and run `check` after each
step; `write_house` and `edit_house` do the same for an agent that has no
files, and answer with what `check` finds.
