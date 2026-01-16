// Copyright © 2013 the Search Authors under the MIT license. See AUTHORS for the list of authors.
#include <cassert>
#include <boost/cstdint.hpp>
#include <boost/integer/static_log2.hpp>
#include <boost/multiprecision/cpp_int.hpp>

void fatal(const char*, ...);
extern "C" unsigned long hashbytes(unsigned char[], unsigned int);

class Tiles;

template<int Ntiles> class PackedTiles {
	friend class Tiles;

	enum {
		Nbits = boost::static_log2<Ntiles>::value,
		Nbytes = (int) ((Nbits / 8.0) * Ntiles),
	};

	unsigned char bytes[Nbytes];

public:

	void pack(Tiles::Tile ts[]) {
		fatal("Tiles::pack is unimplemented");
	}

	Tiles::Pos unpack(Tiles::Tile ts[]) {
		fatal("Tiles::unpack is unimplemented");
		return 0;
	}

	Tiles::Pos unpack_md(const unsigned int md[][Ntiles], const Tiles::Cost costs[], Tiles::Tile ts[], Tiles::Cost *h, int *d) {
		*h = 0;
		*d = 0;
		fatal("Tiles::unpack_md is unimplemented");
		return 0;
	}

	unsigned long hash(const void*) {
		return hashbytes(bytes, sizeof(bytes));
	}

	bool eq(const void*, PackedTiles &o) const {
		return memcmp(bytes, o.bytes, sizeof(bytes)) == 0;
	}
};

template<int Ntiles> class PackedTiles64 {
	friend class Tiles;

	boost::uint64_t word;

public:

	void pack(Tiles::Tile ts[]) {
		word = 0;
		for (int i = 0; i < Ntiles; i++)
			word = (word << 4) | ts[i];
	}

	Tiles::Pos unpack(Tiles::Tile ts[]) {
		int b;
		boost::uint64_t w = word;
		for (int i = Ntiles - 1; i >= 0; i--) {
			Tiles::Tile t = w & 0xF;
			w >>= 4;
			ts[i] = t;
			if (t == 0)
				b = i;
		}
		return b;
	}

	Tiles::Pos unpack_md(const unsigned int md[][Ntiles], const Tiles::Cost costs[], Tiles::Tile ts[], Tiles::Cost *hp, int *dp) {
		int b = -1;
		Tiles::Cost h = 0;
		int d = 0;
		boost::uint64_t w = word;
		for (int i = Ntiles - 1; i >= 0; i--) {
			Tiles::Tile t = w & 0xF;
			w >>= 4;
			ts[i] = t;
			if (t == 0)
				b = i;
			else {
				h += costs[t] * md[t][i];
				d += md[t][i];
			}
		}
		*hp = h;
		*dp = d;
		return b;
	}

	unsigned long hash(const void*) {
		return word;
	}

	bool eq(const void*, const PackedTiles64 &o) const {
		return word == o.word;
	}
};

template<> class PackedTiles<16> : public PackedTiles64<16> {
};

template<> class PackedTiles<12> : public PackedTiles64<12> {
};

template<> class PackedTiles<9> : public PackedTiles64<9> {
};

template<int Ntiles> class PackedTiles128 {
	friend class Tiles;

	boost::multiprecision::uint128_t word;

public:

	void pack(Tiles::Tile ts[]) {
		word = 0;
		for (int i = 0; i < Ntiles; i++)
			word = (word << 5) | ts[i];
	}

	Tiles::Pos unpack(Tiles::Tile ts[]) {
		int b;
		boost::multiprecision::uint128_t w = word;
		for (int i = Ntiles - 1; i >= 0; i--) {
			Tiles::Tile t = (Tiles::Tile)(w & 0x1F);
			w >>= 5;
			ts[i] = t;
			if (t == 0)
				b = i;
		}
		return b;
	}

	Tiles::Pos unpack_md(const unsigned int md[][Ntiles], const Tiles::Cost costs[], Tiles::Tile ts[], Tiles::Cost *hp, int *dp) {
		int b = -1;
		Tiles::Cost h = 0;
		int d = 0;
		boost::multiprecision::uint128_t w = word;
		for (int i = Ntiles - 1; i >= 0; i--) {
			Tiles::Tile t = (Tiles::Tile)(w & 0x1F);
			w >>= 5;
			ts[i] = t;
			if (t == 0)
				b = i;
			else {
				h += costs[t] * md[t][i];
				d += md[t][i];
			}
		}
		*hp = h;
		*dp = d;
		return b;
	}

	unsigned long hash(const void*) {
		std::hash<boost::multiprecision::uint128_t> hasher;
		return hasher(word);
	}

	bool eq(const void*, const PackedTiles128 &o) const {
		return word == o.word;
	}
};

template<> class PackedTiles<25> : public PackedTiles128<25> {
};
