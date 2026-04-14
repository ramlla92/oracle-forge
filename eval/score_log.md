# Score Log — Oracle Forge

## Score Progression

| Run | Date | Queries | pass@1 | Notes |
|-----|------|---------|--------|-------|
| Baseline | — | — | — | Pending first end-to-end run (Day 5) |

---

## How to update this log

After each eval run, add a row:
```
python eval/run_benchmark.py --agent agent.agent_core --trials 5 --output results/team_results.json
python eval/score.py --results results/team_results.json
```

Then add a row to the table above with the date, query count, pass@1, and a one-line note on what changed.
| 20260411_142058 | yelp | 0/7 | 0% | pass@1 | — |
| 20260411_142724 | yelp | 0/7 | 0% | pass@1 | — |
| 20260411_143810 | yelp | 1/7 | 14% | pass@1 | — |
| 20260411_144040 | yelp | 0/7 | 0% | pass@1 | — |
| 20260411_144221 | yelp | 0/7 | 0% | pass@1 | — |
| 20260413_142407 | yelp | 0/7 | 0% | pass@1 | — |
| 20260413_204424 | yelp | 0/7 | 0% | pass@1 | — |
| 20260413_205007 | yelp | 0/7 | 0% | pass@1 | — |
| 20260414_044753 | yelp | 1/7 | 14% | pass@1 | — |
| 20260414_121131 | yelp | 0/7 | 0% | pass@1 | — |
| 20260414_121741 | yelp | 0/7 | 0% | pass@1 | — |
| 20260414_122656 | yelp | 0/7 | 0% | pass@1 | — |
| 20260414_123006 | yelp | 1/7 | 14% | pass@1 | — |
| 20260414_123714 | yelp | 1/7 | 14% | pass@1 | — |
| 20260414_125716 | yelp | 1/7 | 14% | pass@3 | — |
| 20260414_153138 | yelp | 1/7 | 14% | pass@3 | — |
| 20260414_155651 | yelp | 4/7 | 57% | pass@3 | — |
| 20260414_173700 | yelp | 4/7 | 57% | pass@1 | — |
| 20260414_174530 | yelp | 4/7 | 57% | pass@1 | — |
| 20260414_175755 | yelp | 5/7 | 71% | pass@1 | — |
