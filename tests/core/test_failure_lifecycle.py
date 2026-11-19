"""Failure lifecycle runs on a daily clock, independent of the main-loop cadence.

``FailureConfig.probability`` is documented (and reported in the paper) as a
daily rate. It used to be rolled once per main-loop tick, so a treatment
operator (``processing_time`` = 24 days) failed ~1/24 as often as stated, and
the configured duration never set the FAILED outage (fixed at 1 day). These
tests pin the daily semantics, the configured outage length, the zero
throughput of a FAILED entity, and the policy-invariance of the failure stream.
"""

import simpy

from models.data_classes import FailureConfig, OperationalEntity
from models.enums import EntityStatus


class _ClockedEntity(OperationalEntity):
    """An OperationalEntity with a coarse main loop, like a treatment operator.

    ``loop_period`` mimics ``processing_time``; the loop only reads status. It
    also optionally burns draws on ``rng`` each tick to emulate policy-dependent
    RNG consumption in the real entities.
    """

    def __init__(self, env, failure_config, seed, loop_period, rng_draws_per_tick=0):
        super().__init__(failure_config=failure_config, seed=seed)
        self.env = env
        self.loop_period = loop_period
        self.rng_draws_per_tick = rng_draws_per_tick
        self.failure_days = []
        env.process(self._main_loop())
        self.start_failure_process(env)

    def check_failure(self, current_time, failure_probability):
        was_operational = self.status == EntityStatus.OPERATIONAL
        failed = super().check_failure(current_time, failure_probability)
        if was_operational and failed:
            self.failure_days.append(current_time)
        return failed

    def _main_loop(self):
        while True:
            self.apply_failure_tick()
            for _ in range(self.rng_draws_per_tick):
                self.rng.random()
            yield self.env.timeout(self.loop_period)


def _run(entity_kwargs, days):
    env = simpy.Environment()
    entity = _ClockedEntity(env, **entity_kwargs)
    env.run(until=days)
    return entity


def test_failure_rate_is_daily_regardless_of_main_loop_cadence():
    """A 24-day main loop must not dilute a daily failure probability.

    With p = 0.05/day and a fixed 1-day outage + 1-day ramp, each failure
    removes two non-rolling days, so over 3650 days the expected count is
    3650 / (1/0.05 + 2) ~= 166.

    Mutation check (red): roll the failure inside ``apply_failure_tick`` again
    (once per 24-day tick) -> ~7 failures, far below the band.
    """
    config = FailureConfig(probability=0.05, min_duration=1.0, max_duration=1.0)
    entity = _run(dict(failure_config=config, seed=7, loop_period=24.0), days=3650)

    assert 120 < len(entity.failure_days) < 215, len(entity.failure_days)


def test_failure_can_start_between_main_loop_ticks():
    """Failures land on the daily clock, not only on main-loop wake-ups.

    Mutation check (red): drop ``start_failure_process`` -> no failures at all.
    """
    config = FailureConfig(probability=1.0, min_duration=1.0, max_duration=1.0)
    entity = _run(dict(failure_config=config, seed=0, loop_period=24.0), days=5)

    assert entity.failure_days[0] == 1.0


def test_failed_outage_length_comes_from_failure_config():
    """FAILED lasts the configured duration, not a hardcoded one day.

    Mutation check (red): remove the ``downtime_duration`` draw in
    ``check_failure`` -> the default 1.0-day outage ends on day 2.
    """
    config = FailureConfig(probability=1.0, min_duration=5.0, max_duration=5.0)

    still_failed = _run(dict(failure_config=config, seed=0, loop_period=24.0), days=5.5)
    assert still_failed.status == EntityStatus.FAILED  # failed on day 1, outage to day 6

    recovering = _run(dict(failure_config=config, seed=0, loop_period=24.0), days=6.5)
    assert recovering.status == EntityStatus.RECOVERING


def test_failed_entity_has_zero_operational_efficiency():
    """A FAILED entity does no work (its tick is skipped), so efficiency is 0.

    Mutation check (red): return the old 0.1 floor for FAILED -> 0.1 != 0.0.
    """
    entity = OperationalEntity(seed=0)
    entity.status = EntityStatus.FAILED

    assert entity.get_operational_efficiency() == 0.0


def test_failure_history_is_invariant_to_policy_rng_consumption():
    """Same seed, different policy-driven RNG use -> identical failure days (CRN).

    Mutation check (red): draw failures from ``self.rng`` instead of
    ``self.policy_independent_failure_rng`` -> the extra main-loop draws shift the failure days.
    """
    config = FailureConfig(probability=0.1, min_duration=0.5, max_duration=2.0)
    quiet = _run(dict(failure_config=config, seed=11, loop_period=3.0), days=365)
    noisy = _run(
        dict(failure_config=config, seed=11, loop_period=3.0, rng_draws_per_tick=5),
        days=365,
    )

    assert quiet.failure_days  # non-vacuous: failures actually happened
    assert quiet.failure_days == noisy.failure_days
