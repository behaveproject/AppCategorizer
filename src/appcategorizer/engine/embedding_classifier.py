# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import os
from pathlib import Path
import re
from platformdirs import user_cache_dir

from .logger import logger

CATEGORY_DESCRIPTIONS = {
    "Internet Browsers": "A web browser for navigating the internet, rendering HTML pages, managing bookmarks and tabs, browsing websites",
    "Productivity Tools": "Office suite, document editor, spreadsheet, task manager, note-taking, writing tool, calendar, PDF editor, AI writing assistant, project management, ChatGPT, Claude, AI tools",
    "Communication & Collaboration": (
        "Messaging app, email client, video conferencing, team chat, voice calls, "
        "social networking, workplace communication, business messaging, instant messaging, "
        "group chat, channels, direct messages, Slack, Teams, Discord"
    ),
    "Out-of-browser Entertainment": (
        "Multimedia player, media player software, video player, audio player, "
        "movie and music streaming, broadcasting, video game, game launcher, "
        "gaming platform, emulation"
    ),
    "Utilities & Maintenance": "System utility, operating system, linux distro, wsl, antivirus, VPN, disk cleaner, driver manager, file manager, system optimization",
    "Media Creation": (
        "Photo editor, image editor, image manipulation program, video editor, audio editor, "
        "3D modeling, graphic design, illustration, animation tool, drawing, painting, "
        "raster graphics, vector graphics, digital art creation"
    ),
    "Development & Programming": (
        "Code editor, IDE, compiler, terminal, version control, API client, "
        "developer framework, programming tool, repository, precompiled binaries, "
        "linux server, wsl environment"
    ),
    "Others": "Uncategorized or general purpose application",
}

CONFIDENCE_THRESHOLD = 0.25
DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_CACHE_DIR = Path(user_cache_dir("appcategorizer"))


def _configure_model_environment() -> None:
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("HF_HUB_VERBOSITY", "error")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")


def _safe_model_cache_name(model_name: str) -> str:
    model_name = model_name.strip()
    if not model_name:
        raise ValueError("model_name must not be empty.")

    if model_name == DEFAULT_MODEL_NAME:
        return "default"

    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", model_name).strip("_")
    if not safe_name:
        raise ValueError("model_name must contain at least one safe path character.")
    return safe_name


def _model_path(model_name: str, cache_dir: str | Path | None = None) -> Path:
    base_cache_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    return base_cache_dir / "models" / _safe_model_cache_name(model_name)


class EmbeddingClassifier:
    @staticmethod
    def need_download(
        model_name: str = DEFAULT_MODEL_NAME,
        cache_dir: str | Path | None = None,
    ) -> bool:
        return not _model_path(model_name, cache_dir).exists()

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        cache_dir: str | Path | None = None,
    ):
        _configure_model_environment()
        try:
            from sentence_transformers import SentenceTransformer, util
        except ImportError as exc:
            raise ImportError(
                "local_ml mode requires the local backend dependencies. "
                "Install them with: pip install 'appcategorizer[localml]'"
            ) from exc

        self.model_name = model_name
        self.local_model_path = _model_path(model_name, cache_dir)
        self._cos_sim = util.cos_sim

        # Check whether the local model is already available.
        if self.need_download(model_name, cache_dir):
            logger.info(f"Model not found locally in {self.local_model_path}")
            logger.info(f"Downloading '{model_name}'... (one-time operation)")

            # Download and cache the model on first use.
            temp_model = SentenceTransformer(model_name, trust_remote_code=False)
            temp_model.save(str(self.local_model_path))

            logger.info("Model saved successfully in the local directory.")

        # Load the cached local model.
        self.model = SentenceTransformer(
            str(self.local_model_path),
            trust_remote_code=False,
        )

        self.category_embeddings = {
            cat: self.model.encode(desc)
            for cat, desc in CATEGORY_DESCRIPTIONS.items()
            if cat != "Others"
        }

    def classify(self, tokens: list[str]) -> str:
        app_text = " ".join(t for t in tokens if t.strip())

        if not app_text:
            return "Others"

        app_embedding = self.model.encode(app_text)

        scores = {
            cat: self._cos_sim(app_embedding, emb).item()
            for cat, emb in self.category_embeddings.items()
        }

        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]

        return best_category if best_score >= CONFIDENCE_THRESHOLD else "Others"
