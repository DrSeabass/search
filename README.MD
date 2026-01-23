# Overview

Code for researching heuristic search algorithms.

You can build with either GCC or clang.  If one or the other doesn't
work then it is a bug so please tell me.

Ubuntu package dependencies:
	libboost-dev

The plat2d/watch binary and graphics code also need:
	libsdl1.2-dev libsdl-image1.2-dev

search/learnh/lms needs lapack:
	liblapack-dev

Clang versions less than 3.0 do not seem to work.

# Outstanding Issues
Please see [TODO.md](./TODO.md)

# Domains

## blocksworld

A bespoke implementation of the [classic planning domain](https://en.wikipedia.org/wiki/Blocks_world).

### Instance Generation

Done via python script.
```
python3 problemGen.py -b 10 -ss 3 -sg 5 -f demo_problem.txt
```

### Invoking Solvers

```
cat demo_problem.txt | ./20bw_solver astar
cat demo_problem.txt | ./20bw_solver wastar -wt 2.25
```

## drobot

A domain-specific implementation of dock-worker robots, a classic planning domain.

### Instance Generation

Done via a Python script that emits text files in the native drobot format.

Generate a single instance and write it to a file:

```
cd drobot
./make_instances.py --nlocs 20 --piles-per-loc 3 --cranes-per-loc 2 \
    --ncontainers 100 --seed 42 -o demo_problem.txt
```

### Invoking Solver

```
cat demo_problem.txt | ./drobot_solver astar
cat demo_problem.txt | ./drobot_solver wastar -wt 2.25
```

## gridnav

### Instance Generation

#### Uniform Random Instances

```
./mkseedinst -width 80 -height 25 -prob 0.1 -lifecost -eightway # Life Cost Octile Movement
./mkseedinst -width 80 -height 25 -prob 0.1 -lifecost 		 # Life Cost 4-Way Movement
./mkseedinst -width 80 -height 25 -prob 0.1 -eightway 		 # Unit Cost Octile Movement
./mkseedinst -width 80 -height 25 -prob 0.1 	       		 # Unit Cost 4-Way Movement
```

#### randinst

Takes a grid and produces a random instance on top of it by adding start and goal locations.

```
./mkseedinst -height 25 -width 80 -prob 0.1 > demo.grid
./randinst -s 2 -m demo.grid > demo.instance
```


#### Portable Pixel Map

```
./ppm2grid foo.ppm
```

#### Random Cups
**TODO**
Missing base input to run bash file

### Invoking Solver

```
./mkseedinst -height 25 -width 80 -prob 0.1 > demo.grid
./randinst -s 2 -m demo.grid > demon.instanec
cat demo.instance | ./gridnav_solver astar
```

### Displaying Instances
#### Draw

Produces an image of the grid instance supplied on standard in.
Additionally prints it to stdout if desired. Postscript is the only
output file format supported.

```
./mkseedinst -height 25 -width 80 -prob 0.1 | ./draw -o demo_image.ps -p
```

#### Watch

For creating movies of recorded search runs.  It's currently unclear how to record search runs on grids.

### Other Binaries With Unknown Effects
**TODO** Figure out what these do for sure and update
* scenario2rdb
* scenario_solver
* 2poly

## pancake
### Instance Generation

Instances are generated via a lightweight Python script that shuffles
``ncakes`` into a random permutation and writes it to numbered files.

Generate 10 pancake instances with 50 cakes each:

```
cd pancake
./make_instances.py --seed 42 --ncakes 50 --count 10 --out-dir ./instances
```

### Invoking Solver

```
./50pancake_solver astar
./70pancake_solver astar
```

## plat2d

Videogame pathfinding Instances based off of [Ethan's game Mid](https://github.com/eaburns/mid)

### Instance Generation

Via ```mklvls.sh``` but assumes you've built mid and have access to the level generator in ```cmd```.

### Invoking Solver

```
cat demo_lvl | ./plat2d_solver astar
```

## segments

Robotic motion planning navigation assuming holonomic motion and a
point robot.  Basically you move from from corner of polygon to corner
of polygon while navigating a two dimmensional field strewn with
shapes, a start, and a goal.

### Instance Generation

```
./mkinst -width 80 -height 25 -nangle 16 -seed 42
```

### Invoking Solver

```
./mkinst -seed 42 > demo.inst
cat demo.inst | ./segments_solver greedy
```

## synth_tree
### Instance Generation

Via a Python script that produces simple seed files, each defining a
deterministic synthetic tree explored by the C++ domain.

Generate 10 instances using RNG seed 42:

```
cd synth_tree
./make_instances.py --count 10 --seed 42 --out-dir ./instances
```

### Invoking Solver

Each generated instance is a single integer seed on its own line. The
``synth_tree_solver`` reads this from standard input.

Run A* on the first generated instance with no heuristic error:

```
cat instances/1 | ./synth_tree_solver astar
```

Optionally, you can inject heuristic error using the ``-err`` flag:

```
cat instances/1 | ./synth_tree_solver astar -err 0.1
```

## tiles
### Instance Generation

```./generator -h4 -w4 -n100 -d ./4x4 -seed 42```

### Invoking Solver

```cat 4x4/0 | ./15md_solver greedy```

## traffic
### Instance Generation
```
./randinst <width> <height> <number of objects> <seed>
./randinst 200 100 10 42
```
### Invoking Solver
```
./randinst 5 5 1 0 | ./traffic_solver greedy
```

## vacuum
### Instance Generation

Instances are generated via a Python script that creates random grids in
the format expected by the C++ ``Vacuum`` domain.

Generate 10 vacuum instances on a 10x15 grid with 20% blocked cells, 5
dirts, and 1 charger tile:

```
cd vacuum
./make_instances.py --height 10 --width 15 --p-blocked 0.2 --dirts 5 \
    --chargers 1 --seed 42 --count 10 --out-dir ./instances
```
### Invoking Solver

Each generated instance is written as ``instances/1``, ``instances/2``,
and so on. The solver reads from standard input.

Run A* with unit costs on the first generated instance:

```
cat instances/1 | ./vacuum_solver astar
```

You can also use weighted A* and/or cost variants via ``-cost``:

```
cat instances/1 | ./vacuum_solver wastar -wt 2.25 -cost life
```

## visnav
### Instance Generation
```
./rand | ./inst
```

### Invoking Solver

```
cat tmp.inst | ./visnav_solver greedy
```\