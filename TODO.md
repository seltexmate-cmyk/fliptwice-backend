# FlipTwice TODO / Milestones

## Milestones

- [x] Item Status State Machine + Sold Snapshot Freeze
  - Added a domain-only state machine for item status transitions.
  - Integrated transition validation into the item update workflow.
  - Enforced pricing snapshot freeze once an item is Sold (snapshot persists at time of selling; later updates do not recompute pricing while status remains Sold).

## Next

- [ ] Add explicit workflow(s) for moving items off `Sold` (if needed) and define whether snapshot should unfreeze on that transition.
- [ ] Add automated tests for status transitions and Sold snapshot freeze.
- [ ] Add repo-level lint/typecheck configuration (ruff/mypy) and CI checks.
