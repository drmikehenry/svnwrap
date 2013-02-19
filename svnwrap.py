#!/usr/bin/env python
# vim:set fileencoding=utf8: #

__VERSION__ = '0.5.0'

import sys
import re
import os
import subprocess
import difflib
import platform
import shutil
import ConfigParser

platformIsWindows = platform.system() == "Windows"

sampleIniContents = """
[aliases]
## Create aliases like this:
## project1 = http://server/url/for/project1
##
## Use them by starting URLs with // and the alias name, e.g.:
## //project1/trunk
"""

# True when debugging.
debugging = False

def debug(s):
    if debugging:
        sys.stdout.write(s)

def debugLn(s=""):
    debug(s + "\n")

class SvnError(Exception):
    pass

def getEnviron(envVar, default=None):
    try:
        return os.environ[envVar]
    except KeyError:
        if default is None:
            raise SvnError("missing environment variable %s" % envVar)
        return default

def getConfigDir():
    configHome = os.path.join(getEnviron("HOME", ""), ".config")
    if platformIsWindows:
        configHome = getEnviron("APPDATA", configHome)
    configHome = getEnviron("XDG_CONFIG_HOME", configHome)
    return os.path.join(configHome, "svnwrap")

def getIniPath():
    configDir = getConfigDir()
    iniPath = os.path.join(configDir, "config.ini")
    if not os.path.isdir(configDir):
        os.makedirs(configDir)
    if not os.path.isfile(iniPath):
        with open(iniPath, "w") as f:
            f.write(sampleIniContents)
    return iniPath

def svnwrapConfig():
    config = ConfigParser.SafeConfigParser()
    config.read(getIniPath())
    return config

def getAliases():
    config = svnwrapConfig()
    try:
        aliases = config.items("aliases")
    except ConfigParser.NoSectionError:
        aliases = {}
    return dict(aliases)

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

colorScheme = {
        'diffAdd': ['darkblue', None],
        'diffRemoved': ['lightred', None],
        'diffMisc': ['darkyellow', None],
        'conflict': ['lightwhite', 'darkred'],
        'statusAdded': ['darkgreen', None],
        'statusDeleted': ['darkred', None],
        'statusUpdated': ['darkblue', None],
        'statusConflict': ['lightwhite', 'darkred'],
        'statusModified': ['darkblue', None],
        'statusMerged': ['darkmagenta', None],
        'statusUntracked': ['lightblack', None],
        'status': ['lightblack', None],
        'info': ['darkgreen', None],
}

entryNameToStyleName = {}
for key in colorScheme:
    entryNameToStyleName[key.lower()] = key

def readColorScheme():
    config = svnwrapConfig()
    try:
        configuredColors = dict(config.items('colors'))
    except ConfigParser.NoSectionError:
        configuredColors = {}

    validKeys = set(colorScheme.keys())
    for key, value in configuredColors.items():
        key = entryNameToStyleName.get(key, key)

        if key not in validKeys:
            continue
        colors = map(lambda x: x.strip() or 'default', value.split(','))
        if len(colors) == 1:
            foreground, background = colors[0], None
        elif len(colors) == 2:
            foreground, background = colors
        else:
            raise SvnError(
                    "Invalid number of colors specified for '%s' in config" % (
                        key,))

        if foreground == 'default':
            foreground = colorScheme[key][0]
        if background == 'default':
            background = colorScheme[key][1]

        if foreground is not None and foreground not in colorDict:
            raise SvnError("Invalid color ('%s') specified for '%s'" % (
                foreground, key))
        if background is not None and background not in colorDict:
            raise SvnError("Invalid color ('%s') specified for '%s'" % (
                background, key))

        colorScheme[key] = [foreground, background]

usingColor = os.isatty(sys.stdout.fileno())
if usingColor and platformIsWindows:
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

def wrapColor(s, style):
    foreground, background = colorScheme[style]
    return (setForeground(foreground) +
            setBackground(background) +
            s +
            resetColors())

def write(s, f=sys.stdout):
    f.write(s)
    f.flush()

def writeLn(line = ""):
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
            'statusConflict'))
        for line in conflictingLines:
            writeLn(wrapColor(line, 'statusConflict'))

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
            line = wrapColor(line, 'diffAdd')
            #line = wrapColor(line, 'darkgreen')
        elif c == '-':
            line = wrapColor(line, 'diffRemoved')
        elif c == '@':
            line = wrapColor(line, 'diffMisc')
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
            line = wrapColor(line, 'status')
        elif c == 'A':
            line = wrapColor(line, 'statusAdded')
        elif c == 'D':
            line = wrapColor(line, 'statusDeleted')
        elif c == 'U':
            line = wrapColor(line, 'statusUpdated')
        elif c == 'C':
            addConflictLine(line)
            line = wrapColor(line, 'statusConflict')
        elif c == 'M':
            line = wrapColor(line, 'statusModified')
        elif c == 'G':
            line = wrapColor(line, 'statusMerged')
        elif c == '?':
            line = wrapColor(line, 'statusUntracked')
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

def getUser():
    return getEnviron("USER")

def svnUrlSplitPeg(url):
    m = re.match(r'(.*)(@\d+)$', url)
    if m:
        newUrl, peg = m.group(1), m.group(2)
    else:
        newUrl, peg = url, ""
    return newUrl, peg

def svnUrlSplit(url):
    m = re.match(r'''
            (?P<head> .*?)
            /
            (?P<middle> trunk | (tags | branches) (/ guests / [^/]+)? / [^/]+)
            (?P<tail> .*)
        ''', url, re.MULTILINE | re.VERBOSE)
    if m:
        return m.group("head"), m.group("middle"), m.group("tail")
    else:
        return url, "", ""

def svnUrlJoin(head, middle, tail):
    url = head
    if middle:
        url += "/" + middle
    if tail:
        url += tail
    return url

def svnUrlSplitHead(url):
    head, middle, tail = svnUrlSplit(url)
    return head

def svnUrlSplitTail(url):
    head, middle, tail = svnUrlSplit(url)
    return tail

def isUrl(path):
    return re.match(r'\w+://', path) is not None

def svnGetUrl(path="."):
    # If this is already a URL, return it unchanged.
    if isUrl(path):
        return path
    infoDictList = list(svnGenInfo([path]))
    try:
        infoDict = infoDictList[0]
        return infoDict["URL"]
    except IndexError, KeyError:
        raise SvnError("invalid subversion path %r" % path)

def svnGetUrlHead(url):
    return svnUrlSplitHead(svnGetUrl(url))

def svnGetUrlTail(url):
    return svnUrlSplitTail(svnGetUrl(url))

def svnUrlMap(url):
    debugLn("mapping %s" % repr(url))
    urlHistory = set()
    aliases = getAliases()
    while True:
        m = re.match(r'''
                    # Alias of the form //alias ...
                    //(?P<alias>[^/]+) (?P<aliasAfter>.*)
                | 
                    # Absolute URL (e.g., https://...) not at start.
                    .* [:/] (?P<url> \w {2,} :// .*)
                |
                    # Keyword at path-component boundary.
                    (?P<keyBefore> ^ | .*? /)

                    # Avoid single-character drive letters like C:.
                    (?P<key> \w {2,}) :

                    # After the colon, must not have two slashes.
                    (?P<keyAfter> .? $ | [^/] .* | / [^/] .*)
            ''', url, re.MULTILINE | re.VERBOSE)

        if m and m.group("alias"):
            alias = m.group("alias")
            after = m.group("aliasAfter")
            try:
                url = aliases[alias] + after
            except KeyError:
                raise SvnError("undefined alias %r" % alias)
        elif m and m.group("url"):
            url = m.group("url")
        elif m and m.group("key"):
            before = m.group("keyBefore")
            key = m.group("key")
            after = m.group("keyAfter")
            if before.endswith("/") and before != "/":
                before = before[:-1]
            # Add "/" after "keyword:", but only if what follows is non-empty,
            # does not have a leading slash, and is not a peg revision.
            if after and after[0] not in "/@":
                after = "/" + after
            if key == "pr":
                url = getEnviron("P")
            elif key == "pp":
                url = getEnviron("PP")
            elif key == "tr":
                url = svnGetUrlHead(before) + "/trunk"
            elif key == "br":
                url = svnGetUrlHead(before) + "/branches"
            elif key == "tag":
                url = svnGetUrlHead(before) + "/tags"
            elif key == "rel":
                url = svnGetUrlHead(before) + "/tags/release"
            elif key == "gb":
                url = svnGetUrlHead(before) + "/branches/guests"
            elif key == "gt":
                url = svnGetUrlHead(before) + "/tags/guests"
            elif key == "mb":
                url = svnGetUrlHead(before) + "/branches/guests/" + getUser()
            elif key == "mt":
                url = svnGetUrlHead(before) + "/tags/guests/" + getUser()
            else:
                raise SvnError("unknown keyword '%s:' in URL" % key)

            url += after
        else:
            break
        if url in urlHistory:
            raise SvnError("mapping loop for URL %r" % url)
        urlHistory.add(url)
        debugLn("        %s" % repr(url))

    debugLn("    ==> %s" % repr(url))
    return url

subcommands = set("""
? add ann annotate blame cat changelist checkout ci cl cleanup co commit copy
cp del delete di diff export h help import info list lock log ls merge
mergeinfo mkdir move mv patch pd pdel pe pedit pg pget pl plist praise propdel
propedit propget proplist propset ps pset relocate remove ren rename resolve
resolved revert rm st stat status sw switch unlock up update upgrade
""".split())

zeroArgSwitches = set("""
--allow-mixed-revisions --auto-props --diff --dry-run --force --force-log
--git --help --ignore-ancestry --ignore-externals --ignore-keywords
--ignore-whitespace --incremental --internal-diff --keep-changelists
--keep-local --no-auth-cache --no-auto-props --no-diff-deleted --no-ignore
--no-unlock --non-interactive --non-recursive --notice-ancestry --parents
--quiet --record-only --recursive --reintegrate --relocate --remove
--reverse-diff --revprop --show-copies-as-adds --show-updates --stop-on-copy
--strict --strict option to disabl --summarize --trust-server-cert
--use-merge-history --version --verbose --with-all-revprops
--with-no-revprops --xml -?  -N -R -g -q -u -v
""".split())

oneArgSwitches = set("""
--accept --change --changelist --cl --config-dir --config-option --depth
--diff-cmd --diff3-cmd --editor-cmd --encoding --extensions --file --limit
--message --native-eol --new --old --password --revision --set-depth
--show-revs --strip --targets --username --with-revprop -F -c -l -m -r -x
""".split())

switchArgCount = {}
for arg in zeroArgSwitches:
    switchArgCount[arg] = 0
for arg in oneArgSwitches:
    switchArgCount[arg] = 1

def getSwitchArgCount(s):
    try:
        return switchArgCount[s]
    except KeyError:
        raise SvnError("invalid switch %r" % s)

def urlMapArgs(cmd, posArgs):
    if cmd in "propset pset ps".split():
        numUnmappablePosArgs = 2
    elif cmd in """
            propdel pdel pd 
            propedit pedit pe 
            propget pget pg""".split():
        numUnmappablePosArgs = 1
    else:
        numUnmappablePosArgs = 0
    return (posArgs[:numUnmappablePosArgs] +
            [svnUrlMap(arg) for arg in posArgs[numUnmappablePosArgs:]])

def adjustUrlForWcPath(url, wcPath):
    newUrl = url
    urlBase, urlPeg = svnUrlSplitPeg(url)
    if urlBase.endswith("/."):
        writeLn("Skipping adjustment for URL ending with '/.':")
        writeLn("  %s" % wrapColor(url, "info"))
    else:
        wcTail = svnGetUrlTail(wcPath)
        urlHead, urlMiddle, urlTail = svnUrlSplit(urlBase)
        newUrl = svnUrlJoin(urlHead, urlMiddle, wcTail) + urlPeg
        if newUrl != url:
            writeLn("Adjusting URL to match working copy tail:")
            writeLn("  Was: %s" % wrapColor(url, "info"))
            writeLn("  Now: %s" % wrapColor(newUrl, "info"))
            writeLn("  (append %s to URL to avoid adjustment)" %
                    wrapColor("'/.'", "info"))
    return newUrl

def helpWrap(args=[], summary=False):
    if summary:
        write('''
Type 'svn helpwrap' for help on svnwrap extensions.
''')
    else:
        iniPath = getIniPath()
        version = __VERSION__
        write('''\
svnwrap version %(version)s providing:
- Suppression of noisy status output
- Highlighting of status, diff, and other outputs
- Integration with kdiff3
- URL aliases and mapping

status (st, stat) - status output suppressing messages regarding svn:externals
stnames           - status output trimmed to bare path names
stmod             - status output for modified files only (all but ?)
stmodroot         - stmod trimmed to path roots (top-level directories)
stmodrevert       - reverts modified files (use with caution!)
update (up)       - update, suppressing messages regarding svn:externals
switch (sw)       - switch, suppressing messages regarding svn:externals
checkout (co)     - checkout, suppressing messages regarding svn:externals
diff, ediff (di)  - highlighted diff output with linewise svn:externals diffing
bdiff, ebdiff     - like diff but ignoring space changes
kdiff (kdiff3)    - diff with '--diff-cmd kdiff3'
mergeraw RAWPATH [WCPATH]
                  - merge raw (non-SVN) tree into working copy
ee                - propedit svn:externals
ei                - propedit svn:ignore
url               - show URL as received from "svn info"
helpwrap          - this help

Global svnwrap options:
  --color on|off|auto       use color in output (defaults to auto)

Svnwrap configuration file: %(iniPath)s

"//alias" at start of URL expands as defined in configuration file.  E.g., if:
      proj = https://server/SomeProject
  then the following two operations would be identical:
    svn co //proj/trunk/etc
    svn co https://server/SomeProject/trunk/etc

"keyword:" mapping for URLs:
- The keyword (including colon) may be at the URL start or after any "/".
- URL is composed of _prefix_, keyword, _suffix_
- _prefix_ + keyword become new _prefix_; _suffix_ (if present) is appended.
- _head_ means that part of _prefix_ which comes before "trunk", "tags", etc.

Keyword     _prefix_ + keyword becomes:
-------     -------------------------------------------------------

tr:         _head_/trunk
br:         _head_/branches
gb:         _head_/branches/guests
mb:         _head_/branches/guests/$USER
tag:        _head_/tags
gt:         _head_/tags/guests
mt:         _head_/tags/guests/$USER
rel:        _head_/tags/release
pr:         $P
pp:         $PP

(Above, P, PP, and USER are environment variables.)
''' % vars())

def parseArgs():
    """Return (switchArgs, posArgs)."""

    argsToSkip = 0
    switchArgs = []
    posArgs = []
    args = sys.argv[1:]
    while args:
        arg = args.pop(0)
        if argsToSkip:
            argsToSkip -= 1
            switchArgs.append(arg)
        elif arg == '--debug':
            global debugging
            debugging = True
        elif arg == '--test':
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
        elif arg.startswith("--"):
            argsToSkip = getSwitchArgCount(arg)
            switchArgs.append(arg)
        elif arg.startswith("-"):
            if arg == "-":
                raise SvnError("invalid switch '-'")
            # Split arg into one-character switches.
            s = arg[1:]
            while s:
                arg = "-" + s[0]
                s = s[1:]
                argsToSkip = getSwitchArgCount(arg)
                if argsToSkip and s:
                    argsToSkip -= 1
                    s = ""
            switchArgs.append(arg)
        else:
            posArgs.append(arg)
    return switchArgs, posArgs

def main():
    # Ensure config file exists.
    svnwrapConfig()
    readColorScheme()

    switchArgs, posArgs = parseArgs()
    if posArgs:
        cmd = posArgs.pop(0)
        posArgs = urlMapArgs(cmd, posArgs)
    else:
        cmd = None
    args = switchArgs + posArgs

    if cmd is None:
        svnCall(args)
        if "--version" in switchArgs:
            writeLn("svnwrap version %s" % __VERSION__)
        else:
            helpWrap(summary=True)

    elif cmd == 'help' and not args:
        svnCall(['help'])
        helpWrap(summary=True)

    elif cmd == 'helpwrap':
        helpWrap(args)

    elif cmd == 'st' or cmd == 'stat' or cmd == 'status':
        writeStatusLines(svnGenStatus(args))

    elif cmd == 'stnames':
        writeLines(svnGenStatus(args, namesOnly=True))

    elif cmd == 'stmod':
        writeLines(svnGenStatus(args, modified=True))

    elif cmd == 'stmodroot':
        d = {}
        for line in svnGenStatus(args, modified=True):
            line = re.sub(r'/.*', '', line)
            d[line] = 1
        for name in sorted(d):
            writeLn(name)

    elif cmd == 'stmodrevert':
        mods = [line.rstrip() for line in svnGenStatus(args, modified=True)]
        svnRevert(mods)

    elif cmd in ['up', 'update']:
        writeUpdateLines(svnGenCmd(cmd, args, regex=UPDATE_REX))

    elif cmd in ['co', 'checkout']:
        writeUpdateLines(svnGenCmd(cmd, args, regex=CHECKOUT_REX))

    elif cmd in ['diff', 'ediff', 'di']:
        writeDiffLines(diffFilter(svnGenDiff(args)))

    elif cmd in ['bdiff', 'ebdiff']:
        writeDiffLines(diffFilter(svnGenDiff(args, ignoreSpaceChange=True),
            ignoreSpaceChange=True))

    elif cmd in ['kdiff', 'kdiff3']:
        svnCall(['diff', '--diff-cmd', 'kdiff3', '-x', '--qall'] + args)

    elif cmd == 'mergeraw':
        if not args or len(args) > 2:
            writeLn("mergeraw RAWPATH [WCPATH]")
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
        if posArgs:
            for arg in posArgs:
                writeLn(svnGetUrl(arg))
        else:
            writeLn(svnGetUrl())

    elif cmd == 'br':
        if len(posArgs) != 1:
            raise SvnError("br takes exactly one URL")
        # Default to branches of current URL, but absolute URL following
        # will override.
        branch = svnUrlMap("br:" + posArgs[0])
        trunk = svnUrlMap(branch + "/tr:")
        cpArgs = ["cp", trunk, branch] + switchArgs
        svnCall(cpArgs)

    elif cmd in ['sw', 'switch']:
        if 1 <= len(posArgs) <= 2 and "--relocate" not in switchArgs:
            url = posArgs.pop(0)
            if posArgs:
                wcPath = posArgs.pop(0)
            else:
                wcPath = "."
            newUrl = adjustUrlForWcPath(url, wcPath)
            args = switchArgs + [newUrl, wcPath]
        writeUpdateLines(svnGenCmd(cmd, args, regex=UPDATE_REX))

    elif cmd == "merge":
        if len(posArgs) > 1 and not isUrl(posArgs[-1]):
            wcPath = popArgs.pop()
        else:
            wcPath = "."
        urls = [adjustUrlForWcPath(url, wcPath) for url in posArgs]
        args = switchArgs + urls + [wcPath]
        writeUpdateLines(svnGenCmd(cmd, args, regex=UPDATE_REX))

    else:
        svnCall([cmd] + args)

    displayConflicts()

def mainWithSvnErrorHandling():
    try:
        main()
    except KeyboardInterrupt:
        pass
    except SvnError, e:
        print "svnwrap: %s" % str(e)
        sys.exit(1)

def colorTest():
    for color in sorted(colorDict):
        writeLn(wrapColor('This is %s' % color, color))

if __name__ == '__main__':
    mainWithSvnErrorHandling()
