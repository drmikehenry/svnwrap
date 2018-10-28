*******
Changes
*******

Significant changes to svnwrap (newest changes first).

Version 0.7.13
==============

- Drop explicit support for Python 2.6.

- Fix flake8 error.

Version 0.7.12
==============

- Avoid Python 3 exception ``configparser.DuplicateOptionError`` when reading
  ``~/.subversion/config`` having auto-props differing only in case, e.g.::

    [auto-props]
    *.c = svn:eol-style=native
    *.C = svn:eol-style=native

Version 0.7.11
==============

- Drop support for Python 3.3 (thanks to John Hagen).

Version 0.7.10
==============

- Add support for Python 3.7 (thanks to John Hagen).

Version 0.7.9
=============

- Add support for Python 3.6 (thanks to John Hagen).

- Document some overlooked switches::

    --no-pager           disable the automatic use of a pager
    --debug              enable debug printing (mainly for maintainer use)
    --svn path/to/svn    change path to ``svn`` utility (mainly for testing)

- Add ``--ie`` as an abbreviation for ``--ignore-externals``.

- Add ``svn pdiff`` command as a ``patch-compatible`` diff, equivalent to::

    svn diff --diff-cmd diff -x -U1000000 --patch-compatible

Version 0.7.8
=============

- Restore line suppression feature lost during the refactoring of the line
  generation logic.

Version 0.7.7
=============

- Make 'colorama' be a dependency.  This is necessary on Windows to support
  colorized output.

- Support additional Subversion switches:

  --force-interactive
  --ignore-properties
  --include-externals
  --no-diff-added
  --patch-compatible
  --properties-only
  --search
  --search-and
  --show-inherited-props

Version 0.7.6
=============

- Avoid DeprecationWarning for using SafeConfigParser in Python 3.2+.

- Avoid filtering stdout and stderr during "svn merge" operations.  This ensures
  that the output destined for the user's terminal comes out in the desired
  order; otherwise, it's possible for Subversion's menu choices to show up
  too early (e.g., when choosing the "diff-full" operation, the menu is
  redisplayed first followed by the actual diff output, leading to confusion).

- Change to unbuffered method of reading the "svn" client subprocess's output
  and error streams to provide realtime output display.

- Display total number of stderr characters instead of repeating all of stderr.

Version 0.7.5
=============

- Incorporate several code cleanups (thanks to John Hagen).

Version 0.7.4
=============

- Remove stray comma in description string in setup.py.

Version 0.7.3
=============

- Add Travis and PyPI badges to README (thanks to John Hagen).

- Allow full README to be shown on PyPI (thanks to John Hagen).

- Remove Python nightly version from Travis build (thanks to John Hagen).

Version 0.7.2
=============

- Document how to avoid URL adjustment (add ``/.`` to the end of the URL).

- Publish testsvn.py in the distribution.

- Provide initial support for Travis CI using py.test.

- Rename CHANGES.txt to CHANGES.rst, and LICENSE.txt to LICENSE.rst.

- Include Makefile and requirements.txt in MANIFEST.in.

Version 0.7.1
=============

- Add ``--strict`` to ``svn pge`` to avoid the spurious extra newline.

Version 0.7.0
=============

- Capture stderr from "svn" client, highlight these lines, and repeat them
  at the end of the operation so they are not overlooked.  To facilitate this,
  the method of restoring stdout (and now stderr as well) when invoking
  SVN_EDITOR was changed.  When invoking the editor, stdout and stderr are
  now connected to the platform-specific console device ('/dev/tty' on Unix
  machines, and 'CON:' on Windows).

- Add "pge" and "pgi" shortcuts to propget svn:externals and svn:ignores.

- Support svn v1.7+ svn:externals diff format.

  Newer svn clients now provide line-by-line diff output for changes to
  svn:externals, so svnwrap now detects this case to prevent erroneous
  formatting.

- Port to run on both Python 2.x and 3.x, with 2.6 as the minimum supported
  version of Python.

- Format for PEP8 compliance.

.. vim:set ft=rst:
