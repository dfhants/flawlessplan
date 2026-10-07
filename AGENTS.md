# Flawlessplan, for agents

The rules for working in this repo are in [CLAUDE.md](CLAUDE.md); read it
first, whichever agent you are. Each house may have its own `CLAUDE.md` and
`context.md` in its folder.

Procedures are in `plugin/skills/`: `read-marks` (what the owner drew on a
page) and `new-house` (starting a house). They are plain Markdown, and ship
with the tools as the Claude Code plugin in `plugin/`.

Without this repo's files, the same engine is available as tools:
`python -m flawlessplan mcp` (see `.mcp.json`).
