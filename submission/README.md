# ARGUS Submission Package

## Included

- `cases/HHG-001.json` … `HHG-020.json`: one answer file per benchmark case.
- `benchmark_summary.csv`: compact review table for all 20 cases.
- `DEMO_SCRIPT.md`: 3–5 minute end-to-end demo plan.
- `TECHNICAL_BLOG.md`: technical write-up covering architecture, TigerGraph, agent capabilities and lessons.
- `SOCIAL_POST.md`: submission social post draft.

## Answer-file structure

Every JSON contains:

1. case + verdict/pattern/exposure;
2. affected transaction IDs;
3. connected card/device references;
4. evidence with source and entity references;
5. similar prior cases;
6. initial next-best actions;
7. evidence requests and simulated responses;
8. final next-best actions after evidence;
9. SAR decision and narrative;
10. stop condition / investigation completion reason.

The simulated evidence responses are explicitly labeled as assumptions because the benchmark does not provide live customer/analyst responses.
