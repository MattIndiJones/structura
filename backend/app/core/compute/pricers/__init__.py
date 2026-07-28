"""Registry of pricer functions, keyed by the `kind` a ComputeBatch declares.
A pricer is any callable `(payload: dict) -> dict` where both sides are pure,
JSON-plain data — that's what makes it safe to ship across a process
boundary (see core/compute/executor.py) and to persist in
ComputeJob.payload_json / result_json without any custom serialization.

Adding a new job kind (e.g. a client's external product, see external.py)
means adding one entry here — nothing in executor.py or queue_store.py ever
needs to change, same "drop it in, don't touch the core" spirit as adding a
new PayScript product template."""
from .payscript import price_payscript_job
from .var_scenario import price_var_scenario_job
from .scenario_grid import price_scenario_grid_job

PRICERS = {
    "payscript_reprice": price_payscript_job,
    "var_scenario": price_var_scenario_job,
    "scenario_grid": price_scenario_grid_job,
}
