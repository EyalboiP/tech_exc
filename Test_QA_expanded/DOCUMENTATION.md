# Design Documentation

## 1. Libraries

| Library | Needed for | Notes |
|---|---|---|
| `pyyaml` 6.0.2 | reading `config.yaml` | **only required third-party dependency** |
| `matplotlib` 3.x | PNG plots | optional - the run works and logs a warning if missing |
| `pytest` | tests | dev only |

I did not install anything new: PyYAML, matplotlib and pytest were already available in the Python 3.12.6 used.
The original `requirements.txt` listed numpy, scipy, pandas and seaborn; none are needed (statistics use the stdlib
`statistics` module), in line with the "minimize external dependencies" constraint, so they were removed.

## 2. Bugs found in the provided code and how they were fixed

| # | Problem | Fix |
|---|---|---|
| 1 | `main.py` used ports 5001-5003 while README/config say 5000-5002. | Ports follow README/config (5000/5001/5002); the config is the single source of truth. |
| 2 | The commented-out client calls sent `b'MEASURE_GREENLEE'`, but the server compares the received bytes with the *full* command (`MEASURE_GREENLEE -get_measurement`); the mismatch made the server silently send nothing. | Commands are taken from the config (full commands, as in the README); the server also tolerates trailing whitespace/newlines (e.g. `nc`). |
| 3 | CIRCUTOR emulator expected `... -get_measurement -current`, README says `... -get_measurement`. | Emulator aligned with the README. |
| 4 | An unknown command closed the connection with no reply, so the client saw an empty response and could hang/crash. | Server replies `ERROR: unknown command`; the client turns it into a clear `AmmeterProtocolError`. |
| 5 | "Address already in use" when restarting (`main.py` even suggested increasing `sleep`). | `SO_REUSEADDR` on the server socket, and the fixed `time.sleep(5)` was replaced by waiting until each emulator signals it is listening. |
| 6 | Server handled one client at a time with a single `recv`; a stuck client blocked everyone; the server loop could never be stopped. | One thread per connection, socket timeouts, exceptions per connection never kill the server, `stop()` support (needed for tests and clean shutdown). |
| 7 | `test_framework.py` lacked `from typing import Dict` (NameError) and `run_test` was a stub; it imported with `..utils` which only works as a package. | Rewritten; packages got `__init__.py`. |
| 8 | `logger.py` created a logger without handlers/level and never used the log file path. | Real file (+ optional console) handlers, level from config. |
| 9 | `config.yaml` was mostly empty; README referenced non-existing files (`Ammeters/main.py`, `AmmeterTester.py`). | Config completed and validated; README rewritten. `examples/run_tests.py` (labelled "don't use it", with an invalid call) was deleted. |
| 10 | Emulators `print` every measurement. | Switched to `logging` (DEBUG for per-measurement detail) so hundreds of samples do not flood the console. |

## 3. Architecture and design decisions

```
config.yaml ──► AmmeterTestFramework ──► EmulatorManager (optional) ──► Emulators (threads)
                      │
                      ├─ AmmeterClient  (unified API: read() -> float | AmmeterError)
                      ├─ sampler        (timed sampling, one thread per ammeter)
                      ├─ analysis       (statistics, timing, conformance)
                      ├─ comparison     (reliability ranking)
                      ├─ ResultStore    (JSON + CSV + SQLite)
                      └─ visualization / report (PNG + HTML)
```

* **Unified measurement API.** `AmmeterClient(name, port, command).read()` is the single way to talk to any ammeter.
  Failures are typed (`AmmeterConnectionError`, `AmmeterProtocolError`), so callers never parse socket errors.
* **Config-driven and extensible.** Ammeters, ports, commands, sampling, faults, analysis and storage are all in YAML,
  with defaults + validation (clear `ConfigError` messages). A new ammeter = one class + registry line + config entry.
  Emulators can be started by the framework or external (`start_emulators: false`).
* **Sampling.** Any two of count / duration / frequency (the third is derived). Sample *i* is scheduled at an
  absolute time `start + i/frequency`, so slow reads do not accumulate drift; the achieved frequency and jitter are
  measured and reported. All ammeters are sampled concurrently so they observe the same time window. A failed
  measurement is recorded (value `None` + error) rather than aborting the run; Ctrl+C stops cleanly and saves partial
  results (`status: interrupted`).
* **Statistics.** Mean, median, sample standard deviation (n-1), min, max, plus variance, quartiles, p95, IQR outliers,
  coefficient of variation, error rate, latency, jitter. Undefined values (e.g. std of one sample) are `None`, never a crash.
* **Result management.** Each run has a unique sortable id (`YYYYmmdd_HHMMSS_<6 hex>`), metadata (config snapshot, host,
  platform, Python, sampling plan), `result.json`, `samples.csv`, and rows in a SQLite database for querying across runs.
  `list_runs()`, `load_run()` and `compare_runs()` give easy retrieval/comparison; corrupt files are skipped with a warning
  and loading falls back from JSON to SQLite.
* **Error simulation (bonus).** The emulators can drop the connection, answer garbage, or delay replies, with
  configurable probabilities and a seed for reproducibility (`fault_simulation`, or per ammeter). Different ammeters get
  different (still reproducible) sequences.

## 4. Accuracy / reliability assessment (bonus)

The emulators return independent random numbers from different physical models, so there is **no ground truth** to
compare against and a naive "which ammeter is closest to the true value" is meaningless. The assessment therefore uses
three measurable criteria (see `src/testing/comparison.py`):

1. **Availability** - share of measurements that succeeded.
2. **Conformance** - each emulator's documented ranges define a theoretical mean and standard deviation
   (derived analytically in each emulator class, and verified against 40,000 simulated readings in the tests).
   The observed mean is compared with it via a z-score `z = (mean - μ) / (σ / √n)`; `|z| ≤ 4` means "conforms".
   This detects an ammeter whose output is biased relative to its own specification. (4 rather than 3 because
   Greenlee's I = V/R distribution is heavily skewed, so small samples would otherwise raise false alarms.)
3. **Precision / consistency** - the coefficient of variation (std / mean) is unit-free, so ammeters with currents
   of 0.03 A and 60 A are comparable. Labels: `stable` < 0.25, `moderate` < 0.75, otherwise `variable`.

Ranking: availability first, then conforming before non-conforming, then lowest CV. It is a heuristic ranking, and the
CV of these emulators mostly reflects how widely their inputs are randomised, not a defect; so with healthy emulators
the ranking is stable only in broad terms (Greenlee is consistently the most variable because 1/R spans three decades).
Under fault simulation the availability criterion dominates.

## 5. Allure reports - why not included

Allure would need `allure-pytest` plus the Allure command-line tool (Java) to render, which conflicts with "minimize
external dependencies" and "cross-platform". It is also aimed at *test-case* pass/fail reporting, whereas this
framework's output is measurement statistics. Instead each run produces a self-contained `report.html` with tables
and plots (stdlib only). If Allure is wanted later, the pytest suite can emit it without code changes:
`pytest --alluredir=allure-results` (after installing `allure-pytest`).

## 6. Testing

`pytest` suite (59 tests) covering: sampling modes and validation, drift-free scheduling (with a fake clock), failure
recording, interruption, statistics on known data and edge cases (1 sample, empty, constant data, zero mean), analytic
vs simulated emulator statistics, ranking logic, emulator protocol (valid / unknown command / idle client / restart /
port in use), every fault type and retries, config validation, storage round-trips (JSON, CSV, SQLite, fallback,
corrupt file), full end-to-end runs and the CLI.

## 7. Known limitations

* Timing uses `time.sleep`/`Event.wait`, so precision is OS-scheduler limited (about 1 ms); very high frequencies may fall
  behind schedule when a read takes longer than the sampling interval - this is visible in `achieved_frequency_hz`.
* One TCP connection per measurement (as the emulators' protocol dictates).
* Sample results in `results/sample/` come from a single machine and random data; numbers vary run to run.
