# agent-workspaces

Each folder under `workspaces/` is a workspace: the skills, scripts and declared
connections for one kind of work.

A sandbox clones this repo and starts the agent with its cwd set to the
workspace folder. Claude Code discovers skills from `.claude/skills/` in the cwd
**and every parent up to the repo root**, so a workspace gets its own skills plus
the shared ones at the root for free — no `--add-dir` needed.

```
.claude/skills/            shared, load in every workspace
workspaces/
  marketing-automation/
    .claude/skills/        this workspace only
    scripts/
    workspace.yaml
```

Values for the keys in `workspace.yaml`'s `env:` list are held by the platform and
injected at spin-up. Never commit a secret here.
