Svnwrap - a wrapper script for Subversion
=========================================

Svnwrap extends the functionality of svn, the command-line interface for the
Subversion version control system.  Typically, the user will define a shell
alias for ``svn`` that invokes ``svnwrap``.  In this way, operations like ``svn
status`` will be handled by svnwrap instead of svn.  For the Bash shell, the
following alias could be placed in ``~/.bashrc`` to make the ``svn`` command
invoke ``svnwrap``::

  alias svn='svnwrap'

Features
--------

- Suppression of noisy output from certain operations such as ``svn status``
  (especially beneficial when using svn:externals).

- Color highlighting of status, diff, and other outputs.

- Extended "diff" operations (including integration with kdiff3).

- Configurable URL aliases of the form ``//alias`` that map to arbitrary URL
  prefixes.  Configuring the alias ``proj`` to be ``http://server/Project``
  would make the following commands identical::

    svn checkout //proj/some/path
    svn checkout http://server/Project/some/path

- URL mapping using keywords that takes advantage of context within a working
  copy.  So, for example, in a working copy checked out from
  http://server/Project/trunk/some/path, creating a tag could be done via::

    svn copy tr: tag:tagname

  The working copy's URL (http://server/Project/trunk/some/path) is used as
  context to allow the ``tr:`` keyword to extract everything before the
  "middle" part (``/trunk`` in this case) and append ``/trunk``.  The
  ``tag:`` keyword behaves similarly, but appends ``/tags`` instead of
  ``/trunk``.  Thus, the above ``svn copy`` operation is equivalent to::

    svn copy http://server/Project/trunk http://server/Project/tags/tagname

  Switching or merging a tag is shortened as well::

    svn switch tag:tagname/some/path
    svn merge tag:tagname/some/path

- URL adjustment for certain commands.  URL suffixes like ``/some/path`` may
  often be omitted during a ``switch`` or ``merge`` operation because svnwrap
  can infer the suffix from the context of the current checkout.  For example,
  when executed in a working copy checked out from
  http://server/Project/trunk/some/path, the following are pairs of equivalent
  commands::

    svn switch tag:tagname/some/path
    svn switch tag:tagname

    svn merge tag:tagname/some/path
    svn merge tag:tagname

- Additional new subcommands such as:

  - ``svn branch`` for creating branches.

  - ``svn ee`` for editing svn:externals.

- See built-in help for more details::

    svnwrap helpwrap


Configuration
-------------

Svnwrap is configured via a configuration file, typically at one of these
locations::

  # On Unix:
  ~/.config/svnwrap/config

  # On Windows:
  %APPDATA%\svnwrap\config

On first invocation of svnwrap, the config file will be created with a commented
skeleton.

Caveats
-------

- On occasion, the ``svn`` client needs to invoke an editor (e.g., when
  encountering a merge conflict).  Normally this works fine because the stdout
  of ``svn`` is connected to a terminal.  But to created prettied output,
  svnwrap uses a pipe to capture stdout from ``svn``, which makes some editors
  unable to function correctly.  To work around this problem, svnwrap tries to
  determine which editor ``svn`` would invoke, then it sets the ``SVN_EDITOR``
  environment variable to point to itself.  When ``svn`` launches the editor
  specified by this updated variable, svnwrap duplicates the stderr file
  descriptor (which should still be connected to the terminal) onto stdout, then
  executes the original editor.  Svnwrap looks in most of the places where an
  editor might be configured, but it checks only per-user environment variables
  and config files.  It will not check any registry settings on Windows, nor
  will it check any system-wide configuration files.  To overcome this
  limitation, set the ``SVN_EDITOR`` environment variable to your preferred
  editor settings.

License
-------

Svnwrap is available under the terms of the MIT license; see LICENSE.txt file
for more details.

Changes
-------

See the file CHANGES.txt for details on changes to svnwrap.
