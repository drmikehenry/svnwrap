#!/usr/bin/env python

import sys
import re
import os
import subprocess
import difflib
import platform
import shutil
import ConfigParser
import shlex
import errno
import atexit
import signal

__VERSION__ = '0.7.0'

platform_is_windows = platform.system() == 'Windows'

sample_ini_contents = """
[aliases]
# Aliases are used at the start of a URL.  They are replaced by their
# aliased value.  When the alias "project1" has been defined, this URL:
#   //project1
# will be replaced by the associated URL, e.g.:
#   http://server/url/for/project1
#
# Define aliases as follows:
## project1 = http://server/url/for/project1

[pager]
# The pager is used by several commands to paginate the output.
# Set "enabled" to "false" to disable use of a pager.
## enabled = true

# Customize which pager to use (along with any desired arguments) via the "cmd"
# setting here, or via the environment variable SVN_PAGER, or via the system
# default specified in the PAGER environment variable.  If none of the above
# are set, then "less -FKRX" will be assumed.
#
# Switches for "less":
#   -F  quit the pager early if output fits on one screen
#   -K  allow Ctrl-C to exit less
#   -R  process color escape sequences
#   -X  don't clear the screen when pager quits
## cmd = less -FKRX
#
# If "use_shell" is true, svnwrap will feed "cmd" directly to the shell,
# allowing more complicated commands such as this one (but note that the
# "diff-highlight" command does not come with svnwrap):
#   cmd = diff-highlight | less
#
# **WARNING** If you enable this behavior, svnwrap will not be able to
# detect failures of "cmd".
## use_shell = false
"""

# True when debugging.
debugging = False


def debug(s):
    if debugging:
        sys.stdout.write(s)


def debug_ln(s=''):
    debug(s + '\n')


class SvnError(Exception):
    pass


class PagerClosed(Exception):
    pass


def get_environ(env_var, default=None):
    try:
        return os.environ[env_var]
    except KeyError:
        if default is None:
            raise SvnError('missing environment variable %s' % env_var)
        return default


def get_svnwrap_config_dir():
    config_home = os.path.join(get_environ('HOME', ''), '.config')
    if platform_is_windows:
        config_home = get_environ('APPDATA', config_home)
    config_home = get_environ('XDG_CONFIG_HOME', config_home)
    return os.path.join(config_home, 'svnwrap')


def get_svnwrap_ini_path():
    config_dir = get_svnwrap_config_dir()
    ini_path = os.path.join(config_dir, 'config.ini')
    if not os.path.isdir(config_dir):
        os.makedirs(config_dir)
    if not os.path.isfile(ini_path):
        with open(ini_path, 'w') as f:
            f.write(sample_ini_contents)
    return ini_path


def svnwrap_config():
    config = ConfigParser.SafeConfigParser()
    config.read(get_svnwrap_ini_path())
    return config


def config_boolean(config, section, option, default_value):
    if config.has_option(section, option):
        return config.getboolean(section, option)
    else:
        return default_value


def get_aliases():
    config = svnwrap_config()
    try:
        aliases = config.items('aliases')
    except ConfigParser.NoSectionError:
        aliases = {}
    return dict(aliases)


def get_subversion_config_dir():
    if platform_is_windows:
        config_dir = os.path.join(get_environ('APPDATA', ''), 'Subversion')
    else:
        config_dir = os.path.join(get_environ('HOME', ''), '.subversion')
    return config_dir


def get_subversion_ini_path():
    return os.path.join(get_subversion_config_dir(), 'config')


def subversion_config():
    config = ConfigParser.SafeConfigParser()
    config.read(get_subversion_ini_path())
    return config

STATUS_REX = r'^Performing status|^\s*$|^X[ \t]'
UPDATE_REX = (r'^Fetching external|^External |^Updated external|^\s*$' +
              r'|^At revision')
CHECKOUT_REX = (r'^Fetching external|^\s*$')

SVN = 'svn'

color_names = [
    'black',
    'red',
    'green',
    'yellow',
    'blue',
    'magenta',
    'cyan',
    'white']

color_dict = {}
for i, base_name in enumerate(color_names):
    color_dict['dark' + base_name] = i
    color_dict['light' + base_name] = i + 8

"""
[30m  black foreground
[40m  black background
[90m  light black foreground
[100m light black background
[01m  bold colors
[0m   reset colors

"""

color_scheme = {
    'diffAdd': ['lightblue', None],
    'diffRemoved': ['lightred', None],
    'diffMisc': ['darkyellow', None],
    'conflict': ['lightwhite', 'darkred'],
    'statusAdded': ['darkgreen', None],
    'statusDeleted': ['darkred', None],
    'statusUpdated': ['lightblue', None],
    'statusConflict': ['lightwhite', 'darkred'],
    'statusModified': ['lightblue', None],
    'statusMerged': ['darkmagenta', None],
    'statusUntracked': ['lightblack', None],
    'status': ['lightblack', None],
    'info': ['darkgreen', None],
    'logRev': ['lightyellow', None],
    'logCommitter': ['lightblue', None],
    'logDate': ['lightblack', None],
    'logNumLines': ['lightblack', None],
    'logFieldSeparator': ['lightblack', None],
    'logSeparator': ['darkgreen', None],
    'logText': ['darkwhite', None],
}

entry_name_to_style_name = {}
for key in color_scheme:
    entry_name_to_style_name[key.lower()] = key


def read_color_scheme():
    config = svnwrap_config()
    try:
        configured_colors = dict(config.items('colors'))
    except ConfigParser.NoSectionError:
        configured_colors = {}

    valid_keys = set(color_scheme.keys())
    for key, value in configured_colors.items():
        key = entry_name_to_style_name.get(key, key)

        if key not in valid_keys:
            continue
        colors = map(lambda x: x.strip() or 'default', value.split(','))
        if len(colors) == 1:
            foreground, background = colors[0], None
        elif len(colors) == 2:
            foreground, background = colors
        else:
            raise SvnError(
                "invalid number of colors specified for '%s' in config" % (
                    key,))

        if foreground == 'default':
            foreground = color_scheme[key][0]
        if background == 'default':
            background = color_scheme[key][1]

        if foreground is not None and foreground not in color_dict:
            raise SvnError("invalid color ('%s') specified for '%s'" % (
                foreground, key))
        if background is not None and background not in color_dict:
            raise SvnError("invalid color ('%s') specified for '%s'" % (
                background, key))

        color_scheme[key] = [foreground, background]

using_color = os.isatty(sys.stdout.fileno())
if using_color and platform_is_windows:
    try:
        import colorama
        colorama.init()
    except ImportError as e:
        using_color = False

if os.isatty(sys.stdout.fileno()):
    use_pager = True
else:
    use_pager = False

# Will contain a subprocess.Popen object, if a pager is in use.
pager = None


def set_color_num(color_num):
    if using_color:
        return '\x1b[%dm' % color_num
    else:
        return ''


def set_foreground(foreground):
    if foreground is None:
        return ''
    i = color_dict[foreground]
    if i < 8:
        color_num = 30 + i
    else:
        color_num = 90 + (i - 8)
    return set_color_num(color_num)


def set_background(background):
    if background is None:
        return ''
    i = color_dict[background]
    if i < 8:
        color_num = 40 + i
    else:
        color_num = 100 + (i - 8)
    return set_color_num(color_num)


def reset_colors():
    return set_color_num(0)


def wrap_color(s, style):
    foreground, background = color_scheme[style]
    return (set_foreground(foreground) +
            set_background(background) +
            s +
            reset_colors())


def write(s, f=None):
    if f is None:
        # We don't set f to sys.stdout as a default argument since a pager
        # maybe launched and change the value of sys.stdout.  So we defer
        # resolution until we need it.
        f = sys.stdout

    try:
        f.write(s)
        f.flush()
    except IOError as e:
        if e.errno != errno.EPIPE:
            raise
        raise PagerClosed('Pager pipe closed.')
    except ValueError:
        # If the pager pipe is closed (because someone exited it before we
        # are finished reading off the data from Subversion), then we get a
        # ValueError saying that we provided a bad output file.  Convert this
        # to a PagerClosed exception.
        raise PagerClosed('Pager pipe closed.')


def write_ln(line=''):
    write(line + '\n')


def write_lines(lines):
    for line in lines:
        write_ln(line)


def restore_signals():
    # Python sets up or ignores several signals by default.  This restores the
    # default signal handling for the child process.
    if hasattr(signal, 'SIGINT'):
        signal.signal(signal.SIGINT, signal.SIG_DFL)
    if hasattr(signal, 'SIGPIPE'):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    if hasattr(signal, 'SIGXFZ'):
        signal.signal(signal.SIGXFZ, signal.SIG_DFL)
    if hasattr(signal, 'SIGXFSZ'):
        signal.signal(signal.SIGXFSZ, signal.SIG_DFL)


def add_restore_signals(kwargs):
    # preexec_fn is not supported on Windows, but we want to use it to restore
    # the signal handlers on other platforms.
    if not platform_is_windows:
        kwargs = kwargs.copy()
        kwargs['preexec_fn'] = restore_signals
    return kwargs


def subprocess_call(*args, **kwargs):
    return subprocess.call(*args, **add_restore_signals(kwargs))


def subprocess_popen(*args, **kwargs):
    return subprocess.Popen(*args, **add_restore_signals(kwargs))


def svn_call(args=[]):
    subprocess_args = [SVN] + args
    ret_code = subprocess_call(subprocess_args)
    if ret_code != 0:
        raise SvnError('failing return code %d for external program:\n  %s' %
                       (ret_code, ' '.join(subprocess_args)))


def svn_gen(args, regex=None):
    subprocess_args = [SVN] + args
    svn = subprocess_popen(subprocess_args, stdout=subprocess.PIPE)
    while True:
        line = svn.stdout.readline()
        if line:
            line = line.rstrip('\r\n')
            if regex is None or not re.search(regex, line):
                yield line
        else:
            break
    svn.wait()
    ret_code = svn.returncode
    if ret_code != 0:
        raise SvnError('failing return code %d for external program:\n  %s' %
                       (ret_code, ' '.join(subprocess_args)))


def svn_gen_cmd(cmd, args, regex=None):
    return svn_gen([cmd] + args, regex)


def svn_revert(args):
    svn_call(['revert'] + args)

conflicting_lines = []


def add_conflict_line(line):
    conflicting_lines.append(line)


def display_conflicts():
    if conflicting_lines:
        write_ln(wrap_color('Total conflicts: %d' % len(conflicting_lines),
                            'statusConflict'))
        for line in conflicting_lines:
            write_ln(wrap_color(line, 'statusConflict'))


def split_status(status_line):
    path = status_line[7:]
    if path.startswith(' '):
        path = path[1:]
    return status_line[:7], path


def svn_gen_status(status_args, modified=False, names_only=False):
    for line in svn_gen_cmd('st', status_args, regex=STATUS_REX):
        status, name = split_status(line)
        if names_only:
            yield name
        elif modified:
            if not status.startswith('?'):
                yield name
        else:
            yield line


def svn_gen_info(info_args):
    info_dict = {}
    for line in svn_gen_cmd('info', info_args):
        if ':' in line:
            key, value = line.split(':', 1)
            info_dict[key.strip()] = value.strip()
        else:
            yield info_dict
            info_dict = {}


def svn_gen_diff(args, ignore_space_change=False):
    cmd = ['diff']
    if ignore_space_change:
        cmd.extend(['-x', '-b'])
    return svn_gen(cmd + args)


def wrap_diff_lines(gen):
    for line in gen:
        c = line[:1]
        if c == '+':
            line = wrap_color(line, 'diffAdd')
        elif c == '-':
            line = wrap_color(line, 'diffRemoved')
        elif c == '@':
            line = wrap_color(line, 'diffMisc')
        yield line


def write_diff_lines(gen):
    for line in wrap_diff_lines(gen):
        write_ln(line)


def wrap_status_lines(gen):
    for line in gen:
        c = line[:1]
        if (line.startswith('Checked out') or
                line.startswith('Updated to revision') or
                line.startswith('At revision')):
            line = wrap_color(line, 'status')
        elif c == 'A':
            line = wrap_color(line, 'statusAdded')
        elif c == 'D':
            line = wrap_color(line, 'statusDeleted')
        elif c == 'U':
            line = wrap_color(line, 'statusUpdated')
        elif c == 'C':
            add_conflict_line(line)
            line = wrap_color(line, 'statusConflict')
        elif c == 'M':
            line = wrap_color(line, 'statusModified')
        elif c == 'G':
            line = wrap_color(line, 'statusMerged')
        elif c == '?':
            line = wrap_color(line, 'statusUntracked')
        yield line


def write_status_lines(gen):
    for line in wrap_status_lines(gen):
        write_ln(line)


def write_update_lines(gen):
    for line in wrap_status_lines(gen):
        write_ln(line)


def wrap_log_lines(gen):
    log_re = re.compile(
        r'^(r\d+) \| (.*) \| (.*) \| (\d+ lines?)$')
    separator_line = 72 * '-'

    for line in gen:
        m = log_re.match(line)
        if m:
            # Do stuff...
            field_separator = wrap_color('|', 'logFieldSeparator')
            line = '%s %s %s %s %s %s %s' % (
                wrap_color(m.group(1), 'logRev'),
                field_separator,
                wrap_color(m.group(2), 'logCommitter'),
                field_separator,
                wrap_color(m.group(3), 'logDate'),
                field_separator,
                wrap_color(m.group(4), 'logNumLines'))
            yield line
        elif line == separator_line:
            yield wrap_color(line, 'logSeparator')
        else:
            yield wrap_color(line, 'logText')


def write_log_lines(gen):
    for line in wrap_log_lines(gen):
        write_ln(line)


class ExtDiffer:

    def reset(self):
        self.prop_index = 0
        self.prop_lines = [[], []]

    def __init__(self, ignore_space_change):
        self.ignore_space_change = ignore_space_change
        self.reset()

    def add_line(self, line):
        if re.match(r'\s+- ', line):
            self.prop_index = 0
            line = line.lstrip()[2:]
        elif re.match(r'\s+\+ ', line):
            self.prop_index = 1
            line = line.lstrip()[2:]
        if self.ignore_space_change:
            line = ' '.join(line.strip().split()) + '\n'
        self.prop_lines[self.prop_index].append(line)

    def gen_diff_lines(self):
        new_prop_lines = self.prop_lines[1]
        if new_prop_lines and new_prop_lines[-1].strip() == '':
            extra_line = new_prop_lines.pop()
        else:
            extra_line = None
        if self.prop_lines[0] or self.prop_lines[1]:
            delta = difflib.unified_diff(
                self.prop_lines[0],
                self.prop_lines[1], n=0,
                fromfile='Old externals',
                tofile='New externals')
            for d in delta:
                yield d
        self.reset()
        if extra_line is not None:
            yield extra_line


def diff_filter(lines, ignore_space_change=False):
    ext_differ = ExtDiffer(ignore_space_change)
    in_ext = False
    for line in lines:
        if in_ext and re.match(r'\w+:\s', line):
            for d in ext_differ.gen_diff_lines():
                yield d
            in_ext = False
        if not in_ext and re.match(r'(Name|Modified): svn:externals', line):
            in_ext = True
            yield line
        elif in_ext:
            ext_differ.add_line(line)
        else:
            yield line
    if in_ext:
        for d in ext_differ.gen_diff_lines():
            yield d


def common_prefix(seq1, seq2, parts_equal=lambda part1, part2: part1 == part2):
    prefix = []
    for part1, part2 in zip(seq1, seq2):
        if parts_equal(part1, part2):
            prefix.append(part1)
        else:
            break
    return prefix


def paths_equal(path1, path2):
    return os.path.normcase(path1) == os.path.normcase(path2)


def rel_path(wc_path, start_dir='.'):
    dest_path_parts = os.path.abspath(wc_path).split(os.sep)
    start_dir_parts = os.path.abspath(start_dir).split(os.sep)
    common_parts_len = len(common_prefix(dest_path_parts, start_dir_parts,
                                         paths_equal))
    num_directories_up = len(start_dir_parts) - common_parts_len
    return os.path.normpath(os.path.join(
        os.sep.join([os.pardir] * num_directories_up),
        os.sep.join(dest_path_parts[common_parts_len:])))


def rel_walk(top):
    for root, dirs, files in os.walk(top):
        for d in ['.svn', '_svn']:
            if d in dirs:
                dirs.remove(d)
        yield root, dirs, files


def is_svn_dir(path):
    return os.path.isdir(os.path.join(path, '.svn'))


def svn_merge_raw(raw_root, wc_root):
    # @bug Cannot handle changing a file into a directory or vice-versa.
    if not os.path.isdir(raw_root):
        print 'not a directory: %r' % raw_root
        return
    if is_svn_dir(raw_root):
        print 'cannot use Subversion working copy: %r' % raw_root
        return
    if not is_svn_dir(wc_root):
        print 'not a Subversion working copy: %r' % wc_root
        return
    for root, dirs, files in rel_walk(raw_root):
        for d in dirs:
            raw_path = os.path.join(root, d)
            rel = rel_path(raw_path, raw_root)
            wc_path = os.path.join(wc_root, rel)
            if not os.path.isdir(wc_path):
                print 'adding directory %r' % rel
                shutil.copytree(raw_path, wc_path)
                svn_call(['add', wc_path])
                dirs.remove(d)
        for f in files:
            raw_path = os.path.join(root, f)
            rel = rel_path(raw_path, raw_root)
            wc_path = os.path.join(wc_root, rel)
            already_added = os.path.isfile(wc_path)
            print 'copying file %r' % rel
            shutil.copyfile(raw_path, wc_path)
            if not already_added:
                print 'adding file %r' % rel
                svn_call(['add', wc_path])

    for root, dirs, files in rel_walk(wc_root):
        for d in dirs:
            wc_path = os.path.join(root, d)
            rel = rel_path(wc_path, wc_root)
            raw_path = os.path.join(raw_root, rel)
            if not os.path.isdir(raw_path):
                print 'removing directory %r' % rel
                svn_call(['rm', wc_path])
                dirs.remove(d)
        for f in files:
            wc_path = os.path.join(root, f)
            rel = rel_path(wc_path, wc_root)
            raw_path = os.path.join(raw_root, rel)
            if not os.path.isfile(raw_path):
                print 'removing file %r' % rel
                svn_call(['rm', wc_path])


def get_user():
    return get_environ('USER')


def svn_url_split_peg(url):
    m = re.match(r'(.*)(@\d+)$', url)
    if m:
        new_url, peg = m.group(1), m.group(2)
    else:
        new_url, peg = url, ''
    return new_url, peg


def svn_url_split(url):
    """Split into head, middle, tail.

    If middle can't be found, return (url, "", "").
    If middle is found:
    - head will always end with '/'.
    - middle will not have slashes on either side.
    - tail may start with a slash or '@', or may be empty.
    - only tail may contain a peg revision.

    """

    m = re.match(
        r"""
        (?P<head> .*? /)
        (?P<middle> trunk | (tags | branches) (/ guests / [^/@]+)? / [^/@]+)
        (?P<tail> .*)
        """, url, re.MULTILINE | re.VERBOSE)
    if m:
        return m.group('head'), m.group('middle'), m.group('tail')
    else:
        return url, '', ''


def svn_url_join(head, middle, tail=''):
    url = head
    middle = middle.strip('/')
    tail = tail.strip('/')
    if middle:
        if not url.endswith('/'):
            url += '/'
        url += middle
    if tail:
        if tail[0] in '@/' or url.endswith('/'):
            url += tail
        else:
            url += '/' + tail
    return url


def svn_url_split_head(url):
    head, middle, tail = svn_url_split(url)
    return head


def svn_url_split_tail(url):
    head, middle, tail = svn_url_split(url)
    return tail


def is_url(path):
    return re.match(r'\w+://', path) is not None


def svn_get_url(path):
    # If this is already a URL, return it unchanged.
    if is_url(path):
        return path
    info_dict_list = list(svn_gen_info([path]))
    try:
        info_dict = info_dict_list[0]
        return info_dict['URL']
    except (IndexError, KeyError):
        raise SvnError('invalid subversion path %r' % path)


def svn_get_url_split(path):
    return svn_url_split(svn_get_url(path))


def svn_get_url_head(url):
    return svn_url_split_head(svn_get_url(url))


def svn_get_url_tail(url):
    return svn_url_split_tail(svn_get_url(url))


def svn_url_map(url):
    debug_ln('mapping %s' % repr(url))
    url_history = set()
    aliases = get_aliases()
    while True:
        m = re.match(r"""
                    # Alias of the form //alias ...
                    //(?P<alias>[^/]+) (?P<alias_after>.*)
                |
                    # Absolute URL (e.g., https://...) not at start.
                    .* [:/] (?P<url> \w {2,} :// .*)
                |
                    # Keyword at path-component boundary.
                    (?P<key_before> ^ | .*? /)

                    # Avoid single-character drive letters like C:.
                    (?P<key> \w {2,}) :

                    # After the colon, must not have two slashes.
                    (?P<key_after> .? $ | [^/] .* | / [^/] .*)
            """, url, re.MULTILINE | re.VERBOSE)

        if m and m.group('alias'):
            alias = m.group('alias')
            after = m.group('alias_after')
            try:
                url = aliases[alias] + after
            except KeyError:
                raise SvnError('undefined alias %r' % alias)
        elif m and m.group('url'):
            url = m.group('url')
        elif m and m.group('key'):
            before = m.group('key_before')
            key = m.group('key')
            after = m.group('key_after')
            if key == 'pr':
                url = get_environ('P')
            elif key == 'pp':
                url = get_environ('PP')
            elif key == 'tr':
                url = svn_url_join(svn_get_url_head(before), 'trunk')
            elif key == 'br':
                url = svn_url_join(svn_get_url_head(before), 'branches')
            elif key == 'tag':
                url = svn_url_join(svn_get_url_head(before), 'tags')
            elif key == 'rel':
                url = svn_url_join(svn_get_url_head(before), 'tags/release')
            elif key == 'gb':
                url = svn_url_join(svn_get_url_head(before), 'branches/guests')
            elif key == 'gt':
                url = svn_url_join(svn_get_url_head(before), 'tags/guests')
            elif key == 'mb':
                url = svn_url_join(svn_get_url_head(before),
                                   'branches/guests/' + get_user())
            elif key == 'mt':
                url = svn_url_join(svn_get_url_head(before),
                                   'tags/guests/' + get_user())
            elif key == 'ws':
                ws_head, ws_middle, ignored_tail = svn_get_url_split(before)
                if not ws_middle:
                    ws_middle = 'trunk'
                ws_middle += '/workspace'
                url = svn_url_join(ws_head, ws_middle)
            else:
                raise SvnError("unknown keyword '%s:' in URL" % key)

            url = svn_url_join(url, '', after)
        else:
            break
        if url in url_history:
            raise SvnError('mapping loop for URL %r' % url)
        url_history.add(url)
        debug_ln('        %s' % repr(url))

    debug_ln('    ==> %s' % repr(url))
    return url

subcommands = set("""
? add ann annotate blame cat changelist checkout ci cl cleanup co commit copy
cp del delete di diff export h help import info list lock log ls merge
mergeinfo mkdir move mv patch pd pdel pe pedit pg pget pl plist praise propdel
propedit propget proplist propset ps pset relocate remove ren rename resolve
resolved revert rm st stat status sw switch unlock up update upgrade
""".split())

zero_arg_switches = set("""
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

one_arg_switches = set("""
--accept --change --changelist --cl --config-dir --config-option --depth
--diff-cmd --diff3-cmd --editor-cmd --encoding --extensions --file --limit
--message --native-eol --new --old --password --revision --set-depth
--show-revs --strip --targets --username --with-revprop -F -c -l -m -r -x
""".split())

switch_to_arg_count_map = {}
for arg in zero_arg_switches:
    switch_to_arg_count_map[arg] = 0
for arg in one_arg_switches:
    switch_to_arg_count_map[arg] = 1


def get_switch_arg_count(s):
    try:
        return switch_to_arg_count_map[s]
    except KeyError:
        raise SvnError('invalid switch %r' % s)


def url_map_args(cmd, pos_args):
    if cmd in 'propset pset ps'.split():
        num_unmappable_pos_args = 2
    elif cmd in """
            propdel pdel pd
            propedit pedit pe
            propget pget pg""".split():
        num_unmappable_pos_args = 1
    else:
        num_unmappable_pos_args = 0
    return (pos_args[:num_unmappable_pos_args] +
            [svn_url_map(arg) for arg in pos_args[num_unmappable_pos_args:]])


def adjust_url_for_wc_path(url, wc_path):
    new_url = url
    url_base, url_peg = svn_url_split_peg(url)
    if url_base.endswith('/.'):
        write_ln("Skipping adjustment for URL ending with '/.':")
        write_ln('  %s' % wrap_color(url, 'info'))
    else:
        wc_tail = svn_get_url_tail(wc_path)
        url_head, url_middle, url_tail = svn_url_split(url_base)
        new_url = svn_url_join(url_head, url_middle, wc_tail) + url_peg
        if new_url != url:
            write_ln('Adjusting URL to match working copy tail:')
            write_ln('  Was: %s' % wrap_color(url, 'info'))
            write_ln('  Now: %s' % wrap_color(new_url, 'info'))
            write_ln('  (append %s to URL to avoid adjustment)' %
                     wrap_color("'/.'", 'info'))
    return new_url


def help_wrap(args=[], summary=False):
    if summary:
        write("""
Type 'svn helpwrap' for help on svnwrap extensions.
""")
    else:
        write_ln("""
svnwrap version %(version)s providing:
- Suppression of noisy status output
- Highlighting of status, diff, and other outputs
- Integration with kdiff3
- URL aliases and mapping
- URL adjustment to infer the "tail" of a URL from context (see below).

status (st, stat) - show status (prettied output)
stnames           - show status trimmed to bare path names
stmod             - show status for modified files only (all but ?)
stmodroot         - stmod trimmed to path roots (top-level directories)
stmodrevert       - revert modified files (use with caution!)
update (up)       - update (prettied output)
switch (sw)       - switch (prettied output) with url adjustment
merge             - merge  (prettied output) with url adjustment
checkout (co)     - checkout (prettied output)
diff, ediff (di)  - highlighted diff output with linewise svn:externals diffing
bdiff, ebdiff     - like diff but ignoring space changes
kdiff (kdiff3)    - diff with "--diff-cmd kdiff3" (consider "meld ." instead)
mergeraw RAWPATH [WCPATH]
                  - merge raw (non-SVN) tree into working copy
ee                - propedit svn:externals
ei                - propedit svn:ignore
url               - show URL as received from "svn info"
helpwrap          - this help

Global svnwrap options:
  --color on|off|auto       use color in output (defaults to auto)

Svnwrap configuration file: %(svnwrap_ini_path)s

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
- _middle-or-trunk_ is a "middle" part (e.g., "trunk", "tags/tagname", ...),
  derived from current "middle" part or "trunk" if no middle part in context.

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
ws:         _head_/_middle-or-trunk_/workspace
pr:         $P
pp:         $PP

(Above, P, PP, and USER are environment variables.)

"URL adjustment" is the ability to infer the "tail" of a URL from context.  For
example, in a working copy checked out from http://server/repo/trunk/comp, the
"tail" portion "comp" will be inferred and need not be supplied for certain
commands, such that the following would be equivalent:
  svn switch ^/branches/somebranch/comp
  svn switch ^/branches/somebranch

If your editor isn't launching correctly, setup SVN_EDITOR.
For more details, see the README.rst file distributed with svnwrap.

""".strip() % dict(svnwrap_ini_path=get_svnwrap_ini_path(),
                   version=__VERSION__))


def parse_args():
    """Return (switch_args, pos_args)."""

    debug_arg_parsing = False
    switch_args = []
    pos_args = []
    args = sys.argv[1:]
    while args:
        switch_arg_count = 0
        arg = args.pop(0)
        if arg == '--debug-args':
            debug_arg_parsing = True
        elif arg == '--debug':
            global debugging
            debugging = True
        elif arg == '--test':
            global SVN
            SVN = './testsvn.py'
        elif arg == '--color':
            global using_color
            if args:
                color_flag = args.pop(0)
            else:
                color_flag = ''
            if color_flag == 'on':
                using_color = True
            elif color_flag == 'off':
                using_color = False
            elif color_flag != 'auto':
                help_wrap(summary=True)
                sys.exit()
        elif arg == '--no-pager':
            global use_pager
            use_pager = False
        elif arg.startswith('--'):
            if '=' in arg:
                arg, attached_arg = arg.split('=', 1)
            else:
                attached_arg = None
            switch_arg_count = get_switch_arg_count(arg)
            switch_args.append(arg)
            if attached_arg is not None:
                if switch_arg_count == 0:
                    raise SvnError('switch %s takes no arguments' % arg)
                args.insert(0, attached_arg)
        elif arg.startswith('-'):
            if arg == '-':
                raise SvnError("invalid switch '-'")
            # Split arg into one-character switches.
            s = arg[1:]
            while s:
                arg = '-' + s[0]
                s = s[1:]
                switch_arg_count = get_switch_arg_count(arg)
                switch_args.append(arg)
                if switch_arg_count and s:
                    args.insert(0, s)
                    s = ''
        else:
            pos_args.append(arg)
        if switch_arg_count > len(args):
            raise SvnError('switch %s requires %d argument%s' % (
                arg, switch_arg_count, switch_arg_count > 1 and 's' or ''))
        switch_args.extend(args[:switch_arg_count])
        del args[:switch_arg_count]
    if debug_arg_parsing:
        write_ln('switch_args = %s' % repr(switch_args))
        write_ln('pos_args = %s' % repr(pos_args))
        sys.exit()
    return switch_args, pos_args


def setup_svn_editor():
    """Set SVN_EDITOR to "svnwrap exectty " + original editor settings."""

    config = subversion_config()
    editor = 'vi'
    editor = get_environ('EDITOR', default=editor)
    editor = get_environ('VISUAL', default=editor)
    try:
        editor = config.get('helpers', 'editor-cmd')
    except ConfigParser.Error:
        pass
    editor = get_environ('SVN_EDITOR', default=editor)
    os.environ['SVN_EDITOR'] = sys.argv[0] + ' exectty ' + editor


def setup_pager():
    if not use_pager:
        return

    config = svnwrap_config()
    enabled = config_boolean(config, 'pager', 'enabled', True)
    use_shell = config_boolean(config, 'pager', 'use_shell', False)
    pager_cmd = 'less -FKRX'
    pager_cmd = get_environ('PAGER', default=pager_cmd)
    if config.has_option('pager', 'cmd'):
        pager_cmd = config.get('pager', 'cmd')
    pager_cmd = get_environ('SVN_PAGER', default=pager_cmd)

    # If pager is disabled, nothing more to do.
    if not enabled:
        return

    global pager
    try:
        if use_shell:
            pager = subprocess.Popen(pager_cmd,
                                     stdin=subprocess.PIPE, shell=True)
        else:
            pager = subprocess.Popen(shlex.split(pager_cmd),
                                     stdin=subprocess.PIPE)
    except OSError:
        # Pager is not setup correctly, or command is missing.  Let's just
        # move on.
        return

    # Create extra descriptors to the current stdout and stderr.
    stdout = os.dup(sys.stdout.fileno())
    stderr = os.dup(sys.stderr.fileno())

    # Redirect stdout and stderr into the pager.
    os.dup2(pager.stdin.fileno(), sys.stdout.fileno())
    if sys.stderr.isatty():
        os.dup2(pager.stdin.fileno(), sys.stderr.fileno())

    @atexit.register
    def killpager():
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, signal.SIG_IGN)

        # Restore stdout and stderr to their original state.
        os.dup2(stdout, sys.stdout.fileno())
        os.dup2(stderr, sys.stderr.fileno())

        # Wait for the pager to exit.
        pager.stdin.close()
        pager.wait()


def main():
    # Arguments to "exectty" are unrelated to svnwrap arguments, so
    # handle this subcommand specially.
    args = sys.argv[1:]
    if args and args[0] == 'exectty':
        cmd = args.pop(0)
        if cmd == 'exectty':
            if not args:
                raise SvnError('missing arguments for exectty')

            # Force stdout to be the same as stderr, then exec args.
            os.dup2(2, 1)
            os.execvp(args[0], args)

    setup_svn_editor()

    # Ensure config file exists.
    svnwrap_config()
    read_color_scheme()

    switch_args, pos_args = parse_args()
    if pos_args:
        cmd = pos_args.pop(0)
        pos_args = url_map_args(cmd, pos_args)
    else:
        cmd = None
    args = switch_args + pos_args

    if cmd is None:
        # No positional arguments were given.  Newer svn clients return failure
        # for no arguments at all; in this case, just print the same message
        # that ``svn`` would print without calling ``svn``.
        if switch_args:
            svn_call(args)
        else:
            write_ln("Type 'svn help' for usage.")
        if '--version' in switch_args:
            write_ln('svnwrap version %s' % __VERSION__)
        else:
            help_wrap(summary=True)

    elif cmd == 'help' and not args:
        setup_pager()
        svn_call(['help'])
        help_wrap(summary=True)

    elif cmd == 'helpwrap':
        setup_pager()
        help_wrap(args)

    elif cmd == 'st' or cmd == 'stat' or cmd == 'status':
        write_status_lines(svn_gen_status(args))

    elif cmd == 'stnames':
        write_lines(svn_gen_status(args, names_only=True))

    elif cmd == 'stmod':
        write_lines(svn_gen_status(args, modified=True))

    elif cmd == 'stmodroot':
        d = {}
        for line in svn_gen_status(args, modified=True):
            line = re.sub(r'/.*', '', line)
            d[line] = 1
        for name in sorted(d):
            write_ln(name)

    elif cmd == 'stmodrevert':
        mods = [line.rstrip() for line in svn_gen_status(args, modified=True)]
        svn_revert(mods)

    elif cmd in ['up', 'update']:
        write_update_lines(svn_gen_cmd(cmd, args, regex=UPDATE_REX))

    elif cmd in ['co', 'checkout']:
        write_update_lines(svn_gen_cmd(cmd, args, regex=CHECKOUT_REX))

    elif cmd in ['diff', 'ediff', 'di']:
        setup_pager()
        write_diff_lines(diff_filter(svn_gen_diff(args)))

    elif cmd in ['bdiff', 'ebdiff']:
        setup_pager()
        write_diff_lines(diff_filter(svn_gen_diff(args,
                                                  ignore_space_change=True),
                                     ignore_space_change=True))

    elif cmd in ['kdiff', 'kdiff3']:
        svn_call(['diff', '--diff-cmd', 'kdiff3', '-x', '--qall'] + args)

    elif cmd == 'mergeraw':
        if not args or len(args) > 2:
            write_ln('mergeraw RAWPATH [WCPATH]')
            sys.exit(1)
        raw_root = args.pop(0)
        if args:
            wc_root = args.pop(0)
        else:
            wc_root = '.'
        svn_merge_raw(raw_root, wc_root)

    elif cmd == 'ee':
        if not args:
            args.append('.')
        svn_call('propedit svn:externals'.split() + args)

    elif cmd == 'ei':
        if not args:
            args.append('.')
        svn_call('propedit svn:ignore'.split() + args)

    elif cmd == 'url':
        if pos_args:
            for arg in pos_args:
                write_ln(svn_get_url(arg))
        else:
            write_ln(svn_get_url('.'))

    elif cmd == 'br':
        if len(pos_args) != 1:
            raise SvnError('br takes exactly one URL')
        # Default to branches of current URL, but absolute URL following
        # will override.
        branch = svn_url_map('br:' + pos_args[0])
        trunk = svn_url_map(branch + '/tr:')
        cp_args = ['cp', trunk, branch] + switch_args
        svn_call(cp_args)

    elif cmd in ['sw', 'switch']:
        if 1 <= len(pos_args) <= 2 and '--relocate' not in switch_args:
            url = pos_args.pop(0)
            if pos_args:
                wc_path = pos_args.pop(0)
            else:
                wc_path = '.'
            new_url = adjust_url_for_wc_path(url, wc_path)
            args = switch_args + [new_url, wc_path]
        write_update_lines(svn_gen_cmd(cmd, args, regex=UPDATE_REX))

    elif cmd == 'merge':
        if len(pos_args) > 1 and not is_url(pos_args[-1]):
            wc_path = pos_args.pop()
        else:
            wc_path = '.'
        urls = [adjust_url_for_wc_path(url, wc_path) for url in pos_args]
        args = switch_args + urls + [wc_path]
        write_update_lines(svn_gen_cmd(cmd, args, regex=UPDATE_REX))

    elif cmd == 'log':
        setup_pager()
        write_log_lines(svn_gen_cmd(cmd, args))

    else:
        svn_call([cmd] + args)

    display_conflicts()


def main_with_svn_error_handling():
    try:
        main()
    except KeyboardInterrupt:
        print 'svnwrap: keyboard interrupt'
        sys.exit(1)
    except SvnError as e:
        print 'svnwrap: %s' % e
        sys.exit(1)
    except PagerClosed:
        pass


def color_test():
    for color in sorted(color_dict):
        write_ln(wrap_color('This is %s' % color, color))

if __name__ == '__main__':
    main_with_svn_error_handling()
