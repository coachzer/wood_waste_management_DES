"""Failure counts live on each entity, so runs and entities never share them."""
from models.data_classes import FailureConfig, OperationalEntity

CERTAIN_FAILURE = FailureConfig(probability=1.0, min_duration=1.0, max_duration=1.0)


def test_a_failure_counts_only_against_the_entity_that_failed():
    failed_entity = OperationalEntity(failure_config=CERTAIN_FAILURE, seed=1)
    untouched_entity = OperationalEntity(failure_config=CERTAIN_FAILURE, seed=2)

    failed_entity.check_failure(current_time=1.0, failure_probability=1.0)

    assert failed_entity.failure_count == 1
    assert untouched_entity.failure_count == 0


def test_a_new_entity_starts_with_no_failures_after_another_has_failed():
    OperationalEntity(failure_config=CERTAIN_FAILURE, seed=1).check_failure(1.0, 1.0)

    assert OperationalEntity(failure_config=CERTAIN_FAILURE, seed=3).failure_count == 0
