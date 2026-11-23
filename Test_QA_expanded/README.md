# Ammeter Emulators & Testing Framework

Emulators for three ammeter types (Greenlee, ENTES, CIRCUTOR) plus a configuration-driven
framework that samples them, analyses the measurements, archives the results and compares
the ammeters. Design decisions and the bugs fixed in the original code are in
[DOCUMENTATION.md](DOCUMENTATION.md).

## Quick start

```sh
pip install -r requirements.txt            # only PyYAML is required
pip install -r requirements-optional.txt   # optional: matplotlib, for PNG plots
python main.py                             # emulators + demo readings + a full test run
```

Requires Python 3.11+ (developed on 3.12). Works on macOS, Linux and Windows (stdlib sockets/threads only).

## Two ways to run it (both are supported)

| Entry point | Use it for |
|---|---|
| `python main.py` | The simple path from the assignment: starts the 3 emulators, prints one raw reading from each, then runs the whole test framework with `config/config.yaml`. `--demo-only` stops after the raw readings. |
| `python run_tests.py [flags]` | The full CLI: choose ammeters, sampling, fault simulation, and browse/compare archived runs. |

```sh
python run_tests.py                                           # defaults from config/config.yaml
python run_tests.py --ammeters greenlee entes --count 50 --frequency 5
python run_tests.py --duration 10 --frequency 4               # 40 measurements
python run_tests.py --simulate-faults --drop-rate 0.2 --garbage-rate 0.1 --delay-rate 0.1 --delay-ms 100 --seed 1
python run_tests.py --no-emulators                            # test emulators/devices already running
python run_tests.py --list-runs
python run_tests.py --show <run_id>
python run_tests.py --compare <run_id_a> <run_id_b>
python run_tests.py --help
```

Exit codes: `0` all measurements succeeded, `1` run finished with failed measurements, `2` bad configuration / unknown run, `3` runtime problem (e.g. port in use).

## Emulators

| Ammeter | Port | Command | Method |
|---|---|---|---|
| Greenlee | 5000 | `MEASURE_GREENLEE -get_measurement` | Ohm's law, I = V / R (V 1-10 V, R 0.1-100 Ω) |
| ENTES | 5001 | `MEASURE_ENTES -get_data` | Hall effect, I = B · K (B 0.01-0.1 T, K 500-2000) |
| CIRCUTOR | 5002 | `MEASURE_CIRCUTOR -get_measurement` | Rogowski coil, I = ∫V dt (10 samples, V 0.1-1 V, dt 1-10 ms) |

**macOS note:** since macOS Monterey the *AirPlay Receiver* (`ControlCenter`) listens on `*:5000`. The Greenlee emulator binds `localhost:5000` explicitly and
still works, but if you see odd behaviour on port 5000 switch off *System Settings > General > AirDrop & Handoff > AirPlay Receiver* or change the port in the config.

Manual check without any Python code (start emulators with `python main.py --keep-running`): `printf 'MEASURE_ENTES -get_data' | nc localhost 5001`

## Configuration (`config/config.yaml`)

Everything is configuration-driven; CLI flags override the file.

* `testing.sampling` - give at least **two** of `measurements_count`, `total_duration_seconds`,
  `sampling_frequency_hz`; the third is derived (`duration = count / frequency`).
* `testing.start_emulators` - `true`: the framework starts the emulators; `false`: use ones already running.
* `ammeters.<name>` - `port`, `command` (and an optional `faults:` block for per-ammeter error simulation).
* `fault_simulation` - drop / garbage / delay rates for error simulation.
* `analysis` - metrics shown in the summary, conformance threshold, plot types.
* `result_management` - results folder and which formats to save (JSON, CSV, SQLite, HTML report).

## What a run produces

```
results/runs/<run_id>/result.json    metadata (config, host, python, sampling) + statistics + comparison
results/runs/<run_id>/samples.csv    every raw sample (value, timestamp, latency, error)
results/runs/<run_id>/report.html    standalone report: tables + plots (open in a browser)
results/runs/<run_id>/*.png          time series, histogram per ammeter, comparison boxplot
results/results.db                   SQLite: runs, ammeter_stats, samples (query/compare history)
results/logs/<ts>_run_<id>.log       run log
```

Statistics per ammeter: mean, median, standard deviation, min, max (plus variance, quartiles, p95, outliers,
coefficient of variation, error rate, achieved frequency, jitter, latency, and conformance to the theoretical mean).
A pre-generated example is in [`results/sample/`](results/sample) (open `runs/*/report.html`).

## More documentation

* [DOCUMENTATION.md](DOCUMENTATION.md) - design decisions, bug fixes, accuracy method, libraries.
* [docs/DEV_WORK_SUMMARY.md](docs/DEV_WORK_SUMMARY.md) - outline of the development work.
* [docs/DEV_PLAN.md](docs/DEV_PLAN.md) - the plan and decisions made before coding.
* [docs/MANUAL_VALIDATION.md](docs/MANUAL_VALIDATION.md) - checklist to verify the framework by hand.

## Project structure

```
main.py                     emulators + demo + full run
run_tests.py                CLI entry point
config/config.yaml          configuration
Ammeters/                   emulators (base class, 3 ammeters, registry, fault injection, simple client)
src/testing/                ammeter_client, sampler, analysis, comparison, results_store,
                            visualization, report, emulators (lifecycle), test_framework (orchestrator)
src/utils/                  config loading/validation, logger, utils
tests/                      pytest suite
docs/                       development plan, work summary, manual validation checklist
results/sample/             example output
```

## Extending

* **New ammeter type:** subclass `AmmeterEmulatorBase` (command + `measure_current`, optionally
  `expected_statistics`), register it in `Ammeters/registry.py`, add it under `ammeters:` in the config.
* **Real device instead of an emulator:** set `testing.start_emulators: false` and point `port`/`command` at it.
* **New metric/plot:** add it to `analysis.py` / `visualization.py`; results are plain dicts.

## Tests

```sh
pip install -r requirements-dev.txt
pytest -q
```
