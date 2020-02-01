#!/usr/bin/env python
# coding=utf-8

from __future__ import print_function
from __future__ import unicode_literals

import atexit
import codecs
import difflib
import errno
import io
import locale
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import textwrap
import threading

try:
    from typing import (
        Any,
        BinaryIO,
        Callable,
        Dict,
        Iterable,
        Iterator,
        List,
        Optional,
        Set,
        TextIO,
        Tuple,
        Union,
    )
except ImportError:
    pass


if sys.version_info < (3, 0):
    import ConfigParser as configparser
    from ConfigParser import SafeConfigParser as ConfigParser
    import Queue as queue
else:
    import configparser
    from configparser import ConfigParser
    import queue

__version__ = "0.8.1"

platform_is_windows = platform.system() == "Windows"


def color_supported():
    # type: () -> bool
    if platform_is_windows:
        try:
            import colorama

            colorama.init()
        except ImportError:
            return False
    return True


class State:
    def __init__(self):
        # type: () -> None

        # True when debugging.
        self.debugging = False

        # Path of Subversion client executable.
        self.SVN = "svn"

        # True if stdout is a TTY.
        self.isatty = os.isatty(sys.stdout.fileno())

        # True to use color highlighting on output.
        self.using_color = self.isatty and color_supported()

        # True to feed output through a pager.
        self.use_pager = self.isatty

        # Will contain a subprocess.Popen object, if a pager is in use.
        self.pager = None  # type: Optional[subprocess.Popen]


state = State()

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


def debug(s):
    # type: (str) -> None
    if state.debugging:
        sys.stdout.write(s)


def debug_ln(s=""):
    # type: (str) -> None
    debug(s + "\n")


class SvnError(Exception):
    pass


class PagerClosed(Exception):
    pass


def remove_chars(s, chars):
    # type: (str, str) -> str
    # Remove from all individual characters in chars.
    for c in chars:
        s = s.replace(c, "")
    return s


def get_environ(env_var, default=None):
    # type: (str, str) -> str
    try:
        return os.environ[env_var]
    except KeyError:
        if default is None:
            raise SvnError("missing environment variable %s" % env_var)
        return default


def get_svnwrap_config_dir():
    # type: () -> str
    config_home = os.path.join(get_environ("HOME", ""), ".config")
    if platform_is_windows:
        config_home = get_environ("APPDATA", config_home)
    config_home = get_environ("XDG_CONFIG_HOME", config_home)
    return os.path.join(config_home, "svnwrap")


def get_svnwrap_ini_path():
    # type: () -> str
    config_dir = get_svnwrap_config_dir()
    ini_path = os.path.join(config_dir, "config.ini")
    if not os.path.isdir(config_dir):
        os.makedirs(config_dir)
    if not os.path.isfile(ini_path):
        with open(ini_path, "w") as f:
            f.write(sample_ini_contents)
    return ini_path


def svnwrap_config():
    # type: () -> ConfigParser
    config = ConfigParser()
    config.read(get_svnwrap_ini_path())
    return config


def config_boolean(config, section, option, default_value):
    # type: (ConfigParser, str, str, bool) -> bool
    if config.has_option(section, option):
        return config.getboolean(section, option)
    else:
        return default_value


def get_aliases():
    # type: () -> Dict[str, str]
    config = svnwrap_config()
    try:
        aliases = config.items("aliases")
    except configparser.NoSectionError:
        aliases = []
    return dict(aliases)


def get_subversion_config_dir():
    # type: () -> str
    if platform_is_windows:
        config_dir = os.path.join(get_environ("APPDATA", ""), "Subversion")
    else:
        config_dir = os.path.join(get_environ("HOME", ""), ".subversion")
    return config_dir


def get_subversion_ini_path():
    # type: () -> str
    return os.path.join(get_subversion_config_dir(), "config")


def subversion_config():
    # type: () -> ConfigParser
    # Python 3.2 added ``strict`` to prohibit duplicate keys.
    # ~/.subversion/config may well have duplicate keys because of
    # lines handling lowercase and uppercase filename globs, e.g.::
    #
    #   [auto-props]
    #   *.c = svn:eol-style=native
    #   *.C = svn:eol-style=native
    # Disable this strict checking if it's available, and otherwise
    # just use the older ConfigParser behavior that permitted duplicates.
    try:
        config = ConfigParser(strict=False)
    except TypeError:
        config = ConfigParser()
    config.read(get_subversion_ini_path())
    return config


STATUS_REX = r"^Performing status|^\s*$|^X[ \t]"
UPDATE_REX = (
    r"^Fetching external|^External |^Updated external|^\s*$" + r"|^At revision"
)
CHECKOUT_REX = r"^Fetching external|^\s*$"

color_names = [
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
]

color_dict = {}
for i, base_name in enumerate(color_names):
    color_dict["dark" + base_name] = i
    color_dict["light" + base_name] = i + 8

"""
[30m  black foreground
[40m  black background
[90m  light black foreground
[100m light black background
[01m  bold colors
[0m   reset colors

"""

color_scheme = {
    "diffAdd": ("lightblue", None),
    "diffRemoved": ("lightred", None),
    "diffMisc": ("darkyellow", None),
    "conflict": ("lightwhite", "darkred"),
    "statusAdded": ("darkgreen", None),
    "statusDeleted": ("darkred", None),
    "statusUpdated": ("lightblue", None),
    "statusConflict": ("lightwhite", "darkred"),
    "statusModified": ("lightblue", None),
    "statusMerged": ("darkmagenta", None),
    "statusUntracked": ("lightblack", None),
    "status": ("lightblack", None),
    "info": ("darkgreen", None),
    "logRev": ("lightyellow", None),
    "logCommitter": ("lightblue", None),
    "logDate": ("lightblack", None),
    "logNumLines": ("lightblack", None),
    "logFieldSeparator": ("lightblack", None),
    "logSeparator": ("darkgreen", None),
    "logText": ("darkwhite", None),
    "warning": ("lightwhite", "darkred"),
}  # type: Dict[str, Tuple[str, Optional[str]]]

entry_name_to_style_name = {}
for key in color_scheme:
    entry_name_to_style_name[key.lower()] = key


def read_color_scheme():
    # type: () -> None
    config = svnwrap_config()
    try:
        configured_colors = dict(config.items("colors"))
    except configparser.NoSectionError:
        configured_colors = {}

    valid_keys = set(color_scheme.keys())
    for key, value in configured_colors.items():
        key = entry_name_to_style_name.get(key, key)

        if key not in valid_keys:
            continue
        colors = list(map(lambda x: x.strip() or "default", value.split(",")))
        if len(colors) == 1:
            foreground, background = colors[0], None
        elif len(colors) == 2:
            foreground, background = colors
        else:
            raise SvnError(
                "invalid number of colors specified for '%s' in config"
                % (key,)
            )

        if foreground == "default":
            foreground = color_scheme[key][0]
        if background == "default":
            background = color_scheme[key][1]

        if foreground is not None and foreground not in color_dict:
            raise SvnError(
                "invalid color ('%s') specified for '%s'" % (foreground, key)
            )
        if background is not None and background not in color_dict:
            raise SvnError(
                "invalid color ('%s') specified for '%s'" % (background, key)
            )

        color_scheme[key] = (foreground, background)


def set_color_num(color_num):
    # type: (int) -> str
    if state.using_color:
        return "\x1b[%dm" % color_num
    else:
        return ""


def set_foreground(foreground):
    # type: (Optional[str]) -> str
    if foreground is None:
        return ""
    i = color_dict[foreground]
    if i < 8:
        color_num = 30 + i
    else:
        color_num = 90 + (i - 8)
    return set_color_num(color_num)


def set_background(background):
    # type: (Optional[str]) -> str
    if background is None:
        return ""
    i = color_dict[background]
    if i < 8:
        color_num = 40 + i
    else:
        color_num = 100 + (i - 8)
    return set_color_num(color_num)


def reset_colors():
    # type: () -> str
    return set_color_num(0)


def wrap_color(s, style):
    # type: (str, str) -> str
    foreground, background = color_scheme[style]
    return (
        set_foreground(foreground)
        + set_background(background)
        + s
        + reset_colors()
    )


def write(s, f=None):
    # type: (str, Optional[TextIO]) -> None
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
        raise PagerClosed("Pager pipe closed.")
    except ValueError:
        # If the pager pipe is closed (because someone exited it before we
        # are finished reading off the data from Subversion), then we get a
        # ValueError saying that we provided a bad output file.  Convert this
        # to a PagerClosed exception.
        raise PagerClosed("Pager pipe closed.")


def write_ln(line=""):
    # type: (str) -> None
    write(line + "\n")


def write_lines(lines):
    # type: (Iterable[str]) -> None
    for line in lines:
        write_ln(line)


warning_lines = []


def add_warning_line(line):
    # type: (str) -> None
    warning_lines.append(line)


stderr_parts = []


def add_stderr_text(text):
    # type: (str) -> None
    stderr_parts.append(text)


def restore_signals():
    # type: () -> None
    # Python sets up or ignores several signals by default.  This restores the
    # default signal handling for the child process.
    for attr in "SIGINT SIGPIPE SIGXFZ SIGXFSZ".split():
        if hasattr(signal, attr):
            signal.signal(getattr(signal, attr), signal.SIG_DFL)


def add_restore_signals(kwargs):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    # preexec_fn is not supported on Windows, but we want to use it to restore
    # the signal handlers on other platforms.
    if not platform_is_windows:
        kwargs = kwargs.copy()
        kwargs["preexec_fn"] = restore_signals
    return kwargs


def subprocess_call(*args, **kwargs):
    # type: (Any, Any) -> int
    return subprocess.call(*args, **add_restore_signals(kwargs))


def subprocess_popen(*args, **kwargs):
    # type: (Any, Any) -> subprocess.Popen
    return subprocess.Popen(*args, **add_restore_signals(kwargs))


def svn_call(args=None):
    # type: (Optional[List[str]]) -> None
    if args is None:
        args = []
    subprocess_args = [state.SVN] + args
    ret_code = subprocess_call(subprocess_args)
    if ret_code != 0:
        raise SvnError(
            "failing return code %d for external program:\n  %s"
            % (ret_code, " ".join(subprocess_args))
        )


def read_into_queue(input_io, input_queue):
    # type: (BinaryIO, queue.Queue) -> None
    block_size = 8192
    while True:
        raw_bytes = input_io.read(block_size)
        input_queue.put(raw_bytes)
        if not raw_bytes:
            break


def line_gen(path_or_fd, partial_line_timeout=0.2, encoding=None):
    # type: (Union[str, int], float, str) -> Iterator[str]
    if encoding is None:
        encoding = locale.getpreferredencoding()
    decoder = codecs.getincrementaldecoder(encoding)()
    input_io = io.open(path_or_fd, "rb", closefd=False, buffering=0)
    raw_bytes_queue = queue.Queue(10)  # type: queue.Queue[bytes]

    io_thread = threading.Thread(
        target=read_into_queue, args=(input_io, raw_bytes_queue)
    )
    io_thread.daemon = True
    io_thread.start()

    line_fragments = []  # type: List[str]
    while True:
        if line_fragments and partial_line_timeout > 0.0:
            timeout = partial_line_timeout  # type: Optional[float]
        else:
            timeout = None
        try:
            raw_bytes = raw_bytes_queue.get(timeout=timeout)
        except queue.Empty:
            # Timed out; yield the partial line.
            yield "".join(line_fragments)
            line_fragments = []
        else:
            if not raw_bytes:
                # Empty bytes indicates end-of-file.
                break
            text = decoder.decode(raw_bytes)
            line_fragments.append(text)
            if "\n" in text:
                joined_text = "".join(line_fragments)
                line_fragments = []
                for line in joined_text.splitlines(True):
                    if line.endswith("\n"):
                        yield line
                    else:
                        # Only the final line may lack a '\n'.
                        # Save this partial line for later.
                        line_fragments.append(line)

    io_thread.join()
    input_io.close()
    remainder = "".join(line_fragments)
    if remainder:
        yield remainder


def read_stderr(stderr):
    # type: (io.TextIOBase) -> None
    for line in line_gen(stderr.fileno()):
        add_stderr_text(line)
        write(wrap_color(line, "warning"), sys.stderr)


def svn_gen(args, regex=None):
    # type: (List[str], Optional[str]) -> Iterator[str]
    subprocess_args = [state.SVN] + args
    svn = subprocess_popen(
        subprocess_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    t = threading.Thread(target=read_stderr, args=(svn.stderr,))
    t.daemon = True
    t.start()

    within_partial_line = False
    for line in line_gen(svn.stdout.fileno()):
        is_partial = not line.endswith("\n")
        if within_partial_line or is_partial:
            write(line)
        else:
            line = line.rstrip("\r\n")
            if regex is None or not re.search(regex, line):
                yield line
        within_partial_line = is_partial

    t.join()
    svn.wait()
    ret_code = svn.returncode
    if ret_code != 0:
        raise SvnError(
            "failing return code %d for external program:\n  %s"
            % (ret_code, " ".join(subprocess_args))
        )


def svn_gen_cmd(cmd, args, regex=None):
    # type: (str, List[str], Optional[str]) -> Iterator[str]
    return svn_gen([cmd] + args, regex)


def svn_revert(args):
    # type: (List[str]) -> None
    svn_call(["revert"] + args)


conflicting_lines = []


def add_conflict_line(line):
    # type: (str) -> None
    conflicting_lines.append(line)


def display_notifications():
    # type: () -> None
    if conflicting_lines:
        write_ln(
            wrap_color(
                "Total conflicts: %d" % len(conflicting_lines),
                "statusConflict",
            )
        )
        for line in conflicting_lines:
            write_ln(wrap_color(line, "statusConflict"))
    if warning_lines:
        write_ln(
            wrap_color(
                "Total svn warnings: %d" % len(warning_lines), "warning"
            )
        )
        for line in warning_lines:
            write_ln(wrap_color(line, "warning"))
    if stderr_parts:
        total_stderr_size = sum(len(line) for line in stderr_parts)
        write_ln(
            wrap_color(
                "Total characters of stderr from svn: %d" % total_stderr_size,
                "warning",
            )
        )


def split_status(status_line):
    # type: (str) -> Tuple[str, str]
    path = status_line[7:]
    if path.startswith(" "):
        path = path[1:]
    return status_line[:7], path


def svn_gen_status(status_args, modified=False, names_only=False):
    # type: (List[str], bool, bool) -> Iterator[str]
    for line in svn_gen_cmd("st", status_args, regex=STATUS_REX):
        status, name = split_status(line)
        if names_only:
            yield name
        elif modified:
            if not status.startswith("?"):
                yield name
        else:
            yield line


def svn_gen_info(info_args):
    # type: (List[str]) -> Iterator[Dict[str, str]]
    info_dict = {}
    for line in svn_gen_cmd("info", info_args):
        if ":" in line:
            key, value = line.split(":", 1)
            info_dict[key.strip()] = value.strip()
        else:
            yield info_dict
            info_dict = {}


def svn_gen_diff(args, ignore_space_change=False):
    # type: (List[str], bool) -> Iterator[str]
    cmd = ["diff"]
    if ignore_space_change:
        cmd.extend(["-x", "-b"])
    return svn_gen(cmd + args)


def wrap_diff_lines(gen):
    # type: (Iterable[str]) -> Iterator[str]
    for line in gen:
        c = line[:1]
        if c == "+":
            line = wrap_color(line, "diffAdd")
        elif c == "-":
            line = wrap_color(line, "diffRemoved")
        elif c == "@":
            line = wrap_color(line, "diffMisc")
        yield line


def write_diff_lines(gen):
    # type: (Iterable[str]) -> None
    for line in wrap_diff_lines(gen):
        write_ln(line)


def wrap_status_lines(gen):
    # type: (Iterable[str]) -> Iterator[str]
    for line in gen:
        c = line[:1]
        if (
            line.startswith("Checked out")
            or line.startswith("Updated to revision")
            or line.startswith("At revision")
        ):
            line = wrap_color(line, "status")
        elif c == "A":
            line = wrap_color(line, "statusAdded")
        elif c == "D":
            line = wrap_color(line, "statusDeleted")
        elif c == "U":
            line = wrap_color(line, "statusUpdated")
        elif c == "C":
            add_conflict_line(line)
            line = wrap_color(line, "statusConflict")
        elif c == "M":
            line = wrap_color(line, "statusModified")
        elif c == "G":
            line = wrap_color(line, "statusMerged")
        elif c == "?":
            line = wrap_color(line, "statusUntracked")
        yield line


def write_status_lines(gen):
    # type: (Iterable[str]) -> None
    for line in wrap_status_lines(gen):
        write_ln(line)


def write_update_lines(gen):
    # type: (Iterable[str]) -> None
    for line in wrap_status_lines(gen):
        write_ln(line)


def wrap_log_lines(gen):
    # type: (Iterable[str]) -> Iterator[str]
    log_re = re.compile(r"^(r\d+) \| (.*) \| (.*) \| (\d+ lines?)$")
    separator_line = 72 * "-"

    for line in gen:
        m = log_re.match(line)
        if m:
            # Do stuff...
            field_separator = wrap_color("|", "logFieldSeparator")
            line = "%s %s %s %s %s %s %s" % (
                wrap_color(m.group(1), "logRev"),
                field_separator,
                wrap_color(m.group(2), "logCommitter"),
                field_separator,
                wrap_color(m.group(3), "logDate"),
                field_separator,
                wrap_color(m.group(4), "logNumLines"),
            )
            yield line
        elif line == separator_line:
            yield wrap_color(line, "logSeparator")
        else:
            yield wrap_color(line, "logText")


def write_log_lines(gen):
    # type: (Iterable[str]) -> None
    for line in wrap_log_lines(gen):
        write_ln(line)


class ExtDiffer:
    def reset(self):
        # type: () -> None
        self.prop_index = 0
        self.prop_lines = [[], []]  # type: List[List[str]]

    def __init__(self, ignore_space_change):
        # type: (bool) -> None
        self.ignore_space_change = ignore_space_change
        self.reset()

    def add_line(self, line):
        # type: (str) -> None
        if re.match(r"\s+- ", line):
            self.prop_index = 0
            line = line.lstrip()[2:]
        elif re.match(r"\s+\+ ", line):
            self.prop_index = 1
            line = line.lstrip()[2:]
        if self.ignore_space_change:
            line = " ".join(line.strip().split()) + "\n"
        self.prop_lines[self.prop_index].append(line)

    def gen_diff_lines(self):
        # type: () -> Iterator[str]
        new_prop_lines = self.prop_lines[1]
        extra_line = None  # type: Optional[str]
        if new_prop_lines and new_prop_lines[-1].strip() == "":
            extra_line = new_prop_lines.pop()
        if self.prop_lines[0] or self.prop_lines[1]:
            delta = difflib.unified_diff(
                self.prop_lines[0],
                self.prop_lines[1],
                n=0,
                fromfile="Old externals",
                tofile="New externals",
            )
            for d in delta:
                yield d
        self.reset()
        if extra_line is not None:
            yield extra_line


def diff_filter(lines, ignore_space_change=False):
    # type: (Iterable[str], bool) -> Iterator[str]
    ext_differ = ExtDiffer(ignore_space_change)
    in_ext = False
    expecting_first_line = False
    for line in lines:
        if in_ext:
            if re.match(r"\w+:\s", line):
                for d in ext_differ.gen_diff_lines():
                    yield d
                yield line
                in_ext = False
            elif expecting_first_line and re.match(r"## .* ##$", line):
                # Newer svn clients (1.7 and later) already perform
                # line-by-line diff of svn:externals, detectable by the
                # presence of a position indicator such as ``## -1 +1,2 ##``
                # on the first line of the svn:externals output.
                yield line
                in_ext = False
            else:
                ext_differ.add_line(line)
            expecting_first_line = False
        elif re.match(r"(Name|Modified): svn:externals", line):
            yield line
            in_ext = True
            expecting_first_line = True
        else:
            yield line
    if in_ext:
        for d in ext_differ.gen_diff_lines():
            yield d


def common_prefix(
    seq1,  # type: Iterable[Any]
    seq2,  # type: Iterable[Any]
    parts_equal=lambda part1, part2: part1
    == part2,  # type: Callable[[Any, Any], bool]
):
    # type: (...) -> List[Any]
    prefix = []
    for part1, part2 in zip(seq1, seq2):
        if parts_equal(part1, part2):
            prefix.append(part1)
        else:
            break
    return prefix


def paths_equal(path1, path2):
    # type: (str, str) -> bool
    return os.path.normcase(path1) == os.path.normcase(path2)


def rel_path(wc_path, start_dir="."):
    # type: (str, str) -> str
    dest_path_parts = os.path.abspath(wc_path).split(os.sep)
    start_dir_parts = os.path.abspath(start_dir).split(os.sep)
    common_parts_len = len(
        common_prefix(dest_path_parts, start_dir_parts, paths_equal)
    )
    num_directories_up = len(start_dir_parts) - common_parts_len
    return os.path.normpath(
        os.path.join(
            os.sep.join([os.pardir] * num_directories_up),
            os.sep.join(dest_path_parts[common_parts_len:]),
        )
    )


def rel_walk(top):
    # type: (str) -> Iterator[Tuple[str, List[str], List[str]]]
    for root, dirs, files in os.walk(top):
        for d in [".svn", "_svn"]:
            if d in dirs:
                dirs.remove(d)
        yield root, dirs, files


def is_svn_dir(path):
    # type: (str) -> bool
    return os.path.isdir(os.path.join(path, ".svn"))


def svn_merge_raw(raw_root, wc_root):
    # type: (str, str) -> None
    # @bug Cannot handle changing a file into a directory or vice-versa.
    if not os.path.isdir(raw_root):
        print("not a directory: %r" % raw_root)
        return
    if is_svn_dir(raw_root):
        print("cannot use Subversion working copy: %r" % raw_root)
        return
    if not is_svn_dir(wc_root):
        print("not a Subversion working copy: %r" % wc_root)
        return
    for root, dirs, files in rel_walk(raw_root):
        for d in dirs:
            raw_path = os.path.join(root, d)
            rel = rel_path(raw_path, raw_root)
            wc_path = os.path.join(wc_root, rel)
            if not os.path.isdir(wc_path):
                print("adding directory %r" % rel)
                shutil.copytree(raw_path, wc_path)
                svn_call(["add", wc_path])
                dirs.remove(d)
        for f in files:
            raw_path = os.path.join(root, f)
            rel = rel_path(raw_path, raw_root)
            wc_path = os.path.join(wc_root, rel)
            already_added = os.path.isfile(wc_path)
            print("copying file %r" % rel)
            shutil.copyfile(raw_path, wc_path)
            if not already_added:
                print("adding file %r" % rel)
                svn_call(["add", wc_path])

    for root, dirs, files in rel_walk(wc_root):
        for d in dirs:
            wc_path = os.path.join(root, d)
            rel = rel_path(wc_path, wc_root)
            raw_path = os.path.join(raw_root, rel)
            if not os.path.isdir(raw_path):
                print("removing directory %r" % rel)
                svn_call(["rm", wc_path])
                dirs.remove(d)
        for f in files:
            wc_path = os.path.join(root, f)
            rel = rel_path(wc_path, wc_root)
            raw_path = os.path.join(raw_root, rel)
            if not os.path.isfile(raw_path):
                print("removing file %r" % rel)
                svn_call(["rm", wc_path])


def get_user():
    # type: () -> str
    return get_environ("USER")


def svn_url_split_peg(url):
    # type: (str) -> Tuple[str, str]
    m = re.match(r"(.*)(@\d+)$", url)
    if m:
        new_url, peg = m.group(1), m.group(2)
    else:
        new_url, peg = url, ""
    return new_url, peg


def svn_url_split(url):
    # type: (str) -> Tuple[str, str, str]
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
        """,
        url,
        re.MULTILINE | re.VERBOSE,
    )
    if m:
        return m.group("head"), m.group("middle"), m.group("tail")
    else:
        return url, "", ""


def svn_url_join(head, middle, tail=""):
    # type: (str, str, str) -> str
    url = head
    middle = middle.strip("/")
    tail = tail.strip("/")
    if middle:
        if not url.endswith("/"):
            url += "/"
        url += middle
    if tail:
        if tail[0] in "@/" or url.endswith("/"):
            url += tail
        else:
            url += "/" + tail
    return url


def svn_url_split_head(url):
    # type: (str) -> str
    head, middle, tail = svn_url_split(url)
    return head


def svn_url_split_tail(url):
    # type: (str) -> str
    head, middle, tail = svn_url_split(url)
    return tail


def is_url(path):
    # type: (str) -> bool
    return re.match(r"\w+://", path) is not None


def svn_get_url(path):
    # type: (str) -> str
    # If this is already a URL, return it unchanged.
    if is_url(path):
        return path
    info_dict_list = list(svn_gen_info([path]))
    try:
        info_dict = info_dict_list[0]
        return info_dict["URL"]
    except (IndexError, KeyError):
        raise SvnError("invalid subversion path %r" % path)


def svn_get_url_split(path):
    # type: (str) -> Tuple[str, str, str]
    return svn_url_split(svn_get_url(path))


def svn_get_url_head(url):
    # type: (str) -> str
    return svn_url_split_head(svn_get_url(url))


def svn_get_url_tail(url):
    # type: (str) -> str
    return svn_url_split_tail(svn_get_url(url))


def svn_url_map(url):
    # type: (str) -> str

    # Maps "key" into head-relative path (starting at repository root).
    head_map = {
        "tr": "trunk",
        "br": "branches",
        "tag": "tags",
        "rel": "tags/release",
        "gb": "branches/guests",
        "gt": "tags/guests",
        "mb": "branches/guests/",
        "mt": "tags/guests/",
    }

    debug_ln("mapping %s" % repr(url))
    url_history = set()  # type: Set[str]
    aliases = get_aliases()
    while True:
        m = re.match(
            r"""
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
            """,
            url,
            re.MULTILINE | re.VERBOSE,
        )

        if m and m.group("alias"):
            alias = m.group("alias")
            after = m.group("alias_after")
            try:
                url = aliases[alias] + after
            except KeyError:
                raise SvnError("undefined alias %r" % alias)
        elif m and m.group("url"):
            url = m.group("url")
        elif m and m.group("key"):
            before = m.group("key_before")
            key = m.group("key")
            after = m.group("key_after")
            if key == "pr":
                url = get_environ("P")
            elif key == "pp":
                url = get_environ("PP")
            elif key in head_map:
                url = svn_url_join(svn_get_url_head(before), head_map[key])
                if key in ("mb", "mt"):
                    url = svn_url_join(url, get_user())
            elif key == "ws":
                ws_head, ws_middle, ignored_tail = svn_get_url_split(before)
                if not ws_middle:
                    ws_middle = "trunk"
                ws_middle += "/workspace"
                url = svn_url_join(ws_head, ws_middle)
            else:
                raise SvnError("unknown keyword '%s:' in URL" % key)

            url = svn_url_join(url, "", after)
        else:
            break
        if url in url_history:
            raise SvnError("mapping loop for URL %r" % url)
        url_history.add(url)
        debug_ln("        %s" % repr(url))

    debug_ln("    ==> %s" % repr(url))
    return url


def make_commands(commands_text):
    # type: (str) -> Tuple[Set[str], Dict[str, str]]
    commands = set()
    aliases = {}
    for line in commands_text.strip().splitlines():
        parts = remove_chars(line.strip(), "(,)").split()
        cmd = parts[0]
        rest = parts[1:]
        commands.add(cmd)
        for alias in rest:
            aliases[alias] = cmd
    return commands, aliases


# From "svn help":
builtin_commands_text = """
add
auth
blame (praise, annotate, ann)
cat
changelist (cl)
checkout (co)
cleanup
commit (ci)
copy (cp)
delete (del, remove, rm)
diff (di)
export
help (?, h)
import
info
list (ls)
lock
log
merge
mergeinfo
mkdir
move (mv, rename, ren)
patch
propdel (pdel, pd)
propedit (pedit, pe)
propget (pget, pg)
proplist (plist, pl)
propset (pset, ps)
relocate
resolve
resolved
revert
status (stat, st)
switch (sw)
unlock
update (up)
upgrade
"""

extra_commands_text = """
diff (ediff)
bdiff (ebdiff)
kdiff3 (kdiff)
"""

builtin_commands, builtin_command_aliases = make_commands(
    builtin_commands_text
)
extra_commands, extra_command_aliases = make_commands(extra_commands_text)

all_commands = builtin_commands.union(extra_commands)
all_command_aliases = builtin_command_aliases.copy()
all_command_aliases.update(extra_command_aliases)


zero_arg_switches = set(
    """
--adds-as-modification
--allow-mixed-revisions
--auto-props
--diff
--dry-run
--force
--force-interactive
--force-log
--git
--help
--human-readable
--ignore-ancestry
--ignore-externals
--ignore-keywords
--ignore-properties
--ignore-whitespace
--include-externals
--incremental
--internal-diff
--keep-changelists
--keep-local
--log
--no-auth-cache
--no-auto-props
--no-diff-added
--no-diff-deleted
--no-ignore
--no-newline
--no-unlock
--non-interactive
--non-recursive
--notice-ancestry
--parents
--patch-compatible
--pin-externals
--properties-only
--quiet
--record-only
--recursive
--reintegrate
--relocate
--remove
--remove-added
--remove-ignored
--remove-unversioned
--reverse-diff
--revprop
--show-copies-as-adds
--show-inherited-props
--show-item
--show-passwords
--show-updates
--stop-on-copy
--strict
--summarize
--trust-server-cert
--use-merge-history
--vacuum-pristines
--verbose
--version
--with-all-revprops
--with-no-revprops
--xml
-?
-H
-N
-R
-g
-q
-u
-v
""".split()
)

one_arg_switches = set(
    """
--accept
--change
--changelist
--cl
--config-dir
--config-option
--depth
--diff-cmd
--diff3-cmd
--editor-cmd
--encoding
--extensions
--file
--limit
--message
--native-eol
--new
--old
--password
--revision
--search
--search-and
--set-depth
--show-revs
--strip
--targets
--username
--with-revprop
-F
-c
-l
-m
-r
-x
""".split()
)

switch_to_arg_count_map = {}
for arg in zero_arg_switches:
    switch_to_arg_count_map[arg] = 0
for arg in one_arg_switches:
    switch_to_arg_count_map[arg] = 1


def get_switch_arg_count(s):
    # type: (str) -> int
    try:
        return switch_to_arg_count_map[s]
    except KeyError:
        raise SvnError("invalid switch %r" % s)


def url_map_args(cmd, pos_args):
    # type: (str, List[str]) -> List[str]
    if cmd in "propset pset ps".split():
        num_unmappable_pos_args = 2
    elif (
        cmd
        in """
            propdel pdel pd
            propedit pedit pe
            propget pget pg""".split()
    ):
        num_unmappable_pos_args = 1
    else:
        num_unmappable_pos_args = 0
    return pos_args[:num_unmappable_pos_args] + [
        svn_url_map(arg) for arg in pos_args[num_unmappable_pos_args:]
    ]


def adjust_url_for_wc_path(url, wc_path):
    # type: (str, str) -> str
    new_url = url
    url_base, url_peg = svn_url_split_peg(url)
    if url_base.endswith("/."):
        write_ln("Skipping adjustment for URL ending with '/.':")
        write_ln("  %s" % wrap_color(url, "info"))
    else:
        wc_tail = svn_get_url_tail(wc_path)
        url_head, url_middle, url_tail = svn_url_split(url_base)
        new_url = svn_url_join(url_head, url_middle, wc_tail) + url_peg
        if new_url != url:
            write_ln("Adjusting URL to match working copy tail:")
            write_ln("  Was: %s" % wrap_color(url, "info"))
            write_ln("  Now: %s" % wrap_color(new_url, "info"))
            write_ln(
                "  (append %s to URL to avoid adjustment)"
                % wrap_color("'/.'", "info")
            )
    return new_url


def help_wrap(summary=False):
    # type: (bool) -> None
    if summary:
        write(
            """
Type 'svn helpwrap' for help on svnwrap extensions.
Type 'svn readme' to view the svnwrap README.rst file.
"""
        )
    else:
        write_ln(
            """
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
pdiff             - generate ``patch``-compatible diff; equivalent to:
                    ``diff --diff-cmd diff -x -U1000000 --patch-compatible``
mergeraw RAWPATH [WCPATH]
                  - merge raw (non-SVN) tree into working copy
ee                - propedit svn:externals
ei                - propedit svn:ignore
pge               - propget svn:externals
pgi               - propget svn:ignore
url               - show URL as received from "svn info"
helpwrap          - this help
readme            - show svnwrap README.rst

svnwrap options:
  --color on|off|auto       use color in output (defaults to auto)
  --no-pager                disable the automatic use of a pager
  --ie                      abbreviation for ``--ignore-externals``
  --debug                   enable debug printing (mainly for maintainer use)
  --svn path/to/svn         change path to ``svn`` utility (mainly for testing)

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

NOTE: To avoid URL adjustment, append "/." to the end of the URL, e.g.:
  svn switch ^/branches/somebranch/.

If your editor isn't launching correctly, setup SVN_EDITOR.
For more details, see the README.rst file distributed with svnwrap
(displayable via 'svn readme').

""".strip()
            % dict(
                svnwrap_ini_path=get_svnwrap_ini_path(), version=__version__,
            )
        )


def parse_switch(switch, args):
    # type: (str, List[str]) -> List[str]
    attached_arg = None  # type: Optional[str]
    if switch == "-":
        raise SvnError("invalid switch '-'")
    elif switch.startswith("--"):
        if "=" in switch:
            switch, attached_arg = switch.split("=", 1)
    else:
        switch, rest = switch[:2], switch[2:]
        if rest:
            # What follows is either another switch or an attached_arg.
            if get_switch_arg_count(switch) > 0:
                attached_arg = rest
            elif rest.startswith("-"):
                raise SvnError("Invalid short switch '-'")
            else:
                # Retain additional switches for next pass.
                args.insert(0, "-" + rest)
    switch_args = [switch]
    switch_arg_count = get_switch_arg_count(switch)
    if attached_arg is not None:
        if switch_arg_count == 0:
            raise SvnError("switch %s takes no arguments" % switch)
        args.insert(0, attached_arg)
    if switch_arg_count > len(args):
        raise SvnError(
            "switch %s requires %d argument%s"
            % (arg, switch_arg_count, switch_arg_count > 1 and "s" or "")
        )
    switch_args.extend(args[:switch_arg_count])
    del args[:switch_arg_count]
    return switch_args


def parse_args_color(args):
    # type: (List[str]) -> None
    if args:
        color_flag = args.pop(0)
    else:
        color_flag = ""
    if color_flag == "on":
        state.using_color = True
    elif color_flag == "off":
        state.using_color = False
    elif color_flag != "auto":
        help_wrap(summary=True)
        sys.exit()


def parse_args():
    # type: () -> Tuple[List[str], List[str]]
    """Return (switch_args, pos_args)."""

    debug_arg_parsing = False
    switch_args = []
    pos_args = []
    args = sys.argv[1:]
    while args:
        arg = args.pop(0)
        if arg == "--debug-args":
            debug_arg_parsing = True
        elif arg == "--debug":
            state.debugging = True
        elif arg == "--svn":
            if not args:
                raise SvnError("missing argument for switch %s" % arg)
            state.SVN = os.path.abspath(args.pop(0))
        elif arg == "--color":
            parse_args_color(args)
        elif arg == "--no-pager":
            state.use_pager = False
        elif arg == "--ie":
            args.insert(0, "--ignore-externals")
        elif arg.startswith("-"):
            switch_args.extend(parse_switch(arg, args))
        else:
            pos_args.append(arg)
    if debug_arg_parsing:
        write_ln("switch_args = %s" % repr(switch_args))
        write_ln("pos_args = %s" % repr(pos_args))
        sys.exit()
    return switch_args, pos_args


def setup_svn_editor():
    # type: () -> None
    """Set SVN_EDITOR to restore stdout/stderr and chain to original editor."""

    config = subversion_config()
    editor = "vi"
    editor = get_environ("EDITOR", default=editor)
    editor = get_environ("VISUAL", default=editor)
    try:
        editor = config.get("helpers", "editor-cmd")
    except configparser.Error:
        pass
    editor = get_environ("SVN_EDITOR", default=editor)
    python = sys.executable or "python"
    if " " in python:
        # You cannot quote the SVN_EDITOR program on Windows for some reason,
        # despite claims to the contrary in the manual.  For example, when
        # using svn 1.9.2 on Windows, the following fails:
        #
        #   mkdir "c:\with spaces"
        #   copy c:\windows\notepad.exe "c:\with spaces"
        #   set SVN_EDITOR="c:\with spaces\notepad.exe"
        #   svn propedit svn:externals .
        #
        # This should launch notepad.exe from the "c:\with spaces" directory,
        # but it fails to launch anything.  It also fails to quote the path
        # to notepad.exe even when there are no spaces:
        #
        #   set SVN_EDITOR="c:\windows\notepad.exe"
        #   svn propedit svn:externals .
        #
        # Without the quotes, it works fine:
        #
        #   set SVN_EDITOR=c:\windows\notepad.exe
        #   svn propedit svn:externals .
        #
        # Therefore, if the Python interpreter on Windows lives in a path with
        # spaces, it must be on the system PATH.  On other systems, quote the
        # interpreter to protect the spaces.
        if platform_is_windows:
            python = "python"
        else:
            python = '"%s"' % python
    # Choose platform-specific device to open for access to the console.
    console_dev = "CON:" if platform_is_windows else "/dev/tty"
    s = (
        textwrap.dedent(
            r"""
        %(python)s -c "import os, subprocess, sys;
        console_fd = os.open(\"%(console_dev)s\", os.O_WRONLY);
        os.dup2(console_fd, 1);
        os.dup2(console_fd, 2);
        os.close(console_fd);
        sys.exit(subprocess.call(sys.argv[1:]))
        " %(editor)s
    """
        )
        % locals()
    )
    os.environ["SVN_EDITOR"] = "".join(s.strip().splitlines())


def setup_pager():
    # type: () -> None
    if not state.use_pager:
        return

    config = svnwrap_config()
    enabled = config_boolean(config, "pager", "enabled", True)
    use_shell = config_boolean(config, "pager", "use_shell", False)
    pager_cmd = "less -FKRX"
    pager_cmd = get_environ("PAGER", default=pager_cmd)
    if config.has_option("pager", "cmd"):
        pager_cmd = config.get("pager", "cmd")
    pager_cmd = get_environ("SVN_PAGER", default=pager_cmd)

    # If pager is disabled, nothing more to do.
    if not enabled:
        return

    try:
        if use_shell:
            state.pager = subprocess.Popen(
                pager_cmd, stdin=subprocess.PIPE, shell=True
            )
        else:
            state.pager = subprocess.Popen(
                shlex.split(pager_cmd), stdin=subprocess.PIPE
            )
    except OSError:
        # Pager is not setup correctly, or command is missing.  Let's just
        # move on.
        return

    # Create extra descriptors to the current stdout and stderr.
    stdout = os.dup(sys.stdout.fileno())
    stderr = os.dup(sys.stderr.fileno())

    # Redirect stdout and stderr into the pager.
    os.dup2(state.pager.stdin.fileno(), sys.stdout.fileno())
    if sys.stderr.isatty():
        os.dup2(state.pager.stdin.fileno(), sys.stderr.fileno())

    @atexit.register
    def killpager():
        # type: () -> None
        if hasattr(signal, "SIGINT"):
            signal.signal(signal.SIGINT, signal.SIG_IGN)

        # Restore stdout and stderr to their original state.
        os.dup2(stdout, sys.stdout.fileno())
        os.dup2(stderr, sys.stderr.fileno())

        # Wait for the pager to exit.
        if state.pager is not None:
            state.pager.stdin.close()
            state.pager.wait()


def do_cmd_helpwrap(args):
    # type: (List[str]) -> None
    setup_pager()
    help_wrap()


def do_cmd_status(args):
    # type: (List[str]) -> None
    write_status_lines(svn_gen_status(args))


def do_cmd_stnames(args):
    # type: (List[str]) -> None
    write_lines(svn_gen_status(args, names_only=True))


def do_cmd_stmod(args):
    # type: (List[str]) -> None
    write_lines(svn_gen_status(args, modified=True))


def do_cmd_stmodroot(args):
    # type: (List[str]) -> None
    d = {}
    for line in svn_gen_status(args, modified=True):
        line = re.sub(r"/.*", "", line)
        d[line] = 1
    for name in sorted(d):
        write_ln(name)


def do_cmd_stmodrevert(args):
    # type: (List[str]) -> None
    mods = [line.rstrip() for line in svn_gen_status(args, modified=True)]
    svn_revert(mods)


def do_cmd_update(args):
    # type: (List[str]) -> None
    write_update_lines(svn_gen_cmd("update", args, regex=UPDATE_REX))


def do_cmd_checkout(args):
    # type: (List[str]) -> None
    write_update_lines(svn_gen_cmd("checkout", args, regex=CHECKOUT_REX))


def do_cmd_diff(args):
    # type: (List[str]) -> None
    setup_pager()
    write_diff_lines(diff_filter(svn_gen_diff(args)))


def do_cmd_bdiff(args):
    # type: (List[str]) -> None
    setup_pager()
    write_diff_lines(
        diff_filter(
            svn_gen_diff(args, ignore_space_change=True),
            ignore_space_change=True,
        )
    )


def do_cmd_kdiff3(args):
    # type: (List[str]) -> None
    svn_call(["diff", "--diff-cmd", "kdiff3", "-x", "--qall"] + args)


def do_cmd_pdiff(args):
    # type: (List[str]) -> None
    setup_pager()
    write_diff_lines(
        diff_filter(
            svn_gen_diff(
                "--diff-cmd diff -x -U1000000 --patch-compatible".split()
                + args
            )
        )
    )


def do_cmd_mergeraw(args):
    # type: (List[str]) -> None
    if not args or len(args) > 2:
        write_ln("mergeraw RAWPATH [WCPATH]")
        sys.exit(1)
    raw_root = args.pop(0)
    if args:
        wc_root = args.pop(0)
    else:
        wc_root = "."
    svn_merge_raw(raw_root, wc_root)


def do_cmd_ee(args):
    # type: (List[str]) -> None
    if not args:
        args.append(".")
    svn_call("propedit svn:externals".split() + args)


def do_cmd_ei(args):
    # type: (List[str]) -> None
    if not args:
        args.append(".")
    svn_call("propedit svn:ignore".split() + args)


def do_cmd_pge(args):
    # type: (List[str]) -> None
    if not args:
        args.append(".")
    svn_call("propget svn:externals --strict".split() + args)


def do_cmd_pgi(args):
    # type: (List[str]) -> None
    if not args:
        args.append(".")
    svn_call("propget svn:ignore".split() + args)


def do_cmdx_url(switch_args, pos_args):
    # type: (List[str], List[str]) -> None
    if pos_args:
        for arg in pos_args:
            write_ln(svn_get_url(arg))
    else:
        write_ln(svn_get_url("."))


def do_cmdx_br(switch_args, pos_args):
    # type: (List[str], List[str]) -> None
    if len(pos_args) != 1:
        raise SvnError("br takes exactly one URL")
    # Default to branches of current URL, but absolute URL following
    # will override.
    branch = svn_url_map("br:" + pos_args[0])
    trunk = svn_url_map(branch + "/tr:")
    cp_args = ["cp", trunk, branch] + switch_args
    svn_call(cp_args)


def do_cmdx_switch(switch_args, pos_args):
    # type: (List[str], List[str]) -> None
    if 1 <= len(pos_args) <= 2 and "--relocate" not in switch_args:
        url = pos_args.pop(0)
        if pos_args:
            wc_path = pos_args.pop(0)
        else:
            wc_path = "."
        new_url = adjust_url_for_wc_path(url, wc_path)
        args = switch_args + [new_url, wc_path]
    write_update_lines(svn_gen_cmd("switch", args, regex=UPDATE_REX))


def do_cmdx_merge(switch_args, pos_args):
    # type: (List[str], List[str]) -> None
    if len(pos_args) > 1 and not is_url(pos_args[-1]):
        wc_path = pos_args.pop()
    else:
        wc_path = "."
    urls = [adjust_url_for_wc_path(url, wc_path) for url in pos_args]
    args = switch_args + urls + [wc_path]
    # Using svn_gen_cmd() during merge operation allows direct-to-tty
    # menu options to appear out-of-order with respect to
    # stdout-through-the-pipe.  So, for example, when a conflict causes an
    # interactive menu to appear, pressing "df" will generate the diff in
    # the wrong order relative to the menu.  In the example below, the
    # menu starting with "Select" should appear after the actual diff,
    # but due to lag through the pipe, the menu tends to show up first:
    #
    # Select: (p) postpone, (df) show diff, (e) edit file, (m) merge,
    #         (r) mark resolved, (mc) my side of conflict,
    #         (tc) their side of conflict, (s) show all options: --- \
    #         README.txt.working       - MINE
    # +++ README.txt  - MERGED
    # @@ -1,3 +1,7 @@
    # one
    # +<<<<<<< .working
    # from branch1.
    # +=======
    # +from trunk
    # +>>>>>>> .merge-right.r5
    # three

    # write_update_lines(svn_gen_cmd(cmd, args, regex=UPDATE_REX))
    svn_call(["merge"] + args)


def do_cmd_log(args):
    # type: (List[str]) -> None
    setup_pager()
    write_log_lines(svn_gen_cmd("log", args))


def readme():
    # type: () -> None
    setup_pager()
    import pkg_resources
    import email
    import textwrap

    try:
        dist = pkg_resources.get_distribution("svnwrap")
        meta = dist.get_metadata(dist.PKG_INFO)
    except (pkg_resources.DistributionNotFound, FileNotFoundError):
        print("Cannot access README (try installing via pip or setup.py)")
        return
    msg = email.message_from_string(meta)
    desc = msg.get("Description", "").strip()
    if not desc and not msg.is_multipart():
        desc = msg.get_payload().strip()
    if not desc:
        desc = "No README found"
    if "\n" in desc:
        first, rest = desc.split("\n", 1)
        desc = "\n".join([first, textwrap.dedent(rest)])
    print(desc)


def show_new_switches():
    # type: () -> None
    all_switches = zero_arg_switches.union(one_arg_switches)

    for cmd in sorted(builtin_commands):
        switches = set()

        # Expecting help lines of the form::
        #
        #  --targets ARG            : pass contents of file ARG...
        #  -N [--non-recursive]     : obsolete; same as --depth=empty
        #  --depth ARG              : limit operation by depth ARG...
        #
        # Throw away the colon and beyond, ditch square brackets, and
        # split one whitespace.  Keep only words beginning with a hyphen.
        # Skip lines with too much leading whitespace.
        for line in svn_gen_cmd("help", [cmd]):
            if line.startswith("     "):
                # Too much leading whitespace.
                continue
            line = line.strip()
            if ":" in line and line.startswith("-"):
                line = line.split(":")[0]
                for part in remove_chars(line, "[]").split():
                    if part.startswith("-"):
                        switches.add(part)

        new_switches = switches.difference(all_switches)
        if new_switches:
            print("New switches for {}: {}".format(cmd, new_switches))


def main():
    # type: () -> None
    # Ensure config file exists.
    svnwrap_config()
    read_color_scheme()
    setup_svn_editor()

    switch_args, pos_args = parse_args()
    cmd = None  # type: Optional[str]
    if pos_args:
        cmd = pos_args.pop(0)
        pos_args = url_map_args(cmd, pos_args)
    args = switch_args + pos_args

    if cmd is not None:
        cmd = all_command_aliases.get(cmd, cmd)

    if cmd is None:
        # No positional arguments were given.  Newer svn clients return failure
        # for no arguments at all; in this case, just print the same message
        # that ``svn`` would print without calling ``svn``.
        if switch_args:
            svn_call(args)
        else:
            write_ln("Type 'svn help' for usage.")
        if "--version" in switch_args:
            write_ln("svnwrap version %s" % __version__)
        else:
            help_wrap(summary=True)

    elif cmd == "help" and not args:
        setup_pager()
        svn_call(["help"])
        help_wrap(summary=True)

    elif cmd == "readme":
        readme()

    elif cmd == "shownewswitches":
        show_new_switches()

    else:
        func = "do_cmd_" + cmd
        funcx = "do_cmdx_" + cmd
        if func in globals():
            globals()[func](args)
        elif funcx in globals():
            globals()[funcx](switch_args, pos_args)
        else:
            svn_call([cmd] + args)


def main_with_svn_error_handling():
    # type: () -> None
    exit_status = 0
    try:
        main()
    except KeyboardInterrupt:
        add_warning_line("svnwrap: keyboard interrupt")
        exit_status = 1
    except SvnError as e:
        add_warning_line("svnwrap: %s" % e)
        exit_status = 1
    except PagerClosed:
        pass
    finally:
        display_notifications()
    sys.exit(exit_status)


def color_test():
    # type: () -> None
    for color in sorted(color_dict):
        write_ln(wrap_color("This is %s" % color, color))


if __name__ == "__main__":
    main_with_svn_error_handling()
