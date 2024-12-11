# datamule/__init__.py
import sys
from importlib.util import find_spec
from functools import lru_cache

# Lazy load nest_asyncio only when needed
def _is_notebook_env():
    """Check if the code is running in a Jupyter or Colab environment."""
    try:
        shell = get_ipython().__class__.__name__
        return shell in ('ZMQInteractiveShell', 'Shell', 'Google.Colab')
    except NameError:
        return False

def _setup_notebook_env():
    """Setup Jupyter/Colab-specific configurations if needed."""
    if _is_notebook_env():
        import nest_asyncio
        nest_asyncio.apply()

# Rework imports, we also need to setup lazy loading
from .helper import load_package_csv, load_package_dataset
from .parser.sgml_parsing.sgml_parser_cy import parse_sgml_submission
from .submission import Submission
from .document import Document
from .parser.document_parsing.sec_parser import Parser
from .downloader.downloader import Downloader
from .downloader.premiumdownloader import PremiumDownloader


# Set up notebook environment
_setup_notebook_env()


# rework
__all__ = [
    'Downloader',
    'parse_textual_filing',
    'load_package_csv',
    'load_package_dataset',
    'Parser',
    'Filing',
    'DatasetBuilder'
]