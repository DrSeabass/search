# Bugs

None known as of now

## Possible Bugs

* Haven't seen a segments instance solved.  May be a bug in implementation
* VisNav seg faults

# Modernization

* Moving away from RDB data representation and going to something else
    * JSON
        * utils/rdb_to_json.py helps with this a bit, but it's a stop-gap measure.
    * SQL
    * Document Database?

# Features

* Experiment Running Harness
    * Should this be baked in or a separate repository?
        * For
            * Replicating paper results becomes trivial
                * Check out tagged revision
                * Build
                * run associated scripts
            * Setting up new researcher / student is faster
            * These programs don't really make sense unless run in bulk. The intent is evaluation
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

