@AGENTS.md

# Claude-specific notes

Everything in AGENTS.md applies. These notes only add Claude Code specifics.

## Vault

- Path: `C:\Users\Xody2\OneDrive\Desktop\Vaults\Pulso Vault`. Read and update it by absolute path, following AGENTS.md §5.
- The claude-obsidian transaction writer can't run on native Windows. Write vault notes directly with the Write/Edit tools in UTF-8, following the `claude-obsidian:obsidian-markdown` conventions (frontmatter, `[[wikilinks]]`, callouts, no HTML).

## Owner-approved skills for this project

You don't need to ask before using these. For any other skill or plugin, ask the owner first and say why.

| Work | Skills |
|---|---|
| Planning a phase or task | `superpowers:brainstorming` (before new features or behaviour changes), `superpowers:writing-plans`, `superpowers:executing-plans` |
| Building and fixing | `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion` |
| PRs | `superpowers:requesting-code-review`, `superpowers:receiving-code-review`, `superpowers:finishing-a-development-branch` |
| UI work | `ui-ux-pro-max:ui-ux-pro-max` while designing and building; `styleseed-design-review` before a UI PR is marked ready, and at every phase-end UI checklist |
| Source research (checking a source's current docs and terms before an adapter, per SPEC §4.2) | `firecrawl` (official docs, terms, changelogs), `last30days:last30days` (recent community reports such as blocking or API changes). Record findings in `docs/DATA_SOURCES.md` and the source's vault note |
| Vault notes | `claude-obsidian:obsidian-markdown` conventions |

## Worktrees

Orca creates and manages the worktrees. Don't create extra git worktrees yourself. Never start Beat or live collectors from a worktree (AGENTS.md §4).
