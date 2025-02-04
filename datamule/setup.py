from setuptools import setup, Extension
from pathlib import Path
import platform
import os
from setuptools import find_namespace_packages

# Platform-specific settings
include_dirs = []
library_dirs = []

# Only add Windows paths if on Windows
if platform.system() == "Windows":
    sdk_paths = [
        r"C:\Program Files (x86)\Windows Kits\10\Include\10.0.22621.0\ucrt",
        r"C:\Program Files (x86)\Windows Kits\10\Include\10.0.22621.0\shared",
        r"C:\Program Files (x86)\Windows Kits\10\Include\10.0.22621.0\um"  # Added this for basetsd.h
    ]
    lib_paths = [
        r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.22621.0\um\x64",
        r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.22621.0\ucrt\x64"
    ]
    include_dirs = [path for path in sdk_paths if os.path.exists(path)]
    library_dirs = [path for path in lib_paths if os.path.exists(path)]

# Define extension without cythonize initially
extensions = [
    Extension(
        "datamule.parser.sgml_parsing.sgml_parser_cy",
        ["datamule/parser/sgml_parsing/sgml_parser_cy.pyx"],
        include_dirs=include_dirs,
        library_dirs=library_dirs,
    )
]

# Try to import Cython and cythonize the extensions
try:
    from Cython.Build import cythonize
    # Cython compiler directives
    cython_directives = {
        'language_level': "3",
        'boundscheck': False,
        'wraparound': False,
        'initializedcheck': False,
        'cdivision': True,
    }
    ext_modules = cythonize(
        extensions,
        compiler_directives=cython_directives,
        annotate=True
    )
except ImportError:
    ext_modules = extensions

extras = {
    "mulebot": ['openai'],
    "mulebot_server": ['flask'],
    "dataset_builder": ['pandas', 'google-generativeai', 'psutil']
}

all_dependencies = set(dep for extra_deps in extras.values() for dep in extra_deps)
extras["all"] = list(all_dependencies)

setup(
    name="datamule",
    author="John Friedman",
    version="0.426",
    description="Making it easier to use SEC filings.",
    packages=find_namespace_packages(include=['datamule*']),
    url="https://github.com/john-friedman/datamule-python",
    install_requires=[
        'setuptools>=40.8.0',
        'aiohttp',
        'aiolimiter',
        'tqdm',
        'requests',
        'nest_asyncio',
        'aiofiles',
        'polars',
        'selectolax',
        'pytz',
        'zstandard'
    ],
    setup_requires=[
        'setuptools>=40.8.0',
        'cython>=0.29.0',
        'wheel>=0.33.0',
    ],
    ext_modules=ext_modules,
    extras_require=extras,
    package_data={
        "datamule": ["data/*.csv", "data/*.json"],
        "datamule.mulebot.mulebot_server": [
            "templates/*.html",
            "static/css/*.css",
            "static/scripts/*.js"
        ],
    },
    include_package_data=True,
)