"""Tests for the error_correction (Hamming) module."""

from __future__ import annotations

import pytest

from enterprise.modules.error_correction import (
    ErrorCorrectionModule,
    HammingCode,
    create_error_correction_module,
    decode_correct,
    encode,
    hamming_7_4,
    parity_positions,
    reduce_xor,
)


def test_parity_positions():
    assert parity_positions(7) == [0, 1, 3]
    assert parity_positions(15) == [0, 1, 3, 7]


def test_reduce_xor():
    assert reduce_xor([0, 0, 0]) == 0
    assert reduce_xor([1, 0, 1]) == 0
    assert reduce_xor([1, 1, 1]) == 1
    assert reduce_xor([]) == 0


def test_hamming_dimensions():
    c = hamming_7_4()
    assert c.n == 7
    assert c.k == 4
    assert c.r == 3
    assert c.min_distance == 3
    assert c.data_positions == [2, 4, 5, 6]


@pytest.mark.parametrize("data", [
    [0, 0, 0, 0],
    [1, 1, 1, 1],
    [0, 1, 0, 1],
    [1, 0, 0, 1],
    [1, 1, 0, 0],
    [0, 0, 1, 1],
])
def test_round_trip(data):
    code = encode(data)
    assert len(code) == 7
    assert decode_correct(code) == data


def test_parity_groups_even():
    # Every parity group must XOR to 0 (even parity).
    c = hamming_7_4()
    for data in ([1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]):
        code = c.encode(data)
        # group for parity at index 0 (bit 1): positions 1,3,5
        assert reduce_xor(code[i] for i in (0, 2, 4, 6)) == 0
        # group for parity at index 1 (bit 2): positions 2,3,6
        assert reduce_xor(code[i] for i in (1, 2, 5, 6)) == 0
        # group for parity at index 3 (bit 4): positions 4,5,6
        assert reduce_xor(code[i] for i in (3, 4, 5, 6)) == 0


@pytest.mark.parametrize("bit_index", range(7))
def test_single_bit_flip_corrected(bit_index):
    data = [1, 0, 1, 1]
    code = encode(data)
    corrupted = list(code)
    corrupted[bit_index] ^= 1
    # decode with fix=True must recover original data
    assert decode_correct(corrupted) == data


def test_syndrome_points_to_error():
    c = hamming_7_4()
    data = [1, 1, 0, 1]
    code = c.encode(data)
    # flip a message bit at index 4
    corrupted = list(code)
    corrupted[4] ^= 1
    # syndrome is 1-based index of the error: index 4 -> 5
    assert c.syndrome(corrupted) == 5
    # flip a parity bit at index 0 -> syndrome 1
    corrupted2 = list(code)
    corrupted2[0] ^= 1
    assert c.syndrome(corrupted2) == 1


def test_no_error_syndrome_zero():
    c = hamming_7_4()
    code = c.encode([0, 1, 1, 0])
    assert c.syndrome(code) == 0


def test_double_error_not_corrected():
    # Two flipped bits produce a syndrome pointing at a wrong location; the
    # code cannot be trusted (Hamming(7,4) only corrects single-bit errors).
    c = hamming_7_4()
    data = [1, 0, 0, 0]
    code = c.encode(data)
    corrupted = list(code)
    corrupted[2] ^= 1
    corrupted[5] ^= 1
    # should not equal the original data
    assert c.decode(corrupted, fix=True) != data


def test_general_hamming_15_11():
    c = HammingCode(15)
    assert c.k == 11
    assert c.r == 4
    data = [1, 0] * 5 + [1]
    code = c.encode(data)
    assert c.decode(code) == data
    corrupted = list(code)
    corrupted[9] ^= 1
    assert c.decode(corrupted, fix=True) == data


def test_invalid_length_rejected():
    with pytest.raises(ValueError):
        HammingCode(8)
    with pytest.raises(ValueError):
        HammingCode(0)


def test_encode_wrong_len_rejected():
    with pytest.raises(ValueError):
        encode([1, 0, 0])  # only 3 data bits


def test_encode_bytes():
    c = hamming_7_4()
    # data 0b1011 = 11 -> bits [1,0,1,1]
    code = c.encode_bytes(11)
    assert code[:3] == [0, 1, 1]  # parity positions 0,1,3
    assert code[2] == 1
    assert c.decode(code) == [1, 0, 1, 1]


# -- module lifecycle -------------------------------------------------------

async def test_module_initialize_healthy():
    m = create_error_correction_module()
    await m.initialize()
    assert m.dimensions == {"n": 7, "k": 4, "r": 3}
    assert m.stats()["min_distance"] == 3


async def test_module_encode_decode():
    m = create_error_correction_module()
    await m.initialize()
    code = m.encode([1, 0, 1, 0])
    corrupted = list(code)
    corrupted[3] ^= 1
    assert m.decode(corrupted) == [1, 0, 1, 0]


async def test_module_health_check_and_shutdown():
    m = create_error_correction_module()
    await m.initialize()
    assert (await m.health_check()).value == "healthy"
    await m.shutdown()
    assert (await m.health_check()).value == "stopping"
