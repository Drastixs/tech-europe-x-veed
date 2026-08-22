from argparse import Namespace

from onshape_assist.cli import command_from_args


def test_cli_left_maps_to_navigation():
    assert command_from_args(Namespace(command="left")) == {"type": "navigate", "direction": "left"}


def test_cli_move_maps_to_position():
    assert command_from_args(Namespace(command="move", x=120, y=220, duration_ms=300)) == {
        "type": "move",
        "x": 120,
        "y": 220,
        "duration_ms": 300,
    }
