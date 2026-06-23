// Copyright © 2026 the Search Authors under the MIT license. See AUTHORS for the list of authors.
//
// Ratchet Triangle Search: Triangle with a self-configuring slope. The slope is
// a persistent state, not a parameter: after each step it doubles when that
// step saw strictly more informed than uninformed layer-transitions (the
// expanded node's h fell relative to the previous expansion), and otherwise
// halves (floor 1). So the dive deepens while the heuristic keeps paying off
// and pulls back when it stops. One of two parameterless variants (cf.
// adaptive_triangle); shared machinery is in triangle_engine.hpp.
//
// Ported from src/search/search_algorithms/ratchet_triangle_search.cc (Scorpion).
#pragma once
#include "triangle_engine.hpp"
#include <algorithm>
#include <climits>

template <class D> struct RatchetTriangleSearch : public TriangleEngine<D> {
	typedef typename TriangleEngine<D>::Node Node;
	typedef typename D::Cost Cost;

	RatchetTriangleSearch(int argc, const char *argv[]) :
		TriangleEngine<D>(argc, argv) {
		slope = 1;	// initial slope; ratchets up/down from here
		liftfloor = false;
		for (int i = 0; i < argc; i++) {
			if (i < argc - 1 && strcmp(argv[i], "-slope") == 0)
				slope = atoi(argv[++i]);
			else if (strcmp(argv[i], "-liftfloor") == 0)
				liftfloor = true;
		}
		if (slope < 1)
			fatal("Must specify a >0 initial slope using -slope");
		initslope = slope;
	}

	virtual void output(FILE *out) {
		TriangleEngine<D>::output(out);
		dfpair(stdout, "initial slope", "%d", initslope);
		dfpair(stdout, "lift floor", "%s", liftfloor ? "true" : "false");
	}

protected:

	bool cascade(D &d) {
		const int cap = this->maxactive + slope;
		// Direction B (relaxed cascade start-depth): begin slope-1 layers below
		// the shallowest active layer (pinned to 0 by the front-drain) instead
		// of at the root. Clamped to maxactive so the deepest layer is still
		// served. liftfloor off (or slope 1) => start 0 == vanilla ratchet.
		const int start = liftfloor ? std::min(slope - 1, this->maxactive) : 0;

		Cost last_h = Cost(0);
		bool have_last = false;
		int informed = 0, uninformed = 0;

		for (int i = start; i < cap && !this->limit(); i++) {
			if (i >= (int) this->open.size())
				break;
			if (this->open[i].empty())
				continue;
			Node *n = this->popeligible(i);
			if (!n)
				continue;
			if (have_last) {
				if (n->h < last_h)
					++informed;
				else
					++uninformed;
			}
			last_h = n->h;
			have_last = true;
			if (this->expandnode(d, n, i + 1))
				return true;
		}

		// Ratchet: double on a step with more informed than uninformed
		// transitions, otherwise halve (floor 1). Guard doubling against
		// overflow but leave slope otherwise unbounded above.
		if (informed > uninformed) {
			if (slope < INT_MAX / 2)
				slope *= 2;
		} else {
			slope = std::max(1, slope / 2);
		}
		return false;
	}

	int slope;	// persistent, ratchets up/down each step
	int initslope;
	bool liftfloor;
};
