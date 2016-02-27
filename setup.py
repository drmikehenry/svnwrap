#!/usr/bin/env python

from setuptools import setup, find_packages

NAME = 'svnwrap'

for line in file(NAME + '.py'):
    if line.startswith('__version__'):
        __version__ = line.split("'")[1]
        break

description = 'Wrapper script for Subversion command-line client',

long_description = """\
Svnwrap extends the functionality of svn, the command-line interface for the
Subversion version control system.  Extensions provide for simplified syntax,
color highlighting, suppression of "noisy" output, and abbreviations for
common commands and URL manipulations.
"""

setup(
    name=NAME,
    version=__version__,
    description=description,
    long_description=long_description,
    classifiers=[
        'Topic :: Software Development :: Version Control',
        'Programming Language :: Python :: 2',
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: MIT License',
    ],
    keywords='svn subversion wrapper',
    url='projects/svnwrap',
    author='Michael Henry',
    author_email='drmikehenry@drmikehenry.com',
    license='MIT',
    data_files=['LICENSE', 'README.rst'],
    packages=find_packages(),
    py_modules=[NAME],
    install_requires=[
    ],
    entry_points={
        'console_scripts': [
            'svnwrap = svnwrap:main_with_svn_error_handling',
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
