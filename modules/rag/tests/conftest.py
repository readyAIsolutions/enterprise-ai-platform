"""Pytest bootstrap for the RAG module.

The RAG submodules (chunking, embeddings, retrieval, reranking, context_assembly,
citations, pipeline) are real and import cleanly through the package. No
namespace-package shim is needed; this conftest just ensures the repo root is on
sys.path so `modules.*` and `enterprise.*` imports resolve identically in every
checkout layout.
"""
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
