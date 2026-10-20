"""Audion VS Engine - core orchestration package.

Public API:
  engine.runner.run_pipeline(...)   -- vspipe | ffmpeg subprocess pipe
  engine.env.build_env(...)         -- params dict -> AUDION_VS_* env vars
  engine.probe.probe(path)          -- ffprobe -> dict
  engine.paths.PATHS                -- canonical project paths
"""
from __future__ import annotations

from .paths import PATHS

__all__ = ["PATHS"]
