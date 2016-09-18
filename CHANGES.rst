*******
Changes
*******

Significant changes to svnwrap (newest changes first).

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
