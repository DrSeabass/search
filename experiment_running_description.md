# What empirical research often looks like
* Have a large set of binaries representing many algorithms and solvers for particular problems of interest
* Have a large set of input instances representing domains of industrial or scientific interest
* Run many binaries in multiple configurations against inputs, producing an output file of some structure
* Re-read the output files in aggregate to compare performance, show trends, etc.

# How Instances Are Stored
* root instances directory - /home/user/research/instances/
    * domain name - e.g. tiles, grids, etc
        * key_file - a touched file with key=value, e.g. key=width
        * directory for each key value - ./4/ ./6/ ./200/ etc
            * The final key in the terminal directory is key=instance

# How Experiment Data Was Historically Stored
* root empirical data directory - home/user/research/experiments
    * domain name
        * instance parameters (as described above in how instances are stored) minus instance ID
            * algorithm name
                * algorithm parameters
                    * instance id

# How experiments were historically run
* Researcher writes JSON blob describing experiment to run including
    * Domains + Domain Parameter sets per Domain
    * Algorithms + Algorithm Parameter sets per Domain
* Experiment Runner Code begins running
    * Identifies all relevant instances to run the experiment on
        * Per each instance
            * Produce a file path where the algorithm configuration x instance would go
            * If it exists, move on
            * If not, create the path and touch the file
            * Invoke the binary and pipe output to the file

# Expected future changes (minimal invasion)
* Researcher writes JSON blob describing experiment to run including
    * Domains + Domain Parameter sets per Domain
    * Algorithms + Algorithm Parameter sets per Domain
* Experiment Runner Code begins running
    * Queries Document Store Discovering non-existing instance x algorithm results
    * Identifies all relevant instances to run the experiment on
        * For each instance & algorithm configuration
            * Option A
                * Invoke the binary and pipe output to a tmp file
                * cat tmp file into an ingestion shim that store results in the documentDB
                * clean up tmp file
            * Option B
                * As option A, but performed in memory to avoid tmp file writing and deletion


---
Machine Generated Design Doc Follows:
---

# Design Doc: Document‑DB–Only Experiment Runner (Python, Single Process)

**Audience:** agentic coding system (e.g., cline)  
**Goal:** Execute solver runs over instances and persist **all** experimental data (metadata, metrics, and raw outputs) in a **document store**. Enforce strict, extensible schemas; avoid duplicates; emit minimal CLI progress. **No plaintext artifacts on disk.**

## 0) Constraints & Non‑Goals

*   **Runtime:** Python; **single process**; local machine.
*   **Scale:** up to \~1e6 runs/year.
*   **Storage:** **All** outputs stored in DB (inline compressed; optional overflow).
*   **Top queries/indexes:** `domain`, `algorithm.name`, `instance.id`, `algorithm.binary_version`.
*   **Schema:** fail loudly unless doc matches a **pre‑recognized schema**; adding schemas is easy.
*   **Statuses:** **terminal only** → `ok`, `timeout`, `oom`, `error`.
*   **Progress:** lightweight CLI prints.
*   **Out of scope (v1):** dashboards, distributed queueing, experiment completeness tracking.

## 1) Technology Choices

*   **Document DB:** MongoDB Community (single node, local).
*   **Binary storage within DB:**
    *   **Default:** Inline **zstd‑compressed** `binData` for stdout/stderr in `runs.outputs`.
    *   **Overflow (optional, toggle):**
        *   **GridFS** when compressed stream exceeds threshold (e.g., 8–12 MB), **or**
        *   **`run_outputs` collection** storing big `binData` by reference.
*   **Python libs:** `pymongo`, `typer`, `pydantic`, `orjson`, `zstandard`, `subprocess`.

## 2) Data Model

**One document per logical run**: `(domain × instance.id × algorithm params × binary_version × seed)`.

### 2.1 `runs` collection (core)

**Natural key → `_id`:**

    {domain}|{instance_id}|{algorithm}|p={params_hash}|ver={binary_version}|seed={seed}

*   `params_hash` = `sha256(json.dumps(params, sort_keys=True, separators=(',',':')))[:16]`
*   `binary_version` immutable (e.g., `1.3.2+abc123`).

**Document shape**

```json
{
  "_id": "tiles|inst-000123|Astar|p=3b1c7f2a1e2c4d8f|ver=1.3.2+abc123|seed=0",
  "schema_id": "astar_v1",

  "domain": "tiles",
  "instance": {
    "id": "inst-000123",
    "params": {"width": 4, "height": 4}
  },

  "algorithm": {
    "name": "Astar",
    "params": {"heuristic": "manhattan", "weight": 1.0},
    "params_hash": "3b1c7f2a1e2c4d8f",
    "binary_version": "1.3.2+abc123"
  },

  "seed": 0,
  "resources": {"timeout_sec": 60, "memory_mb": 8192},
  "host": {"name": null},

  "started_at": null,
  "finished_at": null,

  "status": "ok",                // ok|timeout|oom|error

  "wall_time_sec": null,
  "cpu_time_sec": null,
  "memory_mb": null,

  "metrics": {},                 // ragged KPIs (parsed)
  "outputs": {
    "stdout": {
      "storage": "inline",       // inline|gridfs|external_collection
      "encoding": "zstd",
      "bytes": null,             // binData if inline, else null
      "gridfs_id": null,         // if gridfs
      "ref_id": null,            // if external_collection
      "size_uncompressed": 0,
      "size_compressed": 0
    },
    "stderr": { /* same shape */ }
  },

  "history": []                  // optional state notes (e.g., retries)
}
```

## 3) Canonicalization & Hashing

*   Canonicalize algorithm params: `json.dumps(params, sort_keys=True, separators=(',',':'))`.
*   `params_hash = sha256(canonical).hexdigest()[:16]`.
*   `_id` assembled from `{domain, instance_id, algorithm, params_hash, binary_version, seed}`.

## 4) Schema Enforcement

**Intent:** Reject any run that doesn’t match a known, registered schema. **Adding a schema is trivial**.

### 4.1 DB‑Level (MongoDB JSON Schema)

*   Enforce base structure + **terminal‑only** statuses + require `schema_id`.
*   Strict validation; fail insert/update if invalid.

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

        // Terminal-only statuses
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

### 4.2 App‑Level (Pydantic Registry)

*   Enforce **per‑algorithm** shapes via a **schema registry**.
*   Adding a schema: implement a `Pydantic` class and register it.

```python
# models.py
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional

class InstanceShape(BaseModel):
    id: str
    params: Dict[str, Any]

class AlgorithmBase(BaseModel):
    name: str
    params: Dict[str, Any]
    params_hash: str
    binary_version: str

class OutputStream(BaseModel):
    storage: str         # "inline"|"gridfs"|"external_collection"
    encoding: str        # "zstd"
    size_uncompressed: int
    size_compressed: int
    bytes: Optional[bytes] = None
    gridfs_id: Optional[str] = None
    ref_id: Optional[str] = None

class RunBase(BaseModel):
    schema_id: str
    domain: str
    instance: InstanceShape
    algorithm: AlgorithmBase
    seed: int
    status: str          # "ok"|"timeout"|"oom"|"error"
    outputs: Dict[str, OutputStream]
    metrics: Dict[str, Any] = {}
    started_at: Optional[Any] = None
    finished_at: Optional[Any] = None
    wall_time_sec: Optional[float] = None
    cpu_time_sec: Optional[float] = None
    memory_mb: Optional[float] = None

class AStarSchemaV1(RunBase):
    @validator("algorithm")
    def check_astar(cls, alg: AlgorithmBase):
        if alg.name != "Astar":
            raise ValueError("astar_v1 requires algorithm.name == 'Astar'")
        if "heuristic" not in alg.params:
            raise ValueError("Astar requires 'heuristic'")
        w = alg.params.get("weight", 1.0)
        if not isinstance(w, (int, float)):
            raise ValueError("'weight' must be numeric")
        return alg

class IDAStarSchemaV1(RunBase):
    @validator("algorithm")
    def check_idastar(cls, alg: AlgorithmBase):
        if alg.name != "IDAstar":
            raise ValueError("idastar_v1 requires algorithm.name == 'IDAstar'")
        return alg

SCHEMA_REGISTRY = {
    "astar_v1": AStarSchemaV1,
    "idastar_v1": IDAStarSchemaV1,
}

def validate_run_doc(doc: dict) -> dict:
    sid = doc.get("schema_id")
    model = SCHEMA_REGISTRY.get(sid)
    if not model:
        raise ValueError(f"Unknown schema_id: {sid}")
    return model.parse_obj(doc).dict()
```

**Write path rule:** Build run doc → **`validate_run_doc(doc)`** → **insert/update**. If invalid: raise; **do not write**.

## 5) Indexes (initial)

```javascript
db.runs.createIndex({ domain: 1, "algorithm.name": 1, status: 1 });
db.runs.createIndex({ "instance.id": 1 });
db.runs.createIndex({ "algorithm.binary_version": 1 });
```

## 6) Runner Lifecycle (Single Process, Terminal‑Only)

*   Expand grid; for each candidate, compute `_id`.
*   **Insert new** or **update existing** doc (same `_id`) with **terminal status**:
    *   `ok`, `timeout`, `oom`, `error`
*   Set `started_at` and `finished_at` locally (timestamps around the subprocess).
*   **Progress prints** (minimal):
    *   `"[{i}/{N}] {domain}/{instance_id} :: {algorithm} p={hash} seed={seed} → {status}"`

## 7) Execution & Ingestion (No Disk Writes)

*   Spawn solver with `subprocess.Popen` and capture **stdout/stderr pipes**.
*   **Stream‑compress** with `zstd` to in‑memory buffers; track sizes.
*   Parse metrics from stream (line-oriented) or after capture.
*   **Inline storage (default):** if `compressed_size ≤ MAX_INLINE_COMPRESSED_BYTES` (default **8 MB** per stream), set `outputs.*.bytes = binData`.
*   **Overflow (optional):**
    *   If enabled and exceeded → write stream to **GridFS** and store `gridfs_id`, or
    *   Write to **`run_outputs`** collection (document per stream) and store `ref_id`.
*   Always include `size_uncompressed` and `size_compressed`.

## 8) Experiment Spec (Input)

Minimal JSON contract (example):

```json
{
  "name": "tiles_astar_width_sweep",
  "domains": [
    {"name": "tiles", "params": {"width": [4, 6, 200], "height": [4]}}
  ],
  "instances": {
    "tiles": {
      "root": "/home/user/research/instances/tiles",
      "selector": {"width__in": [4, 6, 200]}
    }
  },
  "algorithms": [
    {"name": "Astar", "schema_id": "astar_v1",
     "params": {"heuristic": ["manhattan"], "weight": [1.0, 1.2]}}
  ],
  "seeds": [0, 1, 2],
  "resources": {"timeout_sec": 60, "memory_mb": 8192},
  "binary_version": "1.3.2+abc123"
}
```

## 9) CLI (Typer)

*   `exp validate <spec.json>` — validate experiment spec.
*   `exp enumerate <spec.json> [--dry-run]` — print counts + sample IDs.
*   `exp run <spec.json> [--limit N] [--resume] [--max-inline-mb 8] [--use-gridfs|--use-external-outputs]`
*   `exp status --domain D --algorithm A [--version V]`

**Progress prints only** (no TUI).

## 10) Adapters (per solver framework)

*   **Instance enumerator:** `(domain, domain_params) -> List[{id, params}]`
*   **CLI builder:** `(algorithm.name, algorithm.params, instance, seed) -> argv, env`
*   **Parser:** `(iterable_of_stdout_lines | full_text) -> metrics dict`
*   **Version reporter (optional):** `binary → "semver+git"`

Adapters live in `adapters/<solver>.py`.

## 11) Error Handling

*   Timeout → `status="timeout"`.
*   OOM (wrapper detection) → `status="oom"`.
*   Non‑zero exit → `status="error"`; still store captured outputs compressed.
*   Parser failure → `status="error"`, `metrics.partial=true`.
*   **Always** validate and write a terminal doc (or fail hard before write).

## 12) Repo Layout & Deliverables

    expkit/
      cli.py              # Typer entrypoints
      db.py               # Mongo client; collection creation; validator; indexes
      models.py           # pydantic registry; canonicalization; hashing
      enumerate.py        # grid expansion; instance discovery
      runner.py           # subprocess exec; zstd streaming; doc assembly
      ingest.py           # parse interfaces; metrics extraction
      adapters/
        __init__.py
        solver_example.py # CLI builder + parser stub
      util.py             # sha256, zstd helpers, time/mem capture
    scripts/
      init_mongo.py       # applies validator + creates indexes (+ optional GridFS setup)
    examples/
      tiles_astar.json
    tests/
      test_models.py
      test_hashing.py
      test_db_validator.py
      test_streaming_compress.py
      test_parser_fake.py

**Agent tasks:**

1.  Implement Mongo setup (validator + indexes).
2.  Implement zstd streaming (bounded memory) with inline/overflow toggle.
3.  Implement canonicalization + hashing + `_id` derivation.
4.  Implement runner (single process) with terminal‑only states.
5.  Implement adapter stubs and a fake solver for E2E.
6.  Implement strict Pydantic schema registry and pre‑write validation.
7.  Add unit/integration tests.

## 13) Configuration (env/CLI)

*   `MONGO_URI`, `DB_NAME`
*   `MAX_INLINE_COMPRESSED_BYTES` (default **8 MB** per stream)
*   `USE_GRIDFS` (bool) or `USE_EXTERNAL_OUTPUTS` (bool)
*   `TIMEOUT_SEC_DEFAULT`, `MEMORY_MB_DEFAULT`
*   `BINARY_VERSION` (from spec or adapter)

## 14) Acceptance Criteria

*   **No plaintext experimental outputs** are written to disk.
*   **Strict schema enforcement**: invalid docs rejected (DB and app‑level).
*   **Easy schema extension** via registry (one new class + map entry).
*   **Idempotency** via deterministic `_id` (no duplicates).
*   **Terminal-only statuses** with accurate times and metrics.
*   **Indexes** support sub‑second queries for top filters.
*   E2E demo with fake solver stores compressed outputs and metrics.

