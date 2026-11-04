"""Immutable story objects; state bits follow sorted variable names."""
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class Condition:
    kind: str
    value: bool | None = None
    name: str | None = None
    children: tuple['Condition', ...] = ()


TRUE = Condition('const', value=True)


@dataclass(frozen=True)
class Assertion:
    id: str
    condition: Condition
    message: str


@dataclass(frozen=True)
class Choice:
    id: str
    text: str
    target: str
    condition: Condition = TRUE
    effects: Mapping[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class Node:
    id: str
    title: str
    ending: bool = False
    assertions: tuple[Assertion, ...] = ()
    choices: tuple[Choice, ...] = ()


@dataclass(frozen=True)
class Story:
    title: str
    start: str
    variables: Mapping[str, bool]
    nodes: tuple[Node, ...]


@dataclass(frozen=True)
class Limits:
    max_states: int = 50000
    max_transitions: int = 200000

    def __post_init__(self) -> None:
        for name in ('max_states', 'max_transitions'):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f'{name} 必须是正整数')


State = tuple[str, int]
