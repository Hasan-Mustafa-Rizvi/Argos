"""Every path in the contract's diagram, with time passed in by hand."""

from __future__ import annotations

import pytest

from argos.machine import (
    Acknowledged,
    Asked,
    Escalated,
    Ignored,
    Machine,
    Opened,
    State,
    StoodDown,
)


def open_check(machine: Machine, now: float = 0.0, trigger: str = "fall") -> str:
    effects = machine.trigger(trigger, 0.9, "inc-1", now)
    assert isinstance(effects[0], Opened)
    return "inc-1"


def test_trigger_opens_a_check() -> None:
    machine = Machine(10)
    effects = machine.trigger("help_call", 0.84, "inc-1", 0.0)
    assert machine.state is State.CHECKING
    assert effects == [Opened(machine.check)]
    assert machine.check.confidence == 0.84


def test_manual_trigger_has_no_confidence() -> None:
    machine = Machine(10)
    machine.trigger("manual", 0.7, "inc-1", 0.0)
    assert machine.check.confidence is None


def test_unknown_trigger_is_ignored() -> None:
    machine = Machine(10)
    effects = machine.trigger("earthquake", 1.0, "inc-1", 0.0)
    assert isinstance(effects[0], Ignored)
    assert machine.state is State.CALM


def test_stand_down_by_voice() -> None:
    machine = Machine(10)
    open_check(machine)
    machine.asked("inc-1", 0.5)
    effects = machine.answer("voice", "I'm fine", 3.0)
    assert effects == [StoodDown("inc-1", "voice", "I'm fine")]
    assert machine.state is State.CALM
    assert machine.check is None


def test_stand_down_by_pat() -> None:
    machine = Machine(10)
    open_check(machine)
    machine.asked("inc-1", 0.5)
    assert machine.answer("pat", None, 2.0) == [StoodDown("inc-1", "pat", None)]
    assert machine.state is State.CALM


def test_wait_starts_when_asked_not_at_trigger() -> None:
    machine = Machine(10)
    open_check(machine, now=0.0)
    assert machine.deadline is None
    assert machine.tick(7.0) == []  # 7 s after the trigger and still waiting to ask
    machine.asked("inc-1", 5.0)
    assert machine.deadline == 15.0
    assert machine.tick(14.9) == []
    assert machine.state is State.CHECKING


def test_escalates_at_exactly_the_timeout() -> None:
    machine = Machine(10)
    open_check(machine)
    machine.asked("inc-1", 0.5)
    assert machine.tick(10.4999) == []
    effects = machine.tick(10.5)
    assert effects == [Escalated("inc-1", "fall")]
    assert machine.state is State.ALERT


def test_timeout_is_a_setting() -> None:
    machine = Machine(3)
    open_check(machine)
    machine.asked("inc-1", 0.0)
    assert machine.tick(2.99) == []
    assert isinstance(machine.tick(3.0)[0], Escalated)


def test_question_never_reported_counts_as_asked_after_grace() -> None:
    machine = Machine(10, ask_grace_s=8.0)
    open_check(machine, now=0.0)
    effects = machine.tick(8.0)
    assert effects == [Asked("inc-1", late=True)]
    assert machine.deadline == 18.0
    assert isinstance(machine.tick(18.0)[0], Escalated)


def test_acknowledge_returns_to_calm() -> None:
    machine = Machine(10)
    open_check(machine)
    machine.asked("inc-1", 0.0)
    machine.tick(10.0)
    effects = machine.acknowledge("Daughter", "2026-11-15T19:01:10.000Z", False, 30.0)
    assert effects == [Acknowledged("inc-1", "Daughter", "2026-11-15T19:01:10.000Z", False)]
    assert machine.state is State.CALM


@pytest.mark.parametrize("by", ["voice", "pat"])
def test_in_alert_an_answer_or_pat_changes_nothing(by: str) -> None:
    machine = Machine(10)
    open_check(machine)
    machine.asked("inc-1", 0.0)
    machine.tick(10.0)
    effects = machine.answer(by, "I'm fine", 11.0)
    assert isinstance(effects[0], Ignored)
    assert machine.state is State.ALERT
    assert machine.incident_id == "inc-1"


def test_trigger_during_check_opens_no_second_incident() -> None:
    machine = Machine(10)
    open_check(machine)
    machine.asked("inc-1", 0.0)
    effects = machine.trigger("help_call", 0.9, "inc-2", 5.0)
    assert isinstance(effects[0], Ignored)
    assert machine.incident_id == "inc-1"
    assert machine.deadline == 10.0  # the wait is not extended


def test_trigger_during_alert_opens_no_second_incident() -> None:
    machine = Machine(10)
    open_check(machine)
    machine.asked("inc-1", 0.0)
    machine.tick(10.0)
    effects = machine.trigger("fall", 0.9, "inc-2", 12.0)
    assert isinstance(effects[0], Ignored)
    assert machine.state is State.ALERT
    assert machine.incident_id == "inc-1"


def test_acknowledge_without_alert_is_ignored() -> None:
    machine = Machine(10)
    assert isinstance(machine.acknowledge("Demo", None, True, 0.0)[0], Ignored)
    open_check(machine)
    assert isinstance(machine.acknowledge("Demo", None, True, 0.0)[0], Ignored)
    assert machine.state is State.CHECKING


def test_asked_for_another_incident_is_ignored() -> None:
    machine = Machine(10)
    open_check(machine)
    assert machine.asked("someone-else", 1.0) == []
    assert machine.deadline is None


def test_resume_alert_and_resume_check() -> None:
    machine = Machine(10)
    machine.resume_alert("old", "fall", 0.9)
    assert machine.state is State.ALERT
    assert isinstance(machine.acknowledge("Daughter", None, False, 0.0)[0], Acknowledged)
    effects = machine.resume_check("old-2", "help_call", None, 5.0)
    assert isinstance(effects[0], Opened)
    assert machine.state is State.CHECKING
