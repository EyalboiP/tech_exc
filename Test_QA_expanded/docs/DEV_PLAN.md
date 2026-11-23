# Dev Plan – Ammeter Testing Framework

> Edit freely. I will not start coding until you tell me to. Answer the **Q&A** section first (mark your choice with `[x]` or write under **Answer:**). Anything unanswered I will NOT guess – I'll stop and ask.

## 1. What I found in the existing code (bugs / gaps)

| # | Where | Problem | Proposed fix |
|---|-------|---------|--------------|
| B1 | `main.py` vs README/config | Ports mismatch: main uses 5001/5002/5003, README + config say 5000/5001/5002 | Align (see Q1) |
| B2 | `main.py` | Client calls are commented out and send `b'MEASURE_GREENLEE'`, but servers expect the full command (`MEASURE_GREENLEE -get_measurement`, etc.) → server silently ignores | Send the exact command; uncomment calls |
| B3 | `Circutor_Ammeter.py` | Command is `MEASURE_CIRCUTOR -get_measurement -current`, README says `MEASURE_CIRCUTOR -get_measurement` | Align to README (see Q2) |
| B4 | `base_ammeter.py` | Unknown command → connection closed with no reply; client `recv` gets empty. Also single-recv, one client at a time, no socket `SO_REUSEADDR` (restart problems mentioned in main.py comment) | Reply with an error string, set `SO_REUSEADDR`, handle exceptions per-connection |
| B5 | `Circutor_Ammeter.py` | "Integral" is `sum(v*dt)` – OK, kept as is | none |
| B6 | `src/testing/test_framework.py` | Missing `from typing import Dict`; `run_test` is a stub; relative import `..utils` breaks when run from root | Rewrite the module |
| B7 | `src/utils/logger.py` | Logger created but never gets a handler / level; `log_file` unused | Add file + console handlers |
| B8 | `examples/run_tests.py` | README says "don't use it"; calls `run_test()` without args | Leave untouched (see Q6) |
| B9 | `config/config.yaml` | Mostly NULL/empty; ammeters commented out | Fill in |
| B10 | README | References `Ammeters/main.py` and `AmmeterTester.py` which don't exist | Rewrite README |
| B11 | `requirements.txt` | Heavy (scipy, seaborn, pandas…) vs spec "minimize dependencies" | Trim (see Q3) |
| B12 | repo | `__pycache__` / `.idea` committed-ish | Add `.gitignore` |

## 2. Target architecture

```
Test_QA_expanded/
├─ main.py                    # starts emulators, runs a quick demo request for each
├─ run_tests.py (or CLI)      # entry point for the test framework (see Q5)
├─ config/config.yaml         # ports, commands, sampling, analysis, results settings
├─ Ammeters/                  # emulators (bug-fixed)
├─ src/
│  ├─ utils/{config,logger,Utils}.py
│  ├─ testing/
│  │   ├─ test_framework.py   # AmmeterTestFramework: orchestrates run
│  │   ├─ ammeter_client.py   # unified client: connect/send/parse, retries, timeouts
│  │   ├─ sampler.py          # timed sampling (count / duration / frequency)
│  │   ├─ analysis.py         # mean, median, std, min, max, (+ consistency/CV)
│  │   ├─ results_store.py    # run IDs, metadata, JSON archive, load/compare
│  │   ├─ comparison.py       # (bonus) cross-ammeter accuracy / reliability
│  │   └─ visualization.py    # (bonus) plots
├─ tests/                     # pytest unit + integration tests for the framework
├─ results/                   # runs/<run_id>/{result.json, samples.csv, plot.png}, logs/
└─ DOCUMENTATION.md           # design decisions, fixes, libs installed, sample results
```

## 3. Steps

1. **Fix emulators & main.py** (B1–B4): make `python main.py` print one reading per ammeter.
2. **Unified client API**: `AmmeterClient(name, port, command)` → `read() -> float`; timeouts, retries, clear exceptions (`AmmeterConnectionError`, `AmmeterProtocolError`).
3. **Config-driven setup**: fill `config.yaml`; loader with validation + defaults + CLI overrides.
4. **Sampler**: supports any 2 of {count, duration, frequency} (third derived), precise timing using `time.perf_counter` with drift compensation; records per-sample timestamp and latency; records failed samples instead of crashing.
5. **Analysis**: mean, median, std (sample), min, max, plus count, error rate, CV (consistency), achieved vs requested frequency.
6. **Result management**: unique run id (timestamp + short uuid), metadata (config, ammeter, host, python version, start/end), JSON + CSV storage, `list_runs()`, `load_run()`, `compare_runs()`.
7. **Error handling & simulation (bonus)**: configurable fault injection in emulators (drop connection, delay, garbage reply) enabled via config/flag; tests prove the framework handles them.
8. **Visualization (bonus)**: time-series + histogram per ammeter, overlay comparison (matplotlib, optional dependency – skipped gracefully if missing).
9. **Accuracy assessment (bonus)**: compare ammeters (mean/std/CV, pairwise agreement, rank by lowest CV). Note: emulators generate *independent random* values, so there's no ground truth – see Q4.
10. **Tests** with pytest (spin up emulators on test ports, check stats against known data, config validation, store round-trip).
11. **Docs**: README (usage), DOCUMENTATION.md (design decisions, bug fixes explained, libraries installed), sample results committed under `results/sample/`.

## 4. Q&A – decisions I need from you

**Q1. Ports – which is the source of truth?**
- [x] A) README/config: Greenlee 5000, ENTES 5001, CIRCUTOR 5002
- [ ] B) main.py: Greenlee 5001, ENTES 5002, CIRCUTOR 5003
- [ ] C) Other: ___
**Answer:**

**Q2. CIRCUTOR command – keep `…-get_measurement -current` (code) or change to `…-get_measurement` (README)?**
- [x] A) README version (change the emulator)
- [ ] B) Code version (change README/config)
**Answer:**

**Q3. Dependencies – spec says minimize.**
- [x] A) Only `pyyaml` required; `matplotlib` optional for plots; stdlib `statistics` for math; `pytest` for tests (dev only)
- [ ] B) Keep everything in requirements.txt (numpy, scipy, pandas, seaborn, matplotlib, pyyaml)
- [ ] C) Other: ___
**Answer:**

**Q4. Scope of bonus items (pick all you want implemented):**
- [x] Visualization
- [x] Error simulation (fault injection)
- [x] Cross-ammeter accuracy comparison
- [x] Performance consistency evaluation
- [x] Config-driven approach (I'd do this regardless, it's the core of the framework)
**Answer:**

**Q4b. Accuracy has no ground truth (each emulator returns independent random values in a different range). Which "accuracy" definition do you want?**
- [ ] A) Relative: compare mean/spread across ammeters, rank by coefficient of variation (lowest = most "reliable")
- [ ] B) Also compare against a theoretical expected mean per emulator (computed from the documented ranges)
- [x] C) Other: pick the approach best suited to this exercise (there is no ground truth)
**Answer:** *(recommended approach, implemented)* A hybrid of A and B: rank by availability, then conformance of the observed mean to the theoretical mean derived from each emulator's documented ranges (z-score), then coefficient of variation. Reason: the emulators produce independent random values, so there is no ground truth; this uses only what can be measured and detects an ammeter deviating from its own spec. Details in DOCUMENTATION.md section 4. 

**Q5. Entry point style?**
- [ ] A) CLI: `python run_tests.py --config config/config.yaml --ammeters all --count 50 --frequency 5`
- [ ] B) Just `python main.py` does everything (start emulators + run tests)
- [x] C) Both but make it clear that both can be used in the docs for this exercise
**Answer:**

**Q6. `examples/run_tests.py` is labeled "don't use it" in README. Leave untouched, or delete?**
- [ ] Leave  - [x] Delete
**Answer:**

**Q7. Emulators: keep them in-process threads started by `main.py`/framework (simplest), or also allow connecting to already-running external emulators?**
- [ ] A) Threads only  - [x] B) Both (config flag `start_emulators: true/false`)
**Answer:**

**Q8. Result storage format?**
- [ ] A) JSON per run + CSV of raw samples (no extra deps)
- [ ] B) SQLite (stdlib) for easy querying/comparison
- [x] C) Both
**Answer:**

**Q9. Testing framework for my own tests?**
- [x] pytest  - [ ] unittest (stdlib only)
**Answer:**

**Q10. Python version / OS you will run on?** (the repo has pycache for 3.10–3.12)
3.12
**Answer:**

**Q11. Language of docs/comments (existing comments contain Hebrew)?**
- [ ] English  - [ ] Hebrew  - [x] English, translate existing Hebrew comments
**Answer:**

**Q12. Commit to git when done? (branch `eyal_dev`) I will not commit unless you say so.**
Not right now, I'll handle git
**Answer:**

**Q13. Anything else (extra requirement, deadline, things I must not touch)?**
Would Allure reports for each run fit this exercise?
**Answer:** *(recommendation)* Not included: it needs allure-pytest plus the Allure CLI (Java), which conflicts with the spec's "minimize dependencies / cross-platform", and it targets pass/fail test cases rather than measurement statistics. Each run gets a self-contained `report.html` instead. Allure can be added later without code changes (`pytest --alluredir=...`).
