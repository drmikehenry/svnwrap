#!/usr/bin/env python
# coding=utf-8

import setuptools
import sys
try:
    from typing import Any, IO
except ImportError:
    pass

sys_version = tuple(sys.version_info[:2])
min_version = (2, 7)
if sys_version < min_version:
    sys.exit(
        "Python version %d.%d is too old; %d.%d or newer is required."
        % (sys_version + min_version)
    )


def open_text(name):
    # type: (str) -> IO[Any]
    if sys_version == (2, 7):
        return open(name)
    return open(name, encoding="utf-8")


NAME = "svnwrap"

__version__ = None
for line in open_text("src/{}.py".format(NAME)):
    if line.startswith("__version__"):
        __version__ = line.split('"')[1]
        break

with open_text("README.rst") as f:
    long_description = f.read()

with open_text("requirements.txt") as f:
    requirements = f.read()

with open_text("dev-requirements.txt") as f:
    dev_requirements = f.read()

setuptools.setup(
    name=NAME,
    version=__version__,
    packages=setuptools.find_packages("src"),
    package_dir={"": "src"},
    py_modules=[NAME],
    python_requires=">=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*",
    install_requires=requirements,
    extras_require={"dev": dev_requirements},
    entry_points={
        "console_scripts": [
            "svnwrap = svnwrap:main_with_svn_error_handling"
        ],
    },
    include_package_data=True,
    description="Wrapper script for Subversion command-line client",
    long_description=long_description,
    keywords="svn subversion wrapper",
    url="https://github.com/drmikehenry/svnwrap",
    author="Michael Henry",
    author_email="drmikehenry@drmikehenry.com",
    license="MIT",
    zip_safe=True,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Topic :: Software Development :: Version Control",
        "Environment :: Console",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
)
