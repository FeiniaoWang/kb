To map all individual skill folders inside .agents/skills/ into .claude/skills/ so they appear side-by-side, use a loop or wildcard command. This ensures both tools can share the same skill directories simultaneously.

```sh
mkdir -p .claude/skills && for dir in .agents/skills/*/; do ln -s "$(pwd)/$dir" ".claude/skills/$(basename "$dir")"; done
```
