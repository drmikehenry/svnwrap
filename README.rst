Svnwrap extends the functionality of svn, the command-line interface for the
Subversion version control system.  Typically, the user will define a shell
alias for ``svn`` that invokes ``svnwrap``.  In this way, operations like ``svn
status`` will be handled by svnwrap instead of svn.

Features:

- Suppression of noisy output from certain operations such as ``svn status``
  (especially beneficial when using svn:externals).

- Color highlighting of status, diff, and other outputs.

- Extended "diff" operations (including integration with kdiff3).

- Extended URL syntax providing:

  - Configurable aliases of the form ``//alias`` that map to arbitrary URL
    prefixes.  Configuring the alias ``proj`` to be ``http://server/Project``
    would make the following commands identical::

      svn co //proj/some/path
      svn co http://server/Project/some/path

  - Mapping of one URL prefix into another using keywords, to take advantage of
    context within a working copy.  So, for example, in a working copy checked
    out from http://server/Project/trunk/some/path, creating a tag could be
    done via::

      svn cp tr: tag:tagname

    The working copy's URL (http://server/Project/trunk/some/path) is used as
    context to allow the tr: keyword to extract everything before the
    ``middle`` part (``/trunk`` in this case) and append ``/trunk``.  The
    ``tag:`` keyword behaves similarly, but appends ``/tags`` instead of
    ``/trunk``.  Thus, the above ``svn cp`` operation is equivalent to::

      svn cp http://server/Project/trunk http://server/Project/tags/tagname

    Switching to the new tag is shortened as well::

      svn sw tag:tagname/some/path

    Additionally, URL suffixes like ``/some/path`` may often be omitted during
    a ``switch`` operation because svnwrap can infer the suffix from the
    context of the current checkout, leading to the following equivalent
    invocation::

      svn sw tag:tagname

- Additional new subcommands such as:

  - ``svn branch`` for creating branches.

  - ``svn ee`` for editing svn:externals.

See built-in help for more details::

  svnwrap helpwrap
