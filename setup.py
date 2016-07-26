#!/usr/bin/env python


"""Install script for ``fishrast``."""


import itertools
import os

from setuptools import find_packages
from setuptools import setup


def _parse_dunder(line):

    """Parse a line like:

        __version__ = '1.0.1'

    and return:

        1.0.1
    """

    item = line.split('=')[1].strip()
    item = item.strip('"').strip("'")
    return item


version = author = email = source = None
with open(os.path.join('fishrast', '__init__.py')) as f:
    for line in f:
        if line.find('__version__') >= 0:
            version = _parse_dunder(line)
        elif line.find('__author__') >= 0:
            author = _parse_dunder(line)
        elif line.find('__email__') >= 0:
            email = _parse_dunder(line)
        elif line.find('__source__') >= 0:
            source = _parse_dunder(line)
        elif None not in (version, author, email, source):
            break


with open('README.rst') as f:
    readme = f.read()


extra_reqs = {'test': ['pytest>=2.8.2', 'pytest-cov>=2.2.0']}

# Add all extra requirements
extra_reqs['all'] = list(set(itertools.chain(*extra_reqs.values())))


setup(
    name='fishrast',
    packages=find_packages(exclude='tests'),
    include_package_data=True,
    classifiers=[
        'Development Status :: 1 - Planning',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Scientific/Engineering :: Information Analysis'
    ],
    version=version,
    description='Global Fishing Watch fishing rasters',
    license='Apache 2.0',
    long_description=readme,
    author=author,
    author_email=email,
    url=source,
    keywords='GFW Global Fishing Watch fishing rasters google earth engine',
    zip_safe=True,
    install_requires=['numpy'],
    extras_require=extra_reqs,
)
