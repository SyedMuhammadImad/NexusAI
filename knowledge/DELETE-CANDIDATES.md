# NexusAI V2 — Delete Candidates

**Rule:** this file is a review queue, not authorization to delete.

| Candidate | Why | Preconditions before deletion | Status |
|---|---|---|---|
| Synthetic/random-price legacy backtester path | Produces fictional qualification-style results | Preserve audit evidence; prove no required consumer; replacement path specified | CANDIDATE |
| Legacy adaptive weight mutation | Uses unverified attribution to change trading behavior | Preserve tests/history; confirm no retained consumer | CANDIDATE |
| Symbol-only/latest-same-symbol outcome attribution | Incorrect with concurrent same-symbol trades | Exact-ID replacement verified | CANDIDATE |
| Legacy local-close portfolio logic | Can emit closes without broker confirmation | Broker outcome engine verified; consumer review | CANDIDATE |
| Legacy sentiment influence/orchestration slots | Not part of current V2 target unless re-approved | Dependency search + ADR decision | CANDIDATE |
| Unreachable legacy application startup wiring | Default path deliberately retired | Preserve forensic snapshot; verify no external launcher | CANDIDATE |
| Duplicate stores/services | Multiple DB realities complicate truth | Complete migration/lineage map and rollback plan | REVIEW_ONLY |
| Acceptance classifier as profitability model | Wrong target for profitability | Decide archival/stub role by ADR | REVIEW_ONLY |

## Required Deletion Procedure

1. Verify reachability and external consumers.
2. Preserve evidence/snapshot.
3. Identify data migration and rollback.
4. Obtain explicit human approval.
5. Delete the minimum scope.
6. Run regression + integrity tests.
7. Update `CURRENT-STATE`, architecture and relevant ADR.
