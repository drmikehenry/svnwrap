#!/usr/bin/env python

from setuptools import setup, find_packages

NAME = 'svnwrap'

for line in file(NAME + '.py'):
    if line.startswith('__VERSION__'):
        exec line in globals()
        break

setup(
    name=NAME,
    version=__VERSION__,
    packages=find_packages(),
    py_modules=[NAME],
    install_requires=[
    ],
    entry_points={
        'console_scripts': [
            'svnwrap = svnwrap:main_with_svn_error_handling',
        ],
    },
    description='Wrapper script for Subversion command-line client',
    keywords='svn subversion wrapper',
    url='projects/svnwrap',
    author='Michael Henry',
    author_email='drmikehenry@drmikehenry.com',
    zip_safe=True,
)
