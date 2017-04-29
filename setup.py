#!/usr/bin/env python

from setuptools import setup, find_packages
import sys

sys_version = tuple(sys.version_info[:2])
min_version = (2, 6)
if sys_version < min_version:
    sys.exit('Python version %d.%d is too old; %d.%d or newer is required.' %
             (sys_version + min_version))

NAME = 'svnwrap'

for line in open(NAME + '.py'):
    if line.startswith('__version__'):
        __version__ = line.split("'")[1]
        break

description = 'Wrapper script for Subversion command-line client'

setup(
    name=NAME,
    version=__version__,
    description=description,
    long_description=open('README.rst').read(),
    classifiers=[
        'Topic :: Software Development :: Version Control',
        'Environment :: Console',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Development Status :: 5 - Production/Stable',
    ],
    keywords='svn subversion wrapper',
    url='https://github.com/drmikehenry/svnwrap',
    author='Michael Henry',
    author_email='drmikehenry@drmikehenry.com',
    license='MIT',
    packages=find_packages(),
    py_modules=[NAME],
    install_requires=[
        'colorama',
    ],
    entry_points={
        'console_scripts': [
            'svnwrap = svnwrap:main_with_svn_error_handling',
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
