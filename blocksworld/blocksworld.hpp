#include <cstdio>
#include <cstdlib>
#include <cassert>
#include <vector>
#include <string>

#define MAXBLOCKS 250
#if NBLOCKS > MAXBLOCKS
#error Too many blocks for unsigned char typed blocks.
#endif

extern "C" unsigned long hashbytes(unsigned char[], unsigned int);

class Blocksworld{
public:
    typedef unsigned char Block;
	typedef unsigned int Cost;
    typedef unsigned short Oper;

    enum{Nblocks = NBLOCKS};
	// The type of an operator which can be
	// applied to a state.  This is usually just an
	// integer but it may be some more complex
	// class.  Searches assume that operator==
	// is defined on the Oper class.

    struct Move{
        Block from;
        Block to;

        Move() : from(0), to(0){}
        Move(Block b1, Block b2){
            from = b1;
            to = b2;
        }

        bool operator==(const Move &o) const {
			return from == o.from && to == o.to;
        }
    };

#ifdef DEEP
    static const Oper Nop = Nblocks*Nblocks + Nblocks;//a "do nothing" action
#else
    static const Oper Nop = Nblocks*Nblocks;//a "do nothing" action
#endif

	Blocksworld(FILE*);

	struct State {
        bool eq(const Blocksworld*, const State &o) const {
			for (unsigned int i = 0; i < Nblocks; i++) {
				if (below[i] != o.below[i])
					return false;
			}
			return true;
		}

        bool operator==(const State &o) const {
			for(int i = 0; i<Nblocks; i++){
                if(o.below[i] != below[i]) return false;
            }
            return true;
		}

        void moveblock(Oper move, const Blocksworld &domain)
        {
#ifdef DEEP
            Cost hadj = 2; //h adjustment
#else
            Cost hadj = 1;
#endif
            Block pickUp = domain.movelibrary[move].from;
            Block putOn = domain.movelibrary[move].to;
            Block block = pickUp;
            //If at any point in the stack, the block below doesn't match what is in the goal, remove 1 from h.
            while(block!=0)
            {
                if(below[block-1] != domain.goal[block-1]){
#ifdef DEEP
                    if(below[pickUp-1] == pickUp) h--;
                    else
#endif
                    h -= hadj;
                    break;
                }
                block = below[block-1];
            }
            //remove block from top of old stack (set block below to have nothing on top)
            if(below[pickUp-1] != 0) above[below[pickUp-1]-1] = 0;
            if(putOn != 0) {
                above[putOn-1] = pickUp;
                below[pickUp-1] = putOn;
                //see if block's new location is correct (add 1 to h if not)
                if(below[pickUp-1]!=domain.goal[pickUp-1]){
#ifdef DEEP
                    if(below[pickUp-1] == pickUp) h ++;
                    else
#endif
                    h += hadj;

                 }
                //otherwise move down stack, if any are out of place, add 1 to h.
                else{
                    block = below[pickUp-1];
                    while(block!=0)
                    {
                        if(below[block-1] != domain.goal[block-1]){
                            h += hadj;
                            break;
                        }
                        block = below[block-1];
                    }
                }
            }
            else{
                below[pickUp-1] = 0;
                if(domain.goal[pickUp-1]!=0) h += hadj;
            }
            d = h;
        }

    private:
        friend class Blocksworld;

        Block above[Nblocks] = {0};
        Block below[Nblocks];
        Cost h;
        Cost d;
    };

	// Memory-intensive algs such as A* which store
	// PackedStates instead of States.  Each time operations
	// are needed, the state is unpacked and operated
	// upon.
	struct PackedState {
		Block below[Nblocks];
        Cost h;

		// Functions for putting a packed state
		// into a hash table.
		bool operator==(const PackedState &o) const {
			for(int i = 0; i<Nblocks; i++){
                if(o.below[i] != below[i]) return false;
            }
            return h==o.h;
		}

        unsigned long hash(const Blocksworld*) const {
            return hashbytes((unsigned char *) below,
                        Nblocks * sizeof(Block));
        }

        bool eq(const Blocksworld*, const PackedState &o) const {
            for (unsigned int i = 0; i < Nblocks; i++) {
                if (below[i] != o.below[i])
                    return false;
            }
            return true;
        }

	};

	// Get the initial state.
	State initialstate();

	// Get the heuristic.
	Cost h(const State &s) const {
		return s.h;
	}

	// Get a distance estimate.
	Cost d(const State &s) const {
		return s.d;
	}

	// Is the given state a goal state?
	bool isgoal(const State &s) const {
		return s.h  == 0;
	}

	// Operators implements an vector of the applicable
	// operators for a given state.
	struct Operators {
		Operators(const Blocksworld& b, const State& s){
#ifndef DEEP
                int stacks = 0;
                int tabled = 0;
                for(int i = 0; i< (int) b.nblocks; i++){
                    if(s.above[i] == 0 && s.below[i] != 0) stacks++;
                    else if(s.above[i] == 0) tabled++;
                }
                n = tabled * (stacks + tabled -1) + stacks * (stacks + tabled);
                int * tops = new int[stacks+tabled];
                int pos = 0;
                for(int i = 0; i< (int) b.nblocks; i++){
                    if(s.above[i] == 0) {
                        tops[pos] = i;
                        pos++;
                    }
                }
                pos = 0;
                Oper * temp = new Oper[n];
                mvs = temp;
                for(int pickUp = 0; pickUp < stacks+tabled; pickUp++){
                    for(int putOn = 0; putOn < stacks+tabled; putOn++){
                        if(pickUp!=putOn) mvs[pos] = b.getmoveref(tops[pickUp]+1, tops[putOn]+1);
                        else if(s.below[tops[pickUp]]==0) continue;
                        else mvs[pos] = b.getmoveref(tops[pickUp]+1, 0);
                        pos++;
                    }
                }
                delete [] tops;
#else
                int stacks = 0;
                Block hand = 0;
                int i;
                for(i = 0; i < (int) b.nblocks; i++){
                    if(s.above[i] == 0) stacks++;
                    if(s.below[i] == i+1) hand = i+1;
                }
                int *tops = new int[stacks];
                int pos = 0;
                for(i = 0; i < (int) b.nblocks; i++){
                    if(s.above[i] == 0 && s.below[i] != i+1){
                        tops[pos] = i;
                        pos++;
                    }
                }
                n=stacks;
                if(hand) n++;
                pos = 0;
                Oper * temp = new Oper[n];
                mvs = temp;
                for(int pickUp = 0; pickUp < stacks; pickUp++){
                    if(hand) mvs[pos] = b.getmoveref(hand, tops[pickUp]+1);
                    else mvs[pos] = b.getmoveref(tops[pickUp]+1, tops[pickUp]+1);
                    pos++;
                }
                if(hand) mvs[pos] = b.getmoveref(hand, 0);
#endif
        }

		// size returns the number of applicable operatiors.
		unsigned int size() const {
            return n;
		}

		// operator[] returns a specific operator.
		Oper operator[] (unsigned int i) const {
			return mvs[i];
		}

    private:
        Oper *mvs;
        int n;
	};

	struct Edge {
		Cost cost;
		Oper revop;
		Cost revcost;
		State &state;
        Blocksworld &domain;

		// Applys the operator to thet state.  Some domains
		// may modify the input state in this constructor.
		// Because of this, a search algorithm may not
		// use the state passed to this constructor until
		// after the Edge's destructor has been called!
		Edge(Blocksworld& d, State &s, Oper move) :
                cost(1), revop(d.getmoveref(d.movelibrary[move].from, s.below[d.movelibrary[move].from-1])),
                revcost(1), state(s), domain(d){
            state.moveblock(move, domain);
        }

		// The destructor is expected to undo any changes
		// that it may have made to the input state in
		// the constructor.  If a domain uses out-of-place
		// modification then the destructor may not be
		// required.
		~Edge(void) {
            state.moveblock(revop, domain);
        }
	};

	// Pack the state into the destination packed state.
	// If PackedState is the same type as State then this
	// should at least copy.
	void pack(PackedState &dst, State &src) const {
        for(int i = 0; i<Nblocks; i++) dst.below[i] = src.below[i];
        dst.h = src.h;
	}

	// Unpack the state and return a reference to the
	// resulting unpacked state.  If PackedState and
	// State are the same type then the packed state
	// can just be immediately returned and used
	// so that there is no need to copy.
	State &unpack(State &buf, PackedState &pkd) const {
		for(int i = 0; i<Nblocks; i++) buf.below[i] = pkd.below[i];
        buf.h = pkd.h;
        buf.d = pkd.h;
        Block i;
        for(i = 0; i<Nblocks; i++)buf.above[i] = 0;
        for (i = 0; i < Nblocks; i++){
            if(buf.below[i]!=0)
                buf.above[buf.below[i]-1] = i+1;
        }
        return buf;
	}

	// Print the state.
	void dumpstate(FILE *out, const State &s) const {
        Block printarray[Nblocks][Nblocks];
        for(int i=0; i<Nblocks; i++){
            for(int j=0; j<Nblocks; j++) printarray[i][j]=0;
        }
        int stack = 0;
        int height = 0;
        int maxheight = 0;
        Block current;
        Block hand = 0;
        unsigned int spaces = std::to_string(Nblocks).length();
		for(int i=0; i<Nblocks; i++){
            if(s.below[i]==0){
                current = i+1;
                while(current!=0){
                    printarray[stack][height] = current;
                    current = s.above[current-1];
                    height++;
                }
                if(height>maxheight) maxheight = height;
                height = 0;
                stack++;
            }
            else if(s.below[i] == i+1) hand = s.below[i];
        }

        for(int j=maxheight; j>=0; j--){
            for(int i=0; i<stack; i++){
                unsigned int fill = spaces - std::to_string(printarray[i][j]).length();
                for(unsigned int k=0; k< fill; k++) fprintf(out, " ");
                if(printarray[i][j]==0) fprintf(out, "  ");
                else fprintf(out, "%u ", printarray[i][j]);
            }
            fprintf(out, "\n");
        }
        if(hand) fprintf(out, "Block in Hand: %u\n", hand);
        fprintf(out, "h: %d\n", s.h);
	}

    Move getmove(Block from, Block to){
        return movelibrary[(from-1)*Nblocks + to-1];
    }

    Oper getmoveref(Block from, Block to) const {
#ifndef DEEP
        if(to == 0) to = from;
        to--;
		return (from-1)*(Nblocks) + to;
#else
		return (from-1)*(Nblocks+1) + to;
#endif
    }

	Cost pathcost(const std::vector<State>&, const std::vector<Oper>&);
private:
    // Number of blocks in the loaded instance (<= Nblocks, the compiled-in
    // capacity). Loops over real blocks use this; array sizes use the enum.
    unsigned int nblocks = Nblocks;
    Block init[Nblocks];
    Block goal[Nblocks];
#ifdef DEEP
    Move movelibrary[Nblocks*Nblocks + Nblocks+1] = {Move()};
#else
    Move movelibrary[Nblocks*Nblocks+1] = {Move()};
#endif

    Cost noop(Block above[], Block below[]) {
        Cost oop = 0;
        for(int i=0; i<Nblocks; i++){
            if(below[i] == 0){
                bool incorrect = false;
                Block current = i+1;
                while(current != 0){
                    if(!incorrect && below[current-1] != goal[current-1]) incorrect = true;
                    if(incorrect) oop++;
                    current = above[current-1];
                }
            }
        }
        return oop;
    }
};
