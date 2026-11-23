# Development Work Summary

A short, chronological outline of how this assignment was approached and built. The code was written with AI assistance (permitted by the assignment); the plan, decisions and review were mine.

## 1. Approach
1. Read the spec, README and all provided code before changing anything.
2. Wrote a dev plan ([DEV_PLAN.md](DEV_PLAN.md)) listing the bugs found, the target architecture, the steps, and a Q&A section for every open decision. I answered the questions before any code was written, so nothing was guessed.
3. Wrote a manual validation checklist ([MANUAL_VALIDATION.md](MANUAL_VALIDATION.md)) so I can verify the result by running and debugging it myself.
4. Implemented step by step, testing each layer, then wrote the docs.

## 2. Decisions I made (from the Q&A)
| Topic | Decision |
|---|---|
| Ports | README/config ports (5000, 5001, 5002) |
| CIRCUTOR command | README version (`MEASURE_CIRCUTOR -get_measurement`) |
| Dependencies | Only `pyyaml` required; `matplotlib` optional; `pytest` for dev |
| Bonus items | All: visualization, error simulation, accuracy comparison, consistency evaluation, config-driven |
| Entry points | Both `main.py` and a CLI (`run_tests.py`) |
| Emulators | Started by the framework, or external (`start_emulators` flag) |
| Storage | JSON + CSV per run, plus SQLite |
| Tests | pytest |
| Provided `examples/run_tests.py` | Deleted (README said not to use it) |
| Allure | Not included (heavy dependency, wrong fit); HTML report instead |
| Accuracy definition | No ground truth exists, so: availability, then conformance to the expected mean, then coefficient of variation |

## 3. Work done
**Fixes to the provided code** (details in [DOCUMENTATION.md](../DOCUMENTATION.md))
- Port and command mismatches between `main.py`, the emulators and the README.
- Server ignored bad commands silently, could not restart cleanly, and handled one client at a time.
- Broken `test_framework.py` (missing import, stub) and a logger with no handlers.

**New framework** (`src/testing/`)
- Unified client with typed errors
- Timed sampler (count / duration / frequency, drift-free)
- Statistical analysis
- Cross-ammeter reliability ranking
- Result store (JSON, CSV, SQLite) with list / load / compare
- Fault injection (drop, garbage, delay)
- Plots and an HTML report
- Config loading and validation

**Entry points:** `main.py` (simple path) and `run_tests.py` (full CLI).

**Tests:** 59 pytest tests (sampling, statistics, protocol, faults, config, storage, end-to-end, CLI).

**Docs:** README (usage), DOCUMENTATION (design and fixes), sample results in `results/sample/`.

## 4. How I verified it
- Automated: `pytest -q` (59 passing, repeated for flakiness).
- Manual: followed the validation checklist, including netcat protocol checks, a statistics cross-check against the raw CSV, SQLite queries, port-in-use handling, Ctrl+C mid-run, and fault-simulation runs.

## 5. Known limitations
- No ground truth in the emulators, so "reliability" is relative, not true accuracy.
- Timing precision is limited by the OS scheduler.
- One TCP connection per measurement, as the emulator protocol dictates.
