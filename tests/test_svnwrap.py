#!/usr/bin/env python
# coding=utf-8

try:
    from typing import (
        List,
    )
except ImportError:
    pass

import svnwrap


def test_svnwrap_config():
    # type: () -> None
    svnwrap.svnwrap_config()


def test_paths_equal():
    # type: () -> None
    assert svnwrap.paths_equal("somepath", "somepath")
    assert not svnwrap.paths_equal("somepath1", "somepath2")


def test_parse_switch():
    # type: () -> None

    def parse_zero(switch):
        # type: (str) -> None
        args = ["extra"]  # type: List[str]
        assert svnwrap.parse_switch(switch, args) == [switch]
        assert args == ["extra"]
        if not switch.startswith("--"):
            args = []
            assert svnwrap.parse_switch(switch + "f", args) == [switch]
            assert args == ["-f"]

    def parse_one(cmd):
        # type: (str) -> None
        switch, arg = cmd.split()
        args = [arg, "extra"]  # type: List[str]
        assert svnwrap.parse_switch(switch, args) == [switch, arg]
        assert args == ["extra"]

        args = ["extra"]
        if switch.startswith("--"):
            cmd = switch + "=" + arg
        else:
            cmd = switch + arg
        assert svnwrap.parse_switch(cmd, args) == [switch, arg]
        assert args == ["extra"]

    parse_zero("-N")
    parse_zero("-q")
    parse_zero("--version")
    parse_zero("--verbose")
    parse_one("--depth files")
    parse_one("-F file")
