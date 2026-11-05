---
name: crisp-dm-checkpoint
description: Append a dated entry to docs/crisp-dm-log.md summarising what was done, why, the resulting numbers, and the next step, tagged with the CRISP-DM phase. Use at the end of every meaningful task.
---

# CRISP-DM checkpoint

1. Identify the phase: 1 Business Understanding, 2 Data Understanding, 3 Data Preparation,
   4 Modeling, 5 Evaluation, 6 Deployment. If the work went *back* to an earlier phase
   (e.g. eval showed a data problem), say so explicitly: "5 → 3: ...". These loops are what the report
   should show.
2. Append to `docs/crisp-dm-log.md` (never rewrite older entries):

```
## YYYY-MM-DD — <Phase> — <short title>
- What: <files/components changed>
- Why: <problem or requirement that triggered it>
- Result / numbers: <metrics before → after, or "n/a">
- Next: <one concrete next step>
```

3. Keep it short (≤ 8 lines). Use real numbers from `results/`, never estimates.
4. If the phase's document (`docs/0N_*.md`) is now outdated, update it too.
