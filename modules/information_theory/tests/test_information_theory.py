"""Tests for the information_theory module.

Known-value checks grounded in the source transcripts:
  * fair coin entropy = 1.0 bit; certain outcome = 0.0 bits (StatQuest)
  * MI of independent variables ~ 0 bits (StatQuest)
  * KL(p || p) = 0 bits
  * wordle_feedback('crane','crane') is all-green (3blue1brown)
  * best_guess prefers the higher-entropy guess
"""

from __future__ import annotations

import math

import pytest

from enterprise.modules.information_theory import (
    GRAY,
    GREEN,
    YELLOW,
    InformationTheoryModule,
    best_guess,
    conditional_entropy,
    create_information_theory_module,
    entropy_from_counts,
    expected_information_gain,
    joint_entropy,
    kl_divergence,
    mutual_information,
    pattern_distribution,
    shannon_entropy,
    surprise,
    wordle_feedback,
)


# -- surprise & entropy -----------------------------------------------------

def test_surprise_certain_is_zero():
    assert surprise(1.0) == 0.0


def test_surprise_half_is_one_bit():
    assert surprise(0.5) == pytest.approx(1.0)


def test_surprise_rarer_is_larger():
    assert surprise(0.1) > surprise(0.9)


def test_surprise_invalid():
    with pytest.raises(ValueError):
        surprise(0.0)
    with pytest.raises(ValueError):
        surprise(1.5)


def test_fair_coin_entropy_is_one_bit():
    assert shannon_entropy([0.5, 0.5]) == pytest.approx(1.0)


def test_certain_outcome_entropy_is_zero():
    assert shannon_entropy([1.0, 0.0]) == pytest.approx(0.0)


def test_uniform_four_outcomes_two_bits():
    assert shannon_entropy([0.25, 0.25, 0.25, 0.25]) == pytest.approx(2.0)


def test_entropy_rejects_bad_sum():
    with pytest.raises(ValueError):
        shannon_entropy([0.5, 0.2])


def test_entropy_from_counts_fair_coin():
    assert entropy_from_counts([50, 50]) == pytest.approx(1.0)


def test_entropy_from_counts_empty_is_zero():
    assert entropy_from_counts([]) == 0.0


# -- mutual information & conditional entropy -------------------------------

def _independent_joint():
    # P(x)=[0.5,0.5], P(y)=[0.5,0.5], independent => P(x,y)=0.25 each.
    return {
        ("a", 0): 0.25,
        ("a", 1): 0.25,
        ("b", 0): 0.25,
        ("b", 1): 0.25,
    }


def _perfectly_dependent_joint():
    # Y is a deterministic copy of X.
    return {
        ("a", 0): 0.5,
        ("b", 1): 0.5,
    }


def test_mi_independent_is_zero():
    assert mutual_information(_independent_joint()) == pytest.approx(0.0, abs=1e-12)


def test_mi_dependent_equals_marginal_entropy():
    # When Y copies X, MI = H(X) = 1 bit for a balanced binary X.
    assert mutual_information(_perfectly_dependent_joint()) == pytest.approx(1.0)


def test_conditional_entropy_dependent_is_zero():
    # Knowing Y fully determines X.
    assert conditional_entropy(_perfectly_dependent_joint()) == pytest.approx(0.0, abs=1e-12)


def test_conditional_entropy_independent_equals_hx():
    # Independent => H(X|Y) = H(X) = 1 bit.
    assert conditional_entropy(_independent_joint()) == pytest.approx(1.0)


def test_mi_equals_hx_minus_h_x_given_y():
    joint = {
        ("a", 0): 0.4,
        ("a", 1): 0.1,
        ("b", 0): 0.2,
        ("b", 1): 0.3,
    }
    # MI(X;Y) = H(X) - H(X|Y). Compute H(X) from marginals.
    px = [0.4 + 0.1, 0.2 + 0.3]
    hx = shannon_entropy(px)
    assert mutual_information(joint) == pytest.approx(hx - conditional_entropy(joint))


def test_joint_entropy_uniform():
    assert joint_entropy(_independent_joint()) == pytest.approx(2.0)


# -- KL divergence ----------------------------------------------------------

def test_kl_self_is_zero():
    p = [0.2, 0.3, 0.5]
    assert kl_divergence(p, p) == pytest.approx(0.0, abs=1e-12)


def test_kl_nonnegative():
    p = [0.9, 0.1]
    q = [0.5, 0.5]
    assert kl_divergence(p, q) > 0.0


def test_kl_undefined_when_q_zero():
    with pytest.raises(ValueError):
        kl_divergence([0.5, 0.5], [1.0, 0.0])


# -- Wordle feedback & information gain -------------------------------------

def test_wordle_all_green_on_match():
    assert wordle_feedback("crane", "crane") == (GREEN, GREEN, GREEN, GREEN, GREEN)


def test_wordle_all_gray_on_disjoint():
    assert wordle_feedback("fizzy", "crumb") == (GRAY, GRAY, GRAY, GRAY, GRAY)


def test_wordle_yellow_wrong_position():
    # guess 'brick' vs answer 'crumb': b present(elsewhere)->yellow, r green, etc.
    fb = wordle_feedback("brick", "crumb")
    assert fb[1] == GREEN  # 'r' matches position 1 in 'crumb'
    assert fb[0] == YELLOW  # 'b' present elsewhere


def test_wordle_multiplicity():
    # one 'l' in answer, two in guess: only one yellow/green awarded.
    fb = wordle_feedback("llama", "ample")
    greens_yellows = [t for t in fb if t in (GREEN, YELLOW)]
    # 'a' and one 'l' and 'm' should be colored; second 'l' gray.
    assert fb.count(GRAY) >= 1


def test_wordle_length_mismatch():
    with pytest.raises(ValueError):
        wordle_feedback("cat", "mouse")


def test_pattern_distribution_sums_to_n():
    poss = ["crane", "slate", "trace", "grace"]
    dist = pattern_distribution("crane", poss)
    assert sum(dist.values()) == len(poss)


def test_eig_zero_on_single_possibility():
    assert expected_information_gain("crane", ["crane"]) == 0.0


def test_eig_nonnegative():
    poss = ["crane", "slate", "trace", "grace", "brace"]
    assert expected_information_gain("slate", poss) >= 0.0


def test_best_guess_picks_higher_entropy():
    # A guess that splits possibilities into distinct patterns gains more info
    # than one that lumps them together.
    poss = ["aaaaa", "bbbbb", "ccccc", "ddddd"]
    # 'abcde' produces a distinct pattern vs each answer -> max entropy (2 bits).
    # 'zzzzz' produces all-gray for every answer -> 0 bits.
    high = expected_information_gain("abcde", poss)
    low = expected_information_gain("zzzzz", poss)
    assert high > low
    assert best_guess(["zzzzz", "abcde"], poss) == "abcde"


def test_best_guess_requires_candidates():
    with pytest.raises(ValueError):
        best_guess([], ["crane"])


# -- module lifecycle -------------------------------------------------------

async def test_module_initialize_healthy():
    m = create_information_theory_module()
    await m.initialize()
    assert (await m.health_check()).value == "healthy"


async def test_module_facade_entropy():
    m = create_information_theory_module()
    await m.initialize()
    assert m.entropy([0.5, 0.5]) == pytest.approx(1.0)
    assert m.surprise(0.5) == pytest.approx(1.0)


async def test_module_facade_mi_and_kl():
    m = create_information_theory_module()
    await m.initialize()
    assert m.mutual_information(_independent_joint()) == pytest.approx(0.0, abs=1e-12)
    assert m.kl_divergence([0.5, 0.5], [0.5, 0.5]) == pytest.approx(0.0, abs=1e-12)


async def test_module_facade_wordle():
    m = create_information_theory_module()
    await m.initialize()
    assert m.wordle_feedback("crane", "crane") == (GREEN, GREEN, GREEN, GREEN, GREEN)
    poss = ["aaaaa", "bbbbb", "ccccc", "ddddd"]
    assert m.best_guess(["zzzzz", "abcde"], poss) == "abcde"


async def test_module_health_check_and_shutdown():
    m = create_information_theory_module()
    await m.initialize()
    assert (await m.health_check()).value == "healthy"
    await m.shutdown()
    assert (await m.health_check()).value == "stopping"


def test_module_event_bus_optional():
    # Publishing is a no-op without an event bus (must not raise).
    m = InformationTheoryModule()
    m._publish("x", {"a": 1})


def test_module_set_event_bus_publishes():
    published = []

    class FakeBus:
        def publish(self, event):
            published.append(event)

    m = InformationTheoryModule()
    m.set_event_bus(FakeBus())
    m.entropy([0.5, 0.5])
    assert len(published) == 1
