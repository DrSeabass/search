# Document‑DB–Only Experiment Runner — Specification v1.2

**Audience:** Agentic coding systems (e.g., Cline, Cursor, GitHub Copilot Agents) and research engineers  
**Goal:** Execute solver runs over enumerated instances, and persist **all** experimental data (metadata, metrics, compressed stdout/stderr) exclusively in a **document store** with strict schemas, deterministic execution, and **no plaintext artifacts on disk**.

## 0) Scope, Assumptions, Non‑Goals

*   **Runtime:** Python 3.10+; **single process**; local Linux‑like host.
*   **Scale target:** up to \~1e6 runs/year (across many invocations).
*   **Storage:** All stdout/stderr stored in DB (inline zstd‑compressed by default; overflow to GridFS or an external collection).
*   **Validation:** Strict DB schema + strict app‑level (Pydantic) schema per algorithm family.
*   **Statuses:** Terminal only → `ok`, `timeout`, `oom`, `error`.
*   **Non‑Goals:** dashboards, distributed queueing, completeness orchestration. 

## 1) Filesystem Instance Hierarchy

**Directory form:**

    /…/instances/
      <domain>/
        key_file           # contains: key=<name>
        <key_value>/
          key_file
          ...
            key_file       # contains: key=instance (terminal level)
            <instance files>...

**Contract:**

*   Each directory contains a file named `key_file` with content `key=<name>`.
*   Non‑terminal levels: each subdirectory name is a key value; directories map to `params[key] = parse(value)` where `parse` tries `int`, then `float`, else `str`.
*   **Terminal level:** `key=instance`; each file directly under this directory represents an instance; the filename (without extension) is `instance.id`.
*   **Instance params:** accumulated key/value bindings from root→leaf; **enumeration order is deterministic** (lexicographic).
*   Malformed or missing `key_file` causes that subtree to be skipped with a structured warning.

**Enumeration pseudocode:**

```python
from pathlib import Path

def parse_value(name: str):
    try:
        return int(name)
    except ValueError:
        try:
            return float(name)
        except ValueError:
            return name

def enumerate_instances(domain_root: str) -> list[dict]:
    def walk(dir_path: Path, accum_params):
        key_txt = (dir_path / "key_file").read_text().strip()
        assert key_txt.startswith("key=")
        key = key_txt.split("=", 1)[1]

        if key == "instance":
            for f in sorted(p for p in dir_path.iterdir() if p.is_file()):
                yield {"id": f.stem, "params": dict(accum_params)}
            return

        for sub in sorted(p for p in dir_path.iterdir() if p.is_dir()):
            val = parse_value(sub.name)
            yield from walk(sub, accum_params + [(key, val)])

    return list(walk(Path(domain_root), []))
```


## 2) Experiment Specification (Input)

The experiment spec defines: **domains**, **instances** (by filesystem root + optional selectors), **algorithms** (with `schema_id` and parameter grids), **seeds**, **resources** (timeouts & memory), and a **binary\_version** identifier.
### Canonical JSON Schema (ExperimentSpecV1)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ExperimentSpecV1",
  "type": "object",
  "required": ["name", "domains", "instances", "algorithms", "seeds", "resources", "binary_version"],
  "properties": {
    "name": { "type": "string", "minLength": 1 },
    "domains": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["name", "params"],
        "properties": {
          "name": { "type": "string" },
          "params": { "type": "object" }
        },
        "additionalProperties": false
      }
    },
    "instances": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": ["root"],
        "properties": {
          "root": { "type": "string" },
          "selector": { "type": "object" }
        },
        "additionalProperties": false
      }
    },
    "algorithms": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["name", "schema_id", "params"],
        "properties": {
          "name": { "type": "string" },
          "schema_id": { "type": "string" },
          "params": { "type": "object" }
        },
        "additionalProperties": false
      }
    },
    "seeds": {
      "type": "array",
      "minItems": 1,
      "items": { "type": "integer", "minimum": 0 }
    },
    "resources": {
      "type": "object",
      "required": ["timeout_sec", "memory_mb"],
      "properties": {
        "timeout_sec": { "type": "integer", "minimum": 1 },
        "memory_mb": { "type": "integer", "minimum": 64 }
      },
      "additionalProperties": false
    },
    "binary_version": { "type": "string" }
  },
  "additionalProperties": false
}
```

**Example:**

```json
{
  "name": "tiles_astar_width_sweep",
  "domains": [
    { "name": "tiles", "params": { "width": [4, 6, 200], "height": [4] } }
  ],
  "instances": {
    "tiles": {
      "root": "/home/user/research/instances/tiles",
      "selector": { "width__in": [4, 6, 200] }
    }
  },
  "algorithms": [
    { "name": "Astar", "schema_id": "astar_v1",
      "params": { "heuristic": ["manhattan"], "weight": [1.0, 1.2] } }
  ],
  "seeds": [0, 1, 2],
  "resources": { "timeout_sec": 60, "memory_mb": 8192 },
  "binary_version": "1.3.2+abc123"
}
```

## 3) Data Model (MongoDB)

*   **One document per logical run** in collection `runs`:  
    `(domain × instance.id × algorithm.name × algorithm.params × binary_version × seed)`
*   **Deterministic `_id`** (see §4).
*   **Store** all outputs (stdout/stderr) **compressed** and **in the DB**: inline by default; overflow options provided.
*   **Strict validation** at DB level and at app level. 

### MongoDB JSON Schema (ready to apply)

```javascript
db.createCollection("runs", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "schema_id", "domain", "instance", "algorithm", "seed", "status", "outputs"],
      properties: {
        _id: { bsonType: "string" },
        schema_id: { bsonType: "string" },
        domain: { bsonType: "string" },
        instance: {
          bsonType: "object",
          required: ["id"],
          properties: {
            id: { bsonType: "string" },
            params: { bsonType: "object" }
          },
          additionalProperties: true
        },
        algorithm: {
          bsonType: "object",
          required: ["name", "params", "params_hash", "binary_version"],
          properties: {
            name: { bsonType: "string" },
            params: { bsonType: "object" },
            params_hash: { bsonType: "string" },
            binary_version: { bsonType: "string" }
          },
          additionalProperties: true
        },
        seed: { bsonType: ["int", "long"] },
        status: { enum: ["ok", "timeout", "oom", "error"] },
        started_at: { bsonType: ["date", "null"] },
        finished_at: { bsonType: ["date", "null"] },
        wall_time_sec: { bsonType: ["double", "null"] },
        cpu_time_sec: { bsonType: ["double", "null"] },
        memory_mb: { bsonType: ["double", "null"] },
        metrics: { bsonType: "object" },
        outputs: {
          bsonType: "object",
          required: ["stdout", "stderr"],
          properties: {
            stdout: {
              bsonType: "object",
              required: ["storage", "encoding", "size_uncompressed", "size_compressed"],
              properties: {
                storage: { enum: ["inline", "gridfs", "external_collection"] },
                encoding: { enum: ["zstd"] },
                bytes: { bsonType: ["binData", "null"] },
                gridfs_id: { bsonType: ["objectId", "null"] },
                ref_id: { bsonType: ["objectId", "null"] },
                size_uncompressed: { bsonType: "long" },
                size_compressed: { bsonType: "long" }
              },
              additionalProperties: false
            },
            stderr: { "$ref": "#/properties/outputs/properties/stdout" }
          },
          additionalProperties: false
        },
        history: { bsonType: "array" }
      },
      additionalProperties: true
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

**Indexes:**

```javascript
db.runs.createIndex({ domain: 1, "algorithm.name": 1, status: 1 });
db.runs.createIndex({ "instance.id": 1 });
db.runs.createIndex({ "algorithm.binary_version": 1 });
```

## 4) Canonicalization & `_id` Construction

*   Canonicalize `algorithm.params` via:  
    `json.dumps(params, sort_keys=True, separators=(',', ':'), ensure_ascii=False)`
*   `params_hash = sha256(canonical_json).hexdigest()[:16]`
*   `_id` is a single‑line, URL‑safe token:

<!---->

    run://{domain}/{instance_id}/{algorithm}/p={params_hash}/ver={binary_version}/seed={seed}

*   URL‑encode components that contain `/` or whitespace; **no newlines** permitted.

## 5) Application‑Level Schemas (Pydantic Registry)

*   A common `RunBase` model plus **per‑algorithm** schema classes (e.g., `astar_v1`, `idastar_v1`).
*   `validate_run_doc(doc)` resolves `schema_id` → model and validates before any DB write.
*   On invalid, **do not write**; fail loudly.

## 6) Execution Model

*   The runner expands Cartesian products **deterministically** in lexicographic order:  
    domains → instances → algorithms → parameter combinations → seeds.
*   **Single process; sequential execution** (exactly one subprocess at a time).
*   Each run produces exactly one terminal document (insert or update by `_id`).
*   **Idempotency:** `_id` prevents duplicates; re‑runs update the existing doc when requested.

## 7) Resource Enforcement (with Solver‑Provided Limits)

**Principle:** Many solvers expose CLI flags to enforce **time** and **memory** limits. The adapter must pass those limits to the solver; the runner applies **slightly more generous** OS‑level limits to ensure we measure **solving time**, not startup overhead (binary loading, reading instances).

### 7.1 Time Limits

*   Let `T_solver = resources["timeout_sec"]`.
*   Runner applies a timeout `T_runner = T_solver + 2` seconds.
*   Behavior:
    1.  Solver aims to stop within `T_solver`.
    2.  Runner enforces `T_runner`: on expiry, send `SIGTERM`; after 2 s, `SIGKILL`.
    3.  If solver exits by its own limit → status reflects exit code (`ok` or `error`).
    4.  If runner kills it at `T_runner` → `status="timeout"`.  
        **Rationale:** Only **solving** gets billed against `T_solver`; loading/parsing time is not.

### 7.2 Memory Limits

*   Let `M_solver = resources["memory_mb"]`.
*   Runner sets an OS limit `M_runner = M_solver + ΔM`, with default `ΔM = 256` MB, using `resource.setrlimit(RLIMIT_AS)`.
*   If solver exceeds `M_solver`, it should terminate or fail → `status="oom"`.
*   If OS enforces the higher cap and kills the process, also → `status="oom"`. 

### 7.3 Minimum Runtime Metrics

*   Record (runner‑side): `wall_time_sec` (required), `cpu_time_sec` (best‑effort), `memory_mb` (best‑effort).
*   Adapter‑parsed KPIs are additive. 

## 8) Subprocess Execution & Ingestion

*   Launch solver with `subprocess.Popen`, **no `shell=True`**, returning pipes for stdout/stderr.
*   Stream‑compress both streams with **zstd** in bounded memory; capture sizes.
*   **Inline storage** (default): if `compressed_size ≤ MAX_INLINE_COMPRESSED_BYTES` (default 8 MiB per stream), write to `outputs.*.bytes`.
*   **Overflow options:**
    *   GridFS (`gridfs_id`) when enabled, or
    *   `run_outputs` collection (`ref_id`) when enabled.
*   Always persist `size_uncompressed` and `size_compressed`.

**Execution pseudocode:**

```python
def execute_run(adapter, algorithm, instance, seed, resources, config):
    # Build + validate metadata (no outputs yet)
    run_doc = build_run_doc(adapter, algorithm, instance, seed, resources)
    validate_run_doc(run_doc)

    # Build argv/env with solver-provided limits
    argv, env = adapter.build_cli(algorithm["params"], instance, seed, resources)

    started_at = now()
    try:
        with Popen(argv, env=env, preexec_fn=apply_rlimits(resources),
                   stdout=PIPE, stderr=PIPE) as proc:
            out_buf = ZstdStreamingBuffer()
            err_buf = ZstdStreamingBuffer()
            t_out = start_thread(pipe_reader, proc.stdout, out_buf)
            t_err = start_thread(pipe_reader, proc.stderr, err_buf)

            status = wait_with_timeout(proc, resources["timeout_sec"] + 2)
    except OOMDetected:
        status = "oom"
    finally:
        finished_at = now()

    stdout_bytes, stdout_stats = out_buf.finish()
    stderr_bytes, stderr_stats = err_buf.finish()

    storage_stdout = store_stream(stdout_bytes, stdout_stats, config)
    storage_stderr = store_stream(stderr_bytes, stderr_stats, config)

    metrics = adapter.parse_metrics(out_buf.iter_lines(), out_buf.full_text())

    run_doc.update({
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "wall_time_sec": (finished_at - started_at).total_seconds(),
        "cpu_time_sec": measured_cpu_time(),
        "memory_mb": peak_rss_mb(),
        "metrics": metrics,
        "outputs": {"stdout": storage_stdout, "stderr": storage_stderr}
    })

    validate_run_doc(run_doc)
    upsert_run(run_doc)   # by deterministic _id
```

## 9) Adapter Contract

**Responsibilities:**

1.  `instance_selector(root, selector) → List[{id, params}]` — must honor the filesystem contract and apply selectors.
2.  `build_cli(algorithm_params, instance, seed, resources) → (argv, env)` — **must inject solver time/memory limits** when solver supports them (e.g., `--time-limit`, `--memory-limit`).
3.  `parse_metrics(stdout_lines, full_stdout) → dict` — robust parsing; on failure return `{"partial": true}` at minimum.
4.  `version() → str` — return a stable solver build identifier (`semver+git`).

**Security:**

*   Never use shells; pass `argv: list[str]`.
*   Treat parameters as opaque values; do not interpolate into shell strings.

## 10) CLI

*   `exp validate <spec.json>` — validate against ExperimentSpecV1 and ensure required adapters are present.
*   `exp enumerate <spec.json> [--dry-run]` — deterministic counts + sample IDs.
*   `exp run <spec.json> [--limit N] [--resume] [--update] [--max-inline-mb 8] [--use-gridfs | --use-external-outputs] [--fail-fast | --keep-going]` — sequential execution.
*   `exp status --domain D --algorithm A [--version V]` — summary counts by status.

**Progress print (minimal):**  
`"[{i}/{N}] {domain}/{instance_id} :: {algorithm} p={hash} seed={seed} → {status}"`  
**Exit codes:** `0` success; `2` validation error; `3` failures present with `--fail-fast`. 

***

## 11) Resume & Idempotency

*   `--resume`: skip runs whose `_id` already exists with any terminal status.
*   `--update`: re‑run and **overwrite** outputs/metrics/status for existing `_id`s.
*   Upserts are atomic by `_id`; no duplicates. 

## 12) Error Handling

*   **Timeout** → solver exceeded its own limit or ran into runner grace → `status="timeout"`; still store captured outputs.
*   **OOM** → solver self‑reported OOM or OS enforced RLIMIT → `status="oom"`.
*   **Non‑zero exit** → `status="error"`; still store outputs.
*   **Parser failure** → `status="error"`, `metrics.partial=true`.
*   `--keep-going` continues after failures; otherwise `--fail-fast` stops early. 

## 13) Configuration

Environment variables (overridable via CLI):

*   `MONGO_URI`, `DB_NAME`
*   `MAX_INLINE_COMPRESSED_BYTES` (default 8 MiB per stream)
*   `USE_GRIDFS` (bool), `USE_EXTERNAL_OUTPUTS` (bool)
*   `TIMEOUT_SEC_DEFAULT`, `MEMORY_MB_DEFAULT`
*   `BINARY_VERSION` 

## 14) Repository Layout & Deliverables

    expkit/
      cli.py                 # Typer entrypoints
      db.py                  # Mongo client; collection creation; validator; indexes
      models.py              # Pydantic registry; canonicalization; hashing
      enumerate.py           # grid expansion; filesystem instance discovery
      runner.py              # subprocess exec; zstd streaming; resource limits
      ingest.py              # parse interfaces; metrics extraction
      adapters/
        __init__.py
        solver_example.py    # build_cli + parser stub (document flags for time/mem)
      util.py                # sha256, zstd helpers, time/mem capture, RLIMIT helpers
      scripts/
        init_mongo.py        # applies validator & creates indexes (+ optional GridFS)
      schemas/
        experiment_spec.schema.json
        mongo_runs_validator.js
      examples/
        tiles_astar.json
      tests/
        test_models.py
        test_hashing.py
        test_db_validator.py
        test_streaming_compress.py
        test_parser_fake.py
        test_enumeration_fs.py

## 15) Testing Strategy

**Unit:**

*   Canonicalization & hashing → stable `params_hash` under key reordering.
*   RLIMIT application → synthetic OOM triggers `oom`.
*   zstd streaming → bounded memory; round‑trip integrity; inline/overflow boundary.
*   Mongo validator → invalid docs rejected; valid docs accepted.

**Integration:**

*   Fake solver printing JSON lines (exit 0) → `ok`.
*   Fake solver sleeping past `T_solver` but before `T_runner` → ensure solver exit with `ok`/`error` (not `timeout`).
*   Fake solver exceeding `T_runner` → `timeout`.
*   Fake solver exceeding `M_solver` or `M_runner` → `oom`.
*   Resume semantics: `--resume` skips; `--update` overwrites.

**E2E:**

*   `validate/enumerate/run/status` against `examples/tiles_astar.json` with GridFS and external storage modes.

## 16) Security & Robustness

*   Never pass untrusted data to a shell; always `argv: list[str]`.
*   Restrict environment to a whitelist.
*   Decode text as UTF‑8 with replacement for undecodable bytes.
*   Clamp all size fields to non‑negative 64‑bit integers.
*   URL‑encode `_id` components to avoid separators and whitespace.

## 17) Performance Notes

*   Stream chunks: 256 KiB; avoid copies; flush frames incrementally.
*   No batch writes: single‑document upserts to preserve idempotency semantics and simplicity.

## 18) Acceptance Criteria

*   **No plaintext outputs on disk** at any time.
*   **Strict schemas** at DB and app level; invalid docs are rejected.
*   **Easy schema extension** via registry (add one class and a map entry).
*   **Idempotency:** deterministic `_id`; re‑runs update the same doc.
*   **Terminal‑only statuses** with accurate timestamps and metrics.
*   **Indexes** provide sub‑second queries by domain/algorithm/status and by binary\_version.
*   **Resource enforcement:** solver receives primary time/memory limits; runner enforces **slightly more generous** limits (`+2s`, `+ΔM`) so solving time is billed, not overhead.
*   **E2E demo:** fake solver stores compressed outputs and metrics in DB.

## 19) Example Run Document (Template)

```json
{
  "_id": "run://tiles/inst-000123/Astar/p=3b1c7f2a1e2c4d8f/ver=1.3.2+abc123/seed=0",
  "schema_id": "astar_v1",
  "domain": "tiles",
  "instance": { "id": "inst-000123", "params": { "width": 4, "height": 4 } },
  "algorithm": {
    "name": "Astar",
    "params": { "heuristic": "manhattan", "weight": 1.0 },
    "params_hash": "3b1c7f2a1e2c4d8f",
    "binary_version": "1.3.2+abc123"
  },
  "seed": 0,
  "resources": { "timeout_sec": 60, "memory_mb": 8192 },
  "host": { "name": null },
  "started_at": null,
  "finished_at": null,
  "status": "ok",
  "wall_time_sec": null,
  "cpu_time_sec": null,
  "memory_mb": null,
  "metrics": {},
  "outputs": {
    "stdout": {
      "storage": "inline",
      "encoding": "zstd",
      "bytes": null,
      "gridfs_id": null,
      "ref_id": null,
      "size_uncompressed": 0,
      "size_compressed": 0
    },
    "stderr": {
      "storage": "inline",
      "encoding": "zstd",
      "bytes": null,
      "gridfs_id": null,
      "ref_id": null,
      "size_uncompressed": 0,
      "size_compressed": 0
    }
  },
  "history": []
}
```

## 20) Implementation Task List

1.  Mongo setup (collection, validator, indexes, optional GridFS).
2.  Canonicalization + hashing + `_id` derivation.
3.  Runner with resource enforcement (solver limits + graceful runner caps) and zstd streaming.
4.  Adapter protocol + a fake solver for E2E.
5.  CLI (`validate`, `enumerate`, `run`, `status`) with `--resume`/`--update` semantics.
6.  Pydantic registry and **mandatory** pre‑write validation.
7.  Tests (unit, integration, E2E) as specified.