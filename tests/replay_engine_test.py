import pytest

from simulation.core.event import Event
from simulation.core.reducer import Reducer
from simulation.core.state import State
from simulation.replay.replay_engine import ReplayEngine


def make_engine():

    return ReplayEngine(
        reducer=Reducer()
    )


def make_question_events(count):

    return tuple(
        Event(
            event_type="UserQuestionReceived",
            payload={"prompt": f"q{index}"},
            sequence=index + 1,
        )
        for index in range(count)
    )


def test_empty_event_stream_produces_initial_state():

    state = make_engine().replay(
        events=()
    )

    assert isinstance(state, State)

    assert state.event_counter == 0

    assert state.tasks == {}

    assert state.workers == {}

    assert state.memory == {}

    assert state.conversation_history == []

    assert state.worker_trace == []


def test_known_event_sequence_produces_expected_state():

    events = make_question_events(3)

    state = make_engine().replay(
        events=events
    )

    assert state.event_counter == 3

    assert state.conversation_history == [
        {"role": "user", "content": "q0"},
        {"role": "user", "content": "q1"},
        {"role": "user", "content": "q2"},
    ]


def test_replaying_identical_events_twice_produces_equivalent_state():

    events = make_question_events(2)

    engine = make_engine()

    first = engine.replay(events=events)

    second = engine.replay(events=events)

    assert first.event_counter == second.event_counter

    assert (
        first.conversation_history
        == second.conversation_history
    )

    assert first.to_dict() == second.to_dict()


def test_replay_does_not_mutate_event_history():

    events = make_question_events(2)

    before = tuple(
        (event.event_type, event.payload, event.sequence)
        for event in events
    )

    make_engine().replay(
        events=events
    )

    after = tuple(
        (event.event_type, event.payload, event.sequence)
        for event in events
    )

    assert after == before


def test_replay_starts_from_supplied_initial_state():

    events = make_question_events(1)

    state = make_engine().replay(
        events=events,
        initial_state=State(
            event_counter=10
        ),
    )

    assert state.event_counter == 11

    assert state.conversation_history == [
        {"role": "user", "content": "q0"},
    ]


def test_invalid_event_stream_raises():

    with pytest.raises(TypeError):

        make_engine().replay(
            events=None
        )
