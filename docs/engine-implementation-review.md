# Engine implementation review

The engine is ready for API integration once the missing test fixture is committed. Tick ordering, shared CPU allocation, memory release, and deterministic tie-breaking match the design. I would keep the separation between simulation, execution models, and placement strategies.

## Findings

1. **High — the golden test fails on a fresh checkout.** The `data/` ignore rule also matches `backend/tests/data/expected_sample_run.jsonl`. The fixture exists locally, but the test raised `FileNotFoundError` against an export of committed `HEAD`. Anchor the runtime ignore rule to the repository root with `/data/`, commit the fixture, and rerun the test from a clean checkout. [Ignore rules](../.gitignore) · [Golden test](../backend/tests/test_validator_and_golden.py)

2. **Medium — synchronous run time grows with workload size.** While a server is busy, the simulator advances one tick at a time and rescans the waiting queue each tick. One request with one million work units on a one-unit CPU took about 0.43 seconds locally to produce three events. Before exposing CSV uploads, define and enforce a workload budget for synchronous runs. If large workloads are a goal, a first optimization is to skip directly to the next arrival or completion when the queue is empty. [Simulation loop](../backend/engine/simulator.py)

3. **Low — the README’s CLI example cannot be pasted into a shell.** The shell interprets the pipe in `[--mode exclusive|shared]`. End the runnable command at `--out /data/run.jsonl` and show optional flags separately. [README CLI example](../README.md#cli)

4. **Low — queue-full drop events are emitted in a different order than documented.** The engine retains the correct oldest requests but emits drops from oldest to newest among the discarded requests. The design specifies newest first. Align the code and documentation, then assert the order in a test that drops two requests in the same tick. The current test drops only one. [Tail-drop implementation](../backend/engine/simulator.py) · [Overload tests](../backend/tests/test_engine_behavior.py)

## Verification scope

All 692 tests passed in the working directory. A trace generated through the CLI passed the original assignment validator. The golden-test failure was reproduced separately against a clean Git export. The review covered the engine and CLI using the local Python environment. The API and frontend were skeletons at review time, and the Docker images were not built during this review.
