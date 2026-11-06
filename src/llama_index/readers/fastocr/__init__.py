"""LlamaIndex readers for the FastOCR Document OCR and Bank Statement APIs."""

from ._version import __version__
from .base import FastOCRReader
from .statements import FastOCRBankStatementReader

__all__ = ["__version__", "FastOCRReader", "FastOCRBankStatementReader"]
