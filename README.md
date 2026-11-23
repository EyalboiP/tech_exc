# tech_exc – Ammeter Testing Framework

Home assignment: a configuration-driven testing framework for current-measurement systems, built on top of three
ammeter emulators (Greenlee, ENTES, CIRCUTOR). The project lives in [`Test_QA_expanded/`](Test_QA_expanded).

## What it does
- **Unified API** to read any ammeter, with typed errors.
- **Timed sampling** with configurable count, duration and frequency.
- **Analysis:** mean, median, standard deviation, min, max, coefficient of variation, error rate, timing, latency.
- **Result archive:** unique run IDs and metadata, stored as JSON, CSV and SQLite, with list / load / compare.
- **Bonus:** plots and an HTML report per run, error simulation (drops, garbage, delays), and a cross-ammeter reliability ranking.
- **59 pytest tests.**

## Quick start
```sh
cd Test_QA_expanded
pip install -r requirements.txt                 # only PyYAML is required
pip install -r requirements-optional.txt        # matplotlib: needed for the plots in the report (optional)
python main.py                                  # emulators + demo readings + a full test run
python run_tests.py --count 50 --frequency 5    # full CLI (see --help)
pytest -q                                       # run the tests (pip install -r requirements-dev.txt first)
```
Python 3.11+ (developed on 3.12).

## Documentation
| Document | What's in it |
|---|---|
| [Test_QA_expanded/README.md](Test_QA_expanded/README.md) | Full usage, configuration, outputs, project structure |
| [Test_QA_expanded/DOCUMENTATION.md](Test_QA_expanded/DOCUMENTATION.md) | Design decisions, bugs found and fixed, accuracy method, libraries |
| [Test_QA_expanded/docs/DEV_WORK_SUMMARY.md](Test_QA_expanded/docs/DEV_WORK_SUMMARY.md) | Outline of the development work |
| [Test_QA_expanded/docs/DEV_PLAN.md](Test_QA_expanded/docs/DEV_PLAN.md) | Plan and decisions made before coding |
| [Test_QA_expanded/docs/MANUAL_VALIDATION.md](Test_QA_expanded/docs/MANUAL_VALIDATION.md) | Checklist to verify the framework by hand |
| [Test_QA_expanded/results/sample](Test_QA_expanded/results/sample) | Example run output (healthy and with simulated faults) |
| [Test_QA_expanded/Exam](Test_QA_expanded/Exam) | The original assignment specification |
