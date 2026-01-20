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

## pancake
### Instance Generation

Not provided

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

No provided instance generation

### Invoking Solver

## tiles
### Instance Generation

```./generator -h4 -w4 -n100 -d ./4x4 -seed 42```

### Invoking Solver

```cat 4x4/0 | ./15md_solver greedy```

## traffic
### Instance Generation
### Invoking Solver

## vacuum
### Instance Generation
### Invoking Solver

## visnav
### Instance Generation
### Invoking Solver