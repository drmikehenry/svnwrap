#!/usr/bin/env python
# coding=utf-8

import setuptools
import sys

sys_version = tuple(sys.version_info[:2])
min_version = (2, 7)
if sys_version < min_version:
    sys.exit(
        "Python version %d.%d is too old; %d.%d or newer is required."
        % (sys_version + min_version)
    )

NAME = "svnwrap"

__version__ = None
for line in open("src/{}.py".format(NAME), encoding="utf-8"):
    if line.startswith("__version__"):
        __version__ = line.split('"')[1]
        break

with open("README.rst", encoding="utf-8") as f:
    long_description = f.read()

with open("requirements.txt", encoding="utf-8") as f:
    requirements = f.read()

with open("dev-requirements.txt", encoding="utf-8") as f:
    dev_requirements = f.read()

setuptools.setup(
    name=NAME,
    version=__version__,
    packages=setuptools.find_packages("src"),
    package_dir={"": "src"},
    py_modules=[NAME],
    python_requires=">=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*",
    install_requires=requirements,
    extras_require={
        "dev": dev_requirements,
    },
    entry_points={
        "console_scripts": ["svnwrap = svnwrap:main_with_svn_error_handling"],
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
