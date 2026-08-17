"""Pure-stdlib Hamming error-correcting code.

Grounded in the 3blue1brown transcript *"Hamming codes part 2: The one-line
implementation"* (https://www.youtube.com/watch?v=b3NxrZOu_CE). The key insight
from the video: the four parity-check results, read as 1s and 0s, literally spell
out the binary position of the flipped bit, so encoding/decoding collapse to a
tiny parity (XOR) computation rather than a binary-search algorithm.

Implemented here:
  - (7, 4) Hamming code: 4 data bits -> 7 codeword bits with parity bits at
    power-of-two positions (1, 2, 4). Single-bit error detection + correction.
  - ``reduce_xor`` parity helper (the ``enumerate + reduce(XOR)`` one-liner idea).
  - Generalized ``(2**r - 1, 2**r - r - 1)`` Hamming construction (Hamming(7,4),
    Hamming(15,11), Hamming(31,26)) with automatic parity-position placement.
  - Syndrome computation and single-bit-error position recovery.
"""

from __future__ import annotations

from functools import reduce
from typing import Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "HammingCode",
    "hamming_7_4",
    "reduce_xor",
    "parity_positions",
    "encode",
    "decode_correct",
]


def parity_positions(total_bits: int) -> List[int]:
    """Power-of-two positions (0-indexed) that hold parity bits.

    In a Hamming code of length ``total_bits``, parity bits live at indices
    0, 1, 3, 7, ... i.e. ``2**k - 1`` in 0-indexed space.
    """
    pos: List[int] = []
    k = 0
    while (1 << k) - 1 < total_bits:
        pos.append((1 << k) - 1)
        k += 1
    return pos


def reduce_xor(values: Iterable[int]) -> int:
    """XOR-reduce a sequence of 0/1 bits (the video's ``reduce(XOR)``)."""
    return reduce(lambda a, b: a ^ b, values, 0)


class HammingCode:
    """A systematic Hamming code of length ``n`` with ``k`` data bits.

    ``n`` must be of the form ``2**r - 1``; parity bits sit at power-of-two
    positions and every non-parity position holds one data bit.
    """

    def __init__(self, n: int) -> None:
        if n <= 0 or (n + 1) & n != 0:
            raise ValueError(f"n must be 2**r - 1 (got {n})")
        self.n = n
        r = n.bit_length()  # number of parity bits: n == 2**r - 1
        while (1 << r) - 1 != n:
            r += 1
        self.r = r
        self.k = n - r  # data bits
        self.parity = set(parity_positions(n))
        self.data_positions = [i for i in range(n) if i not in self.parity]

    # -- encoding ---------------------------------------------------------
    def encode(self, data: Sequence[int]) -> List[int]:
        """Encode ``k`` data bits into ``n`` codeword bits."""
        bits = [int(b) for b in data]
        if len(bits) != self.k:
            raise ValueError(f"expected {self.k} data bits, got {len(bits)}")
        code = [0] * self.n
        for bit, idx in zip(bits, self.data_positions):
            code[idx] = bit
        # set parity bits so that each parity group XORs to 0
        for p in sorted(self.parity):
            group = [
                i for i in range(self.n) if i != p and (i + 1) & (p + 1)
            ]
            code[p] = reduce_xor(code[i] for i in group)
        return code

    # -- syndrome / decode -------------------------------------------------
    def syndrome(self, code: Sequence[int]) -> int:
        """Return the 0-indexed error position, or 0 if no single-bit error.

        The parity-check results, read as a binary number, spell the position of
        the flipped bit (the video's central insight). A syndrome of 0 means no
        error detected.
        """
        bits = [int(b) for b in code]
        if len(bits) != self.n:
            raise ValueError(f"expected {self.n} codeword bits, got {len(bits)}")
        s = 0
        for p in sorted(self.parity):
            group = [i for i in range(self.n) if (i + 1) & (p + 1)]
            s |= reduce_xor(bits[i] for i in group) << ((p + 1).bit_length() - 1)
        return s

    def correct(self, code: Sequence[int]) -> List[int]:
        """Correct a single flipped bit and return the corrected codeword."""
        bits = [int(b) for b in code]
        pos = self.syndrome(bits)
        if pos:
            # syndrome is a 1-based position (bits read as the binary index)
            idx = pos - 1
            if 0 <= idx < len(bits):
                bits[idx] ^= 1
        return bits

    def decode(self, code: Sequence[int], fix: bool = True) -> List[int]:
        """Decode a codeword back to ``k`` data bits.

        If ``fix`` is True, first correct a single-bit error.
        """
        if fix:
            code = self.correct(code)
        bits = [int(b) for b in code]
        return [bits[i] for i in self.data_positions]

    def encode_bytes(self, data: int) -> List[int]:
        """Encode a single ``k``-bit integer into codeword bits."""
        bits = [(data >> i) & 1 for i in range(self.k - 1, -1, -1)]
        return self.encode(bits)

    # -- introspection -----------------------------------------------------
    @property
    def min_distance(self) -> int:
        """Minimum Hamming distance is 3 for Hamming codes."""
        return 3

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"HammingCode(n={self.n}, k={self.k}, r={self.r})"


def hamming_7_4() -> HammingCode:
    """Convenience factory for the classic (7,4) Hamming code."""
    return HammingCode(7)


# Module-level helpers operating on the default (7,4) code -------------------

_74 = hamming_7_4()


def encode(data: Sequence[int]) -> List[int]:
    """Encode 4 data bits into a 7-bit (7,4) Hamming codeword."""
    return _74.encode(data)


def decode_correct(code: Sequence[int]) -> List[int]:
    """Decode a 7-bit codeword to 4 data bits, correcting one flipped bit."""
    return _74.decode(code)
