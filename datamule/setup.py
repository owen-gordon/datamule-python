from setuptools import setup, Extension
import platform
import os

# ======================================================
# This setup.py is kept primarily for Cython extensions.
# Most package metadata and configuration is now defined
# in pyproject.toml using modern standards.
# ======================================================

# Platform-specific settings for Cython build
include_dirs = []
library_dirs = []

# Only add Windows paths if on Windows
if platform.system() == "Windows":
    sdk_paths = [
        r"C:\Program Files (x86)\Windows Kits\10\Include\10.0.22621.0\ucrt",
        r"C:\Program Files (x86)\Windows Kits\10\Include\10.0.22621.0\shared",
        r"C:\Program Files (x86)\Windows Kits\10\Include\10.0.22621.0\um",
    ]
    lib_paths = [
        r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.22621.0\um\x64",
        r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.22621.0\ucrt\x64",
    ]
    # Filter paths that actually exist
    include_dirs = [path for path in sdk_paths if os.path.exists(path)]
    library_dirs = [path for path in lib_paths if os.path.exists(path)]

# Define Cython extension
extensions = [
    Extension(
        # Ensure the name matches the structure defined in pyproject.toml packages
        "datamule.parser.sgml_parsing.sgml_parser_cy",
        # Source file relative to this setup.py
        ["datamule/parser/sgml_parsing/sgml_parser_cy.pyx"],
        include_dirs=include_dirs,
        library_dirs=library_dirs,
    )
]

# Attempt to cythonize the extensions if Cython is available
# Build dependencies (including Cython) are specified in pyproject.toml
try:
    from Cython.Build import cythonize

    # Cython compiler directives
    cython_directives = {
        "language_level": "3",
        "boundscheck": False,
        "wraparound": False,
        "initializedcheck": False,
        "cdivision": True,
    }
    ext_modules = cythonize(
        extensions,
        compiler_directives=cython_directives,
        annotate=False,  # Typically False for production builds
    )
except ImportError:
    print(
        "Cython not found. Building extension from C source if available, or skipping."
    )
    # Check if the .c file exists as a fallback
    c_source_file = "datamule/parser/sgml_parsing/sgml_parser_cy.c"
    if os.path.exists(c_source_file):
        print(f"Found C source: {c_source_file}")
        extensions[0].sources = [c_source_file]  # Switch to .c file
        ext_modules = extensions
    else:
        print("C source not found. Extension will not be built.")
        ext_modules = (
            []
        )  # Don't build the extension if Cython isn't there and no .c file

# Minimal setup() call, only specifying extensions.
# All other metadata (name, version, packages, dependencies, etc.)
# is defined in pyproject.toml.
setup(ext_modules=ext_modules)
