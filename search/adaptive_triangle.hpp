// Copyright © 2026 the Search Authors under the MIT license. See AUTHORS for the list of authors.
//
// Adaptive Triangle Search: Triangle whose per-step dive depth is set by a
// heuristic-trend budget instead of a slope parameter. Each step starts with
// budget 1; instantiating a new frontier layer costs one unit, an informed
// layer-transition (h falls relative to the previous expansion in the step)
// refunds one, and an uninformed transition debits `penalty` (default 1). The
// cascade dives until it can no longer afford the next layer. With penalty 0
// the dive runs through non-improving transitions as long as no new layer is
// needed -- the "parameterless" configuration. The primary parameterless
// variant (cf. ratchet_triangle); shared machinery is in triangle_engine.hpp.
//
// Ported from src/search/search_algorithms/adaptive_triangle_search.cc (Scorpion).
#pragma once
#include "triangle_engine.hpp"
#include <algorithm>
#include <cmath>

template <class D> struct AdaptiveTriangleSearch : public TriangleEngine<D> {
	typedef typename TriangleEngine<D>::Node Node;
	typedef typename D::Cost Cost;

	// Direction B floor proxy: how the lifted cascade start-depth is derived.
	enum FloorProxy { LAYERS_ADDED, INFORMEDNESS };

	AdaptiveTriangleSearch(int argc, const char *argv[]) :
		TriangleEngine<D>(argc, argv) {
		liftfloor = false;
		floorproxy = INFORMEDNESS;
		penalty = 1;
		for (int i = 0; i < argc; i++) {
			if (strcmp(argv[i], "-liftfloor") == 0)
				liftfloor = true;
			else if (i < argc - 1 && strcmp(argv[i], "-penalty") == 0)
				penalty = atoi(argv[++i]);
			else if (i < argc - 1 && strcmp(argv[i], "-floorproxy") == 0) {
				const char *v = argv[++i];
				if (strcmp(v, "layers_added") == 0)
					floorproxy = LAYERS_ADDED;
				else if (strcmp(v, "informedness") == 0)
					floorproxy = INFORMEDNESS;
				else
					fatal("Unknown -floorproxy: %s (informedness|layers_added)", v);
			}
		}
		if (penalty < 0)
			fatal("-penalty must be >= 0");
	}

	virtual void output(FILE *out) {
		TriangleEngine<D>::output(out);
		dfpair(stdout, "non progress penalty", "%d", penalty);
		dfpair(stdout, "lift floor", "%s", liftfloor ? "true" : "false");
		dfpair(stdout, "floor proxy", "%s",
			floorproxy == INFORMEDNESS ? "informedness" : "layers_added");
	}

	virtual void reset() {
		TriangleEngine<D>::reset();
		prev_layers_added = 0;
		improving = 0;
		nonimproving = 0;
	}

protected:

	// Start a fresh informedness epoch on genuine progress: the floor drops
	// back toward the root and re-climbs as the new epoch's heuristic quality
	// accrues.
	void on_incumbent_improved() {
		improving = 0;
		nonimproving = 0;
	}

	bool cascade(D &d) {
		int budget = 1;
		Cost last_h = Cost(0);
		bool have_last = false;

		// Direction B (relaxed cascade start-depth). Off => start 0 == vanilla
		// adaptive. The clamp keeps the deepest active layer served.
		int start = 0;
		if (liftfloor) {
			if (floorproxy == LAYERS_ADDED) {
				start = std::max(0, std::min(prev_layers_added - 1, this->maxactive));
			} else {
				int total = improving + nonimproving;
				if (total > 0) {
					long f = lround(
						(double) this->maxactive * improving / total);
					start = (int) std::max(0L,
						std::min((long) this->maxactive, f));
				}
			}
		}
		int layers_added = 0;

		for (int i = start; ; i++) {
			if (i >= (int) this->open.size())
				break;
			if (this->limit())
				break;
			if (this->open[i].empty())
				continue;

			// Find an expandable top without committing yet -- we don't pay the
			// frontier-extension cost until we know we have someone to expand.
			Node *n = this->peekeligible(i);
			if (!n)
				continue;

			// Ensure layer i+1 exists to receive successors; free if already in
			// the deque, otherwise pay one budget unit. If we can't afford it,
			// halt with the expandable entry still in place for the next step.
			if (i + 1 >= (int) this->open.size()) {
				if (budget <= 0)
					break;
				--budget;
				this->growback();
				++layers_added;
			}

			this->popcurrent(i);

			if (have_last) {
				if (n->h < last_h) {
					++budget;
					++improving;
				} else {
					budget -= penalty;
					++nonimproving;
				}
			}
			last_h = n->h;
			have_last = true;

			if (this->expandnode(d, n, i + 1))
				return true;
		}

		// Carry this step's realized dive depth to drive next step's lift_floor.
		prev_layers_added = layers_added;
		return false;
	}

	int penalty;	// budget debit per uninformed transition (0 => parameterless)
	bool liftfloor;
	FloorProxy floorproxy;

	// Number of new frontier layers the previous step instantiated -- the
	// emergent analog of ratchet's persistent slope; drives LAYERS_ADDED.
	int prev_layers_added = 0;
	// Improving / non-improving h-transition counts for INFORMEDNESS. Persistent
	// across steps, reset on each incumbent improvement.
	int improving = 0;
	int nonimproving = 0;
};
