#!/usr/bin/env python

__VERSION__ = '0.3.0'

import sys
import re
import os
import subprocess
import difflib
import platform
import shutil

STATUS_REX = r'^Performing status|^\s*$|^X[ \t]'
UPDATE_REX = (r'^Fetching external|^External |^Updated external|^\s*$' +
    r'|^At revision')
CHECKOUT_REX = (r'^Fetching external|^\s*$')

SVN = 'svn'

colorNames = [
    'black',
    'red',
    'green',
    'yellow',
    'blue',
    'magenta',
    'cyan',
    'white']

colorDict = {}
for i, baseName in enumerate(colorNames):
    colorDict['dark' + baseName] = i
    colorDict['light' + baseName] = i + 8

'''
[30m  black foreground
[40m  black background
[90m  light black foreground
[100m light black background
[01m  bold colors
[0m   reset colors

'''

usingColor = os.isatty(sys.stdout.fileno())
if usingColor and platform.system() == 'Windows':
    try:
        import colorama
        colorama.init()
    except ImportError, e:
        usingColor = False

def setColorNum(colorNum):
    if usingColor:
        return '\x1b[%dm' % colorNum
    else:
        return ''

def setForeground(foreground):
    if foreground is None:
        return ''
    i = colorDict[foreground]
    if i < 8:
        colorNum = 30 + i
    else:
        colorNum = 90 + (i - 8)
    return setColorNum(colorNum)

def setBackground(background):
    if background is None:
        return ''
    i = colorDict[background]
    if i < 8:
        colorNum = 40 + i
    else:
        colorNum = 100 + (i - 8)
    return setColorNum(colorNum)

def resetColors():
    return setColorNum(0)

def wrapColor(s, foreground, background=None):
    return (setForeground(foreground) + 
            setBackground(background) + 
            s +
            resetColors())

def write(s, f=sys.stdout):
    f.write(s)
    f.flush()

def writeLn(line):
    write(line + '\n')

def writeLines(lines):
    for line in lines:
        writeLn(line)

def svnCall(args = []):
    subprocess.call([SVN] + args)

def svnGen(args, regex = None):
    svn = subprocess.Popen([SVN] + args, 
            stdout = subprocess.PIPE,
            stderr = subprocess.STDOUT)
    while 1:
        line = svn.stdout.readline()
        if line:
            line = line.rstrip('\r\n')
            if regex is None or not re.search(regex, line):
                yield line
        else:
            return

def svnGenCmd(cmd, args, regex = None):
    return svnGen([cmd] + args, regex)

def svnRevert(args):
    svnCall(["revert"] + args)

conflictingLines = []
def addConflictLine(line):
    conflictingLines.append(line)

def displayConflicts():
    if conflictingLines:
        writeLn(wrapColor("Total conflicts: %d" % len(conflictingLines),
            'lightwhite', 'darkred'))
        for line in conflictingLines:
            writeLn(wrapColor(line, 'lightwhite', 'darkred'))

def splitStatus(statusLine):
    path = statusLine[7:]
    if path.startswith(' '):
        path = path[1:]
    return statusLine[:7], path

def svnGenStatus(statusArgs, modified = False, namesOnly = False):
    for line in svnGenCmd('st', statusArgs, regex = STATUS_REX):
        status, name = splitStatus(line)
        if namesOnly:
            yield name
        elif modified:
            if not status.startswith('?'):
                yield name
        else:
            yield line

def svnGenInfo(infoArgs):
    infoDict = {}
    for line in svnGenCmd('info', infoArgs):
        if ":" in line:
            key, value = line.split(":", 1)
            infoDict[key.strip()] = value.strip()
        else:
            yield infoDict
            infoDict = {}

def svnGenDiff(args, ignoreSpaceChange=False):
    cmd = ['diff']
    if ignoreSpaceChange:
        cmd.extend(['-x', '-b'])
    return svnGen(cmd + args)

def wrapDiffLines(gen):
    for line in gen:
        c = line[:1]
        if c == '+':
            line = wrapColor(line, 'darkblue')
            #line = wrapColor(line, 'darkgreen')
        elif c == '-':
            line = wrapColor(line, 'lightred')
        elif c == '@':
            line = wrapColor(line, 'darkyellow')
        yield line

def writeDiffLines(gen):
    for line in wrapDiffLines(gen):
        writeLn(line)

def wrapStatusLines(gen):
    for line in gen:
        c = line[:1]
        if (line.startswith('Checked out') or
                line.startswith('Updated to revision') or
                line.startswith('At revision')):
            line = wrapColor(line, 'lightblack')
        elif c == 'A':
            line = wrapColor(line, 'darkgreen')
            #line = wrapColor(line, 'darkcyan')
        elif c == 'D':
            line = wrapColor(line, 'darkred')
        elif c == 'U':
            line = wrapColor(line, 'darkblue')
        elif c == 'C':
            addConflictLine(line)
            line = wrapColor(line, 'lightwhite', 'darkred')
        elif c == 'M':
            line = wrapColor(line, 'darkblue')
        elif c == 'G':
            line = wrapColor(line, 'darkmagenta')
        elif c == '?':
            line = wrapColor(line, 'lightblack')
        yield line

def writeStatusLines(gen):
    for line in wrapStatusLines(gen):
        writeLn(line)

def writeUpdateLines(gen):
    for line in wrapStatusLines(gen):
        writeLn(line)

class ExtDiffer:
    def reset(self):
        self.propIndex = 0
        self.propLines = [[], []]

    def __init__(self, ignoreSpaceChange):
        self.ignoreSpaceChange = ignoreSpaceChange
        self.reset()

    def addLine(self, line):
        if re.match(r'\s+- ', line):
            self.propIndex = 0
            line = line.lstrip()[2:]
        elif re.match(r'\s+\+ ', line):
            self.propIndex = 1
            line = line.lstrip()[2:]
        if self.ignoreSpaceChange:
            line = ' '.join(line.strip().split()) + '\n'
        self.propLines[self.propIndex].append(line)

    def genDiffLines(self):
        newPropLines = self.propLines[1]
        if newPropLines and newPropLines[-1].strip() == '':
            extraLine = newPropLines.pop()
        else:
            extraLine = None
        if self.propLines[0] or self.propLines[1]:
            delta = difflib.unified_diff(
                    self.propLines[0],
                    self.propLines[1], n=0, 
                    fromfile="Old externals",
                    tofile="New externals")
            for d in delta:
                yield d
        self.reset()
        if extraLine is not None:
            yield extraLine

def diffFilter(lines, ignoreSpaceChange=False):
    extDiffer = ExtDiffer(ignoreSpaceChange)
    inExt = False
    for line in lines:
        if inExt and re.match(r'\w+:\s', line):
            for d in extDiffer.genDiffLines():
                yield d
            inExt = False
        if not inExt and re.match(r'(Name|Modified): svn:externals', line):
            inExt = True
            yield line
        elif inExt:
            extDiffer.addLine(line)
        else:
            yield line
    if inExt:
        for d in extDiffer.genDiffLines():
            yield d

def commonPrefix(seq1, seq2, partsEqual=lambda part1, part2: part1 == part2):
    prefix = []
    for part1, part2 in zip(seq1, seq2):
        if partsEqual(part1, part2):
            prefix.append(part1)
        else:
            break
    return prefix

def pathsEqual(path1, path2):
    return os.path.normcase(path1) == os.path.normcase(path2)

def relPath(wcPath, startDir='.'):
    destPathParts = os.path.abspath(wcPath).split(os.sep)
    startDirParts = os.path.abspath(startDir).split(os.sep)
    commonPartsLen = len(commonPrefix(destPathParts, startDirParts, 
        pathsEqual))
    numDirectoriesUp = len(startDirParts) - commonPartsLen
    return os.path.normpath(os.path.join(
            os.sep.join([os.pardir] * numDirectoriesUp),
            os.sep.join(destPathParts[commonPartsLen:])))

def relWalk(top):
    for root, dirs, files in os.walk(top):
        for d in ['.svn', '_svn']:
            if d in dirs:
                dirs.remove(d)
        yield root, dirs, files

def isSvnDir(path):
    return os.path.isdir(os.path.join(path, '.svn'))

def svnMergeRaw(rawRoot, wcRoot):
    ## @bug Cannot handle changing a file into a directory or vice-versa.
    if not os.path.isdir(rawRoot):
        print 'not a directory: %r' % rawRoot
        return
    if isSvnDir(rawRoot):
        print 'cannot use Subversion working copy: %r' % rawRoot
        return
    if not isSvnDir(wcRoot):
        print 'not a Subversion working copy: %r' % wcRoot
        return
    for root, dirs, files in relWalk(rawRoot):
        for d in dirs:
            rawPath = os.path.join(root, d)
            rel = relPath(rawPath, rawRoot)
            wcPath = os.path.join(wcRoot, rel)
            if not os.path.isdir(wcPath):
                print 'adding directory %r' % rel
                shutil.copytree(rawPath, wcPath)
                svnCall(['add', wcPath])
                dirs.remove(d)
        for f in files:
            rawPath = os.path.join(root, f)
            rel = relPath(rawPath, rawRoot)
            wcPath = os.path.join(wcRoot, rel)
            alreadyAdded = os.path.isfile(wcPath)
            print 'copying file %r' % rel
            shutil.copyfile(rawPath, wcPath)
            if not alreadyAdded:
                print 'adding file %r' % rel
                svnCall(['add', wcPath])

    for root, dirs, files in relWalk(wcRoot):
        for d in dirs:
            wcPath = os.path.join(root, d)
            rel = relPath(wcPath, wcRoot)
            rawPath = os.path.join(rawRoot, rel)
            if not os.path.isdir(rawPath):
                print 'removing directory %r' % rel
                svnCall(['rm', wcPath])
                dirs.remove(d)
        for f in files:
            wcPath = os.path.join(root, f)
            rel = relPath(wcPath, wcRoot)
            rawPath = os.path.join(rawRoot, rel)
            if not os.path.isfile(rawPath):
                print 'removing file %r' % rel
                svnCall(['rm', wcPath])

def helpWrap(args=[], summary=False):
    if summary:
        write('''
Type 'svn helpwrap' for help on svnwrap extensions.
''')
    else:
        write('''\
svnwrap version ''' + __VERSION__ + ''' providing:
- Suppression of noisy status output
- Highlighting of status, diff, and other outputs
- Integration with kdiff3

status (st)     - status output suppressing messages regarding svn:externals
stnames         - status output trimmed to bare path names
stmod           - status output for modified files only (all but ?)
stmodroot       - stmod trimmed to path roots (top-level directories)
stmodrevert     - reverts modified files (use with caution!)
update (up)     - update, suppressing messages regarding svn:externals
switch (sw)     - switch, suppressing messages regarding svn:externals
checkout (co)   - checkout, suppressing messages regarding svn:externals
diff, ediff     - highlighted diff output with linewise svn:externals diffing
bdiff, ebdiff   - like diff but ignoring space changes
kdiff (kdiff3)  - diff with '--diff-cmd kdiff3'
mergeraw RAWPATH [WCPATH]
                - merge raw (non-SVN) tree into working copy
ee              - propedit svn:externals
ei              - propedit svn:ignore
url             - show URL as received from "svn info"
helpwrap        - this help

options:
  --color on|off|auto       use color in output (defaults to auto)
        
''')

def main():
    args = sys.argv[1:]
    cmd = ''
    while args and not cmd:
        arg = args.pop(0)
        if arg == '--test':
            global SVN
            SVN = './testsvn.py'
        elif arg == '--color':
            global usingColor
            if args:
                colorFlag = args.pop(0)
            else:
                colorFlag = ''
            if colorFlag == 'on':
                usingColor = True
            elif colorFlag == 'off':
                usingColor = False
            elif colorFlag != 'auto':
                helpWrap(summary=True)
                sys.exit()
        else:
            cmd = arg

    if cmd == 'help' and not args:
        svnCall(['help'])
        helpWrap(summary=True)

    elif cmd == '' and not args:
        svnCall()
        helpWrap(summary=True)

    elif cmd == 'helpwrap':
        helpWrap(args)

    elif cmd == 'st' or cmd == 'status':
        writeStatusLines(svnGenStatus(args))

    elif cmd == 'stnames':
        writeLines(svnGenStatus(args, namesOnly = True))

    elif cmd == 'stmod':
        writeLines(svnGenStatus(args, modified = True))

    elif cmd == 'stmodroot':
        d = {}
        for line in svnGenStatus(args, modified = True):
            line = re.sub(r'/.*', '', line)
            d[line] = 1
        for name in sorted(d):
            writeLn(name)

    elif cmd == 'stmodrevert':
        mods = [line.rstrip() for line in svnGenStatus(args, modified = True)]
        svnRevert(mods)

    elif cmd in ['up', 'update', 'sw', 'switch']:
        writeUpdateLines(svnGenCmd(cmd, args, regex=UPDATE_REX))

    elif cmd in ['co', 'checkout']:
        writeUpdateLines(svnGenCmd(cmd, args, regex=CHECKOUT_REX))

    elif cmd in ['diff', 'ediff']:
        writeDiffLines(diffFilter(svnGenDiff(args)))

    elif cmd in ['bdiff', 'ebdiff']:
        writeDiffLines(diffFilter(svnGenDiff(args, ignoreSpaceChange=True),
            ignoreSpaceChange=True))

    elif cmd in ['kdiff', 'kdiff3']:
        svnCall(['diff', '--diff-cmd', 'kdiff3', '-x', '--qall'] + args)

    elif cmd == 'mergeraw':
        if not args or len(args) > 2:
            write("mergeraw RAWPATH [WCPATH]")
            sys.exit(1)
        rawRoot = args.pop(0)
        if args:
            wcRoot = args.pop(0)
        else:
            wcRoot = '.'
        svnMergeRaw(rawRoot, wcRoot)

    elif cmd == 'ee':
        if not args:
            args.append(".")
        svnCall("propedit svn:externals".split() + args)

    elif cmd == 'ei':
        if not args:
            args.append(".")
        svnCall("propedit svn:ignore".split() + args)

    elif cmd == 'url':
        for infoDict in svnGenInfo(args):
            writeLn(infoDict["URL"])

    elif cmd == '':
        svnCall()

    else:
        svnCall([cmd] + args)

    displayConflicts()

def colorTest():
    for color in sorted(colorDict):
        writeLn(wrapColor('This is %s' % color, color))

if __name__ == '__main__':
    main()
