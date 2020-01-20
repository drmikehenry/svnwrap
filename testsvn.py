#!/usr/bin/env python

import sys


def write(s):
    sys.stdout.write(s)
    sys.stdout.flush()


def write_ln(s):
    write(s + "\n")


def fake_status():
    write(
        """\
A      .
?      svnwrap.py
Performing status

X yadda

A      svnwrap.sh

?      Wiki-20
?      Account-Manager
C      svnwrap/testsvn.py
G      svnwrap/merged.py
?      pyrepl
?      svnwrap/svnwrap.py

A      svnwrap
D      svnwrap/junkfile
A      svnwrap/svnwrap.sh
A      other/stuff.py
M      other/goodStuff.py
"""
    )


def fake_update():
    write(
        """\

Fetching external

External
?      svnwrap
A      svnwrap/svnwrap.sh
C      svnwrap/testsvn.py
G      svnwrap/merged.py
A      other/stuff.py
M      other/goodStuff.py
Updated external

At revision 3.
"""
    )


def fake_switch():
    write(
        """\
A      svnwrap/svnwrap.sh
C      svnwrap/testsvn.py
G      svnwrap/merged.py
D      other/stuff.py

At revision 2.
Updated to revision 2.
"""
    )


def fake_diff():
    write(
        """\

Property changes on: .
___________________________________________________________________
Name: svn:externals
   - # Section one
one file:///home/mrhenr1/tmp/svn/repo/trunk/one
two file:///home/mrhenr1/tmp/svn/repo/trunk/two

# Gap above, starting section two
three file:///home/mrhenr1/tmp/svn/repo/trunk/three

four file:///home/mrhenr1/tmp/svn/repo/trunk/four

   + # Section one
one file:///home/mrhenr1/tmp/svn/repo/trunk/one
five file:///home/mrhenr1/tmp/svn/repo/trunk/five

# Gap above, starting section two
three file:///home/mrhenr1/tmp/svn/repo/trunk/three

six file:///home/mrhenr1/tmp/svn/repo/trunk/six
# Extra line


Modified: svn:externals
## -1 +1,3 ##
+../comp0 comp0
 ../comp comp
+../comp3 comp3
Added: some_weird_property
+property_value goes here
Index: testfile.txt
===================================================================
--- testfile.txt        (revision 0)
+++ testfile.txt        (revision 0)
@@ -0,0 +1,4 @@
+This
+is
+a
+test file.

Property changes on: testfile.txt
___________________________________________________________________
Name: svn:eol-style
   + native

"""
    )


def fake_revert(args):
    write_ln("Reverting:")
    for f in args:
        write_ln("%r" % f)


def fake_log():
    write(
        """\
------------------------------------------------------------------------
r15 | committer | 2014-10-12 15:34:35 -0400 (Sun, 12 Oct 2014) | 4 lines

Even more bar.

And a multi-line log.

------------------------------------------------------------------------
r14 | committer | 2014-10-11 04:43:18 -0400 (Sat, 11 Oct 2014) | 1 line

more bar
------------------------------------------------------------------------
r13 | committer | 2014-10-11 04:43:17 -0400 (Sat, 11 Oct 2014) | 1 line

more bar
------------------------------------------------------------------------
r12 | committer | 2014-10-11 04:43:16 -0400 (Sat, 11 Oct 2014) | 1 line

more bar
------------------------------------------------------------------------
r11 | committer | 2014-10-11 04:43:15 -0400 (Sat, 11 Oct 2014) | 1 line

more bar
------------------------------------------------------------------------
r10 | committer | 2014-10-11 04:43:14 -0400 (Sat, 11 Oct 2014) | 1 line

more bar
------------------------------------------------------------------------
r9 | committer | 2014-10-11 04:43:13 -0400 (Sat, 11 Oct 2014) | 1 line

more bar
------------------------------------------------------------------------
r8 | committer | 2014-10-11 04:43:12 -0400 (Sat, 11 Oct 2014) | 1 line

more bar
------------------------------------------------------------------------
r7 | committer | 2014-10-11 04:43:11 -0400 (Sat, 11 Oct 2014) | 1 line

more bar
------------------------------------------------------------------------
r6 | committer | 2014-10-11 04:43:10 -0400 (Sat, 11 Oct 2014) | 1 line

more bar
------------------------------------------------------------------------
r5 | committer | 2014-10-11 04:43:09 -0400 (Sat, 11 Oct 2014) | 1 line

more bar
------------------------------------------------------------------------
r4 | committer | 2014-10-11 04:43:08 -0400 (Sat, 11 Oct 2014) | 1 line

more bar
------------------------------------------------------------------------
r3 | committer | 2014-10-11 04:42:52 -0400 (Sat, 11 Oct 2014) | 1 line

more bar
------------------------------------------------------------------------
r2 | committer | 2014-10-11 04:42:36 -0400 (Sat, 11 Oct 2014) | 1 line

add bar
------------------------------------------------------------------------
r1 | committer | 2014-10-11 04:42:10 -0400 (Sat, 11 Oct 2014) | 1 line

add foo
------------------------------------------------------------------------
"""
    )


def main():
    args = sys.argv[1:]

    if args:
        cmd = args.pop(0)
    else:
        cmd = ""

    if cmd in ["st", "status"]:
        fake_status()

    elif cmd in ["up", "update"]:
        fake_update()

    elif cmd in ["sw", "switch"]:
        fake_switch()

    elif cmd == "diff":
        fake_diff()

    elif cmd == "revert":
        fake_revert(args)

    elif cmd == "log":
        fake_log()

    elif cmd == "":
        write_ln("Type 'svn help' for usage.")

    else:
        write_ln("testsvn unknown command: svn %s %s" % (cmd, " ".join(args)))


if __name__ == "__main__":
    main()
