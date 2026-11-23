# Manual Validation Guide

Verify everything yourself by running/debugging. Run commands from `Test_QA_expanded/`. Ports: Greenlee 5000, ENTES 5001, CIRCUTOR 5002. Tick each box.

## 0. Setup
- [ ] `python3 --version` → 3.12 (3.11+ required)
- [ ] `pip install -r requirements-dev.txt` (if your pip index credentials are expired, re-login to it, or install from the public index)
- [ ] `lsof -i :5000-5002` shows no leftover `python` processes (on macOS, `ControlCenter` listening on 5000 is the AirPlay Receiver - expected, see README note)

## 1. Baseline – `python main.py --demo-only`
- [ ] Logs "… is running on port 5000/5001/5002"
- [ ] One reading per ammeter: `[greenlee] Received current measurement from port 5000: X A`, etc.
- [ ] Ranges plausible: Greenlee 0.01–100 A, ENTES 5–200 A, CIRCUTOR ≈ 0.0001–0.1 A
- [ ] Run it twice in a row immediately – no "Address already in use"
- [ ] `python main.py` (no flag) also runs the full test and prints the summary table + ranking

## 2. Protocol checks with netcat (independent of my client)
Terminal 1: `python main.py --keep-running` (Ctrl+C to stop). Terminal 2:
```sh
printf 'MEASURE_GREENLEE -get_measurement' | nc localhost 5000
printf 'MEASURE_ENTES -get_data'           | nc localhost 5001
printf 'MEASURE_CIRCUTOR -get_measurement' | nc localhost 5002
printf 'BAD_COMMAND'                        | nc localhost 5000   # expect: ERROR: unknown command
nc localhost 5001 </dev/null                                      # connect + send nothing; server must survive
```
- [ ] Valid commands return a float; bad command returns an error text (no hang); servers still answer afterwards
- [ ] The old CIRCUTOR command `MEASURE_CIRCUTOR -get_measurement -current` now returns the error (README command is the valid one)
- [ ] Then, still with emulators up: `python run_tests.py --no-emulators --count 5 --frequency 5` works against them

## 3. Framework run – `python run_tests.py --count 20 --frequency 5`
- [ ] Summary table shows `20/20` for each ammeter; exit code `0` (`echo $?`)
- [ ] `results/runs/<run_id>/` contains `result.json`, `samples.csv`, `report.html`, PNGs; `results/results.db`, `results/logs/*.log` exist
- [ ] `samples.csv` has exactly 60 rows (20 per ammeter) + header
- [ ] Timing: total ≈ count / frequency (4 s here); `achieved_frequency_hz` in `result.json` ≈ 5
- [ ] Each sampling mode works: `--count 20 --frequency 5`, `--duration 4 --frequency 5`, `--count 20 --duration 4`
- [ ] Single ammeter: `--ammeters entes`; unknown name → clear error, exit code 2
- [ ] Invalid: `--frequency 0`, `--count 5 --duration 10 --frequency 10` (inconsistent), `--count 10` alone → clear "Configuration error", exit 2, no stack trace

## 4. Statistics cross-check
```sh
python - <<'EOF'
import csv, statistics as s, json, sys
run = sorted(__import__("os").listdir("results/runs"))[-1]
rows = list(csv.DictReader(open(f"results/runs/{run}/samples.csv")))
res = json.load(open(f"results/runs/{run}/result.json"))
for name, info in res["ammeters"].items():
    v = [float(r["value"]) for r in rows if r["ammeter"] == name and r["value"]]
    st = info["stats"]
    print(name, "OK" if abs(st["mean"]-s.mean(v))<1e-9 and abs(st["std"]-s.stdev(v))<1e-9 and st["median"]==s.median(v)
          and st["min"]==min(v) and st["max"]==max(v) else "MISMATCH", s.mean(v), s.stdev(v))
EOF
```
- [ ] Prints `OK` for all three (std is the **sample** std, n-1)
- [ ] `--count 1 --frequency 5` → run finishes, std shown as `-` (undefined), no crash

## 5. Result management
- [ ] Run twice → two different run ids, two folders; `python run_tests.py --list-runs` lists both
- [ ] `python run_tests.py --show <run_id>` reprints the summary table
- [ ] `python run_tests.py --compare <run_a> <run_b>` prints per-ammeter deltas (mean/std/cv/error_rate/latency)
- [ ] `sqlite3 results/results.db "select run_id, ammeter, mean, cv from ammeter_stats"` shows the same numbers as the JSON
- [ ] `sqlite3 results/results.db "select count(*) from samples"` = total number of samples
- [ ] Corrupt one `result.json` (add junk) → `--list-runs` still works, with a warning; `--show` of that run falls back to SQLite

## 6. Error handling & simulation (debug scenarios)
- [ ] `python run_tests.py --no-emulators --count 5 --frequency 5` with nothing running → 100% errors, "AmmeterConnectionError" in `error_types`, exit `1`, no crash
- [ ] Occupy a port (`nc -l 5000`), then `python run_tests.py` → clean "could not listen on port 5000" error, exit `3`
- [ ] `python run_tests.py --simulate-faults --drop-rate 0.3 --garbage-rate 0.1 --seed 1 --count 40 --frequency 20`
  → error rate ≈ 40% per ammeter, status `completed_with_errors`, stats computed from the successful samples only; same seed → same pattern when repeated (different pattern per ammeter)
- [ ] `--simulate-faults --delay-rate 1 --delay-ms 3000` → timeouts (timeout is 2 s in the config)
- [ ] Ctrl+C mid-run (e.g. `--count 200 --frequency 2`) → "Interrupted", partial results saved, `status: interrupted`, ports released (`lsof -i :5001-5002` empty)

## 7. Bonus checks
- [ ] Open `report.html` in a browser: tables, ranking and plots render; the time-series shows red ✗ for failed samples in a faulty run
- [ ] Uninstall/hide matplotlib (`pip uninstall matplotlib`) → run still succeeds, warning "plots skipped"
- [ ] Ranking sanity: with a faulty run, ammeters with lower availability rank lower; compare the CV column by hand
- [ ] Open `results/sample/` – two pre-generated runs (healthy and faulty)

## 8. Debugging tips
- Breakpoints: `Ammeters/base_ammeter.py` (`_handle_client`), `src/testing/sampler.py` (`run_sampling` loop), `src/testing/analysis.py` (`analyze_samples`), `src/testing/test_framework.py` (`run`)
- Verbose logs: `python run_tests.py --log-level DEBUG ...` (per-measurement emulator details, failed-sample reasons)
- Per-run log: `results/logs/<timestamp>_run_<id>.log`
- Port stuck: `lsof -i :5000` then `kill <pid>`

## 9. Automated tests
- [ ] `pytest -q` → 59 passed (about 7 s)
- [ ] Run it 3× in a row to check for flakiness (ports are chosen free per test)
- [ ] `pytest -q tests/test_emulators_and_client.py -k fault` to see only the error-simulation tests

## 10. Deliverables checklist
- [ ] README.md (usage, both entry points), DOCUMENTATION.md (design decisions, bug fixes, libraries)
- [ ] Sample results in `results/sample/`
- [ ] `.gitignore` excludes `__pycache__`, `.idea`, `.venv`, `results/` (except `results/sample/`)
