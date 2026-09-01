"""Predicates shared by complex-event definitions."""

from collections import deque

from fsm import Observation


def label_count(label: str, minimum: int = 1):
    wanted = label.casefold()
    return lambda observation: sum(x.casefold() == wanted for x in observation.labels) >= minimum


def label_contains(text: str):
    wanted = text.casefold()
    return lambda observation: any(wanted in x.casefold() for x in observation.labels)


def label_any(*labels: str):
    wanted = {label.casefold() for label in labels}
    return lambda observation: any(x.casefold() in wanted for x in observation.labels)


def gunshot_like(observation: Observation) -> bool:
    # Cap-gun is intentionally excluded: YAMNet frequently assigns it to
    # keyboards, finger snaps, camera clicks, and other short indoor impacts.
    terms = ("gunshot", "gunfire", "machine gun", "artillery fire")
    scores = observation.scores or (1.0,) * len(observation.labels)
    return any(
        score >= 0.05 and any(term in label.casefold() for term in terms)
        for label, score in zip(observation.labels, scores)
    )


def gunshot_burst(minimum_score: float = 0.08, required_windows: int = 2, within_seconds: float = 2.0):
    """Require distinct, nearby YAMNet windows instead of one transient guess."""
    recent: deque[float] = deque()
    terms = ("gunshot", "gunfire", "machine gun", "artillery fire")

    def matches(observation: Observation) -> bool:
        scores = observation.scores or (1.0,) * len(observation.labels)
        qualifies = any(
            score >= minimum_score and any(term in label.casefold() for term in terms)
            for label, score in zip(observation.labels, scores)
        )
        while recent and observation.timestamp - recent[0] > within_seconds:
            recent.popleft()
        if qualifies and (not recent or observation.timestamp != recent[-1]):
            recent.append(observation.timestamp)
        return len(recent) >= required_windows

    return matches


def no_people_or_vehicles(observation: Observation) -> bool:
    absent = {"person", "car", "truck", "bus", "motorcycle"}
    return not any(label.casefold() in absent for label in observation.labels)


def no_vehicles(observation: Observation) -> bool:
    vehicles = {"car", "truck", "bus", "motorcycle"}
    return not any(label.casefold() in vehicles for label in observation.labels)
