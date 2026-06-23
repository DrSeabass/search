// Copyright © 2026 the Search Authors under the MIT license. See AUTHORS for the list of authors.
//
// Triangle Search: an anytime, depth-striated beam search. Each step cascades
// from the frontier up to (max active layer + slope), expanding at most one
// node per layer; successors of a layer-i node go into layer i+1, tracing out
// the triangular expansion profile that names the algorithm. The slope is a
// fixed parameter here; the adaptive_triangle and ratchet_triangle variants
// choose it automatically. Shared machinery lives in triangle_engine.hpp.
//
// Reference: Lemons, Ruml, Linares López, Holte. "Triangle Search: An Anytime
// Beam Search." ICAPS 2023 HSDIP Workshop (arXiv:2312.12554).
#pragma once
#include "triangle_engine.hpp"

template <class D> struct TriangleSearch : public TriangleEngine<D> {
	typedef typename TriangleEngine<D>::Node Node;

	TriangleSearch(int argc, const char *argv[]) :
		TriangleEngine<D>(argc, argv) {
		slope = 1;
		for (int i = 0; i < argc; i++) {
			if (i < argc - 1 && strcmp(argv[i], "-slope") == 0)
				slope = atoi(argv[++i]);
		}
		if (slope < 1)
			fatal("Must specify a >0 slope using -slope");
	}

	virtual void output(FILE *out) {
		TriangleEngine<D>::output(out);
		dfpair(stdout, "slope", "%d", slope);
	}

protected:

	// Fixed-slope cascade: dive a constant `slope` layers past the frontier.
	bool cascade(D &d) {
		const int cap = this->maxactive + slope;
		for (int i = 0; i < cap && !this->limit(); i++) {
			if (i >= (int) this->open.size())
				break;
			if (this->open[i].empty())
				continue;
			Node *n = this->popeligible(i);
			if (!n)
				continue;
			if (this->expandnode(d, n, i + 1))
				return true;
		}
		return false;
	}

	int slope;
};
