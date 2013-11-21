#!/usr/bin/env python

import sys

def write(s):
    sys.stdout.write(s)
    sys.stdout.flush()

def writeLn(s):
    write(s + '\n')

def fakeStatus():
    write('''\
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
''')

def fakeUpdate():
    write('''\

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
''')

def fakeSwitch():
    write('''\
A      svnwrap/svnwrap.sh
C      svnwrap/testsvn.py
G      svnwrap/merged.py
D      other/stuff.py
          
At revision 2.
Updated to revision 2.
''')

def fakeDiff():
    write('''\

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

''')

def fakeRevert(args):
    writeLn("Reverting:")
    for f in args:
        writeLn("%r" % f)

def main():
    args = sys.argv[1:]

    if args:
        cmd = args.pop(0)
    else:
        cmd = ''

    if cmd in ['st', 'status']:
        fakeStatus()

    elif cmd in ['up', 'update']:
        fakeUpdate()

    elif cmd in ['sw', 'switch']:
        fakeSwitch()

    elif cmd == 'diff':
        fakeDiff()

    elif cmd == 'revert':
        fakeRevert(args)

    elif cmd == '':
        writeLn("Type 'svn help' for usage.")

    else:
        writeLn('testsvn uknown command: svn %s %s' % (cmd, ' '.join(args)))

if __name__ == '__main__':
    main()

