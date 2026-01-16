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

**Not Provided**

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
./randinst -s 2 -m demo.grid > demon.instanec
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
