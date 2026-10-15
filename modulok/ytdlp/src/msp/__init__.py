"""Multimedia Source Pipeline.

An AI-ready multimedia *source* ingestion pipeline:

    URL -> yt-dlp -> media + metadata.json + source.md + transcript.md
                     + integration.json  (staging/)

This package builds a *staging* repository only. It is not the production
Obsidian vault ("Manifold") and it never writes into one. See CLAUDE.md for the
boundary between the two systems and for the open Manifold-integration
decisions.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
