#!/usr/bin/env python
# coding=utf-8

import svnwrap


def test_svnwrap_config():
    # type: () -> None
    svnwrap.svnwrap_config()


def test_paths_equal():
    # type: () -> None
    assert svnwrap.paths_equal("somepath", "somepath")
    assert not svnwrap.paths_equal("somepath1", "somepath2")
