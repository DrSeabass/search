# Bugs

None known as of now.

## Fixed

* blocksworld: intermittent assertion failure in `Blocksworld::pathcost`
  (`e.state.eq(this, path[i])`). Root cause: the constructor declared a local
  `unsigned int Nblocks` that shadowed the class enum `Nblocks` (== NBLOCKS), so
  `movelibrary` was populated using the *instance's* block count as its stride
  while `getmoveref()` indexed it using the *enum* — the strides disagreed, so
  `movelibrary[getmoveref(...)]` returned the wrong move (and a bogus reverse op),
  corrupting both moves and their inverses. Also left `init[]`/`goal[]` beyond the
  instance count uninitialized. Fixed by reading the instance count into a member
  `nblocks`, zero-initializing unused entries, validating the count against the
  compiled capacity, populating `movelibrary` at the enum stride, and bounding the
  operator generator by `nblocks`. blocksworld now solves reliably across sizes.

## Possible Bugs

* Haven't seen a segments instance solved.  May be a bug in implementation
  * `segments/mkinst` CLI also rejects the README's documented flags
    ("Failed to read the turning angle step").
* VisNav seg faults
* vacuum: a charge operator stalls/loops the search when `--chargers > 0`
  (prints "Charge operator!" then fails to terminate). Use `--chargers 0` until
  resolved. Likely a stray debug print + buggy charge-op handling.

# Modernization

* Moving away from RDB data representation and going to something else
    * JSON
        * utils/rdb_to_json.py helps with this a bit, but it's a stop-gap measure.
    * SQL
    * Document Database?

# Features

* Experiment Running Harness
    * RESOLVED (initial cut): a baseline + harness now lives in-repo.
        * `regression/` — fast deterministic regression baseline (`make regression`).
        * `experiments/2026-06-baseline/` — worked Downward Lab study (the
          chosen harness; shares the analysis pipeline with the FD/Scorpion side).
        * The MongoDB document-store design in `experiment_running_description.md`
          / `agentic_experiment_running_plan.md` is deferred as a more ambitious,
          orthogonal effort (see ALGORITHM_PORT_TODO.md).
    * Original open question retained below for the record:
    * Should this be baked in or a separate repository?
        * For
            * Replicating paper results becomes trivial
                * Check out tagged revision
                * Build
                * run associated scripts
            * Setting up new researcher / student is faster
            * These programs don't really make sense unless run in bulk. The intent is evaluation
            * This is how other projects in my lab are done (e.g. Scorpion)
        * Against
            * Yet another thing this has to do and keep in sync
            * Experiments are not common across researchers
            * The notion is very repeatable
                * Run these binaries with these configurations in this sequence, piping output here
        * Maybe a sub-repo is what makes sense here
* Improving Error & Help Messages
* Make Documentation ([README](README.MD), not code docs) Useful
* Pancake solving on arbitrary size
* More algorithms for menagerie

# Janitorial
* Rename Instance Generation for all domains so that it is consistent
    * This requires non-trivial work for gridnav and a few other domains
* Investigate Eaburns & Snlemons branches to see if there's more to merge in
    * eaburns is integrate
    * snlemons has several branches
        * they look like they've been merged in, but not deleted from the remote
        * Can safely ignore for now
        * Reach out and see if you get a response on current state + rectangle implementation

