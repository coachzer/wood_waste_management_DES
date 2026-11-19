"""``make_collector`` must not register a throwaway transport manager over the caller's."""
import simpy

from core.transport_manager import PointToPointTransport
from models.state import SimulationState
from tests.core.factories import make_collector


def test_the_callers_transport_manager_stays_on_the_state(noop_waste_monitor):
    env = simpy.Environment()
    state = SimulationState()
    transport_manager = PointToPointTransport(state=state, road_circuity_mean=1.0, env=env)

    make_collector(env, noop_waste_monitor, state=state, transport_manager=transport_manager)

    assert state.transport_manager is transport_manager
