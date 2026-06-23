# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html
 
from collections import Counter
from collections.abc import Callable
import logging
from pathlib import Path
from typing import Literal, Protocol

logger = logging.getLogger("AppCategorizer")

AnalysisMode = Literal["local_ml", "cloud_llm"]
DEFAULT_ANALYSIS_MODE: AnalysisMode = "local_ml"
DEFAULT_LOCAL_MODEL_NAME = "all-MiniLM-L6-v2"


class ResolverLike(Protocol):
    async def resolve(self, raw_name: str) -> dict[str, list[str]]:
        ...

    def sanitize(self, raw_name: str) -> str:
        ...


class ClassifierLike(Protocol):
    def classify(self, tokens: list[str]) -> str:
        ...


class Categorizer:
    def __init__(
        self,
        resolver: ResolverLike | None = None,
        classifier: ClassifierLike | None = None,
        on_progress: Callable[[str], None] | None = None,
        model_cache_dir: str | Path | None = None,
    ):
        self.on_progress = on_progress
        self.model_cache_dir = Path(model_cache_dir) if model_cache_dir is not None else None

        if resolver is None or classifier is None:
            self._progress("Loading libraries...")

        if resolver is None:
            from .engine.resolver import Resolver

            resolver = Resolver()

        self.resolver = resolver
        self.classifier = classifier
        self._local_ml_classifiers: dict[str, ClassifierLike] = {}

    def _progress(self, message: str) -> None:
        if self.on_progress is not None:
            self.on_progress(message)

    def _get_local_classifier(
        self,
        local_model_name: str,
    ) -> ClassifierLike:
        if not isinstance(local_model_name, str) or not local_model_name.strip():
            raise ValueError("local_model_name must be a non-empty string.")

        if self.classifier is not None:
            return self.classifier

        if local_model_name not in self._local_ml_classifiers:
            from .engine.embedding_classifier import EmbeddingClassifier

            self._progress("Initializing model in memory...")
            if EmbeddingClassifier.need_download(local_model_name, self.model_cache_dir):
                self._progress("Downloading model for the first time (this may take a moment)...")
            else:
                self._progress("Model found locally, loading from disk...")

            self._local_ml_classifiers[local_model_name] = EmbeddingClassifier(
                local_model_name,
                cache_dir=self.model_cache_dir,
            )

        return self._local_ml_classifiers[local_model_name]

    def _get_llm_classifier(
        self,
        llm_provider: str | None,
        llm_model: str | None,
        llm_api_key: str | None,
        llm_base_url: str | None,
    ):
        from .engine.llm_classifier import LLMClassifier, KNOWN_PROVIDERS

        if not llm_provider:
            raise ValueError(
                f"analysis_mode='cloud_llm' requires llm_provider. "
                f"Supported providers: {', '.join(KNOWN_PROVIDERS)}"
            )

        return LLMClassifier(
            provider=llm_provider,
            model=llm_model,
            api_key=llm_api_key,
            base_url=llm_base_url,
        )

    async def resolve_and_classify(
        self,
        app_name: str,
        analysis_mode: AnalysisMode = DEFAULT_ANALYSIS_MODE,
        local_model_name: str = DEFAULT_LOCAL_MODEL_NAME,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        llm_api_key: str | None = None,
        llm_base_url: str | None = None,
    ) -> str:
        if not isinstance(app_name, str) or not app_name.strip():
            raise ValueError("app_name must be a non-empty string.")

        if analysis_mode not in ("local_ml", "cloud_llm"):
            raise ValueError("analysis_mode must be 'local_ml' or 'cloud_llm'.")

        # ------------------------------------------------------------------ #
        # cloud_llm: bypass the resolver entirely, send the sanitized name    #
        # directly to the LLM. No metadata sources are queried.               #
        # ------------------------------------------------------------------ #
        if analysis_mode == "cloud_llm":
            llm_classifier = self._get_llm_classifier(
                llm_provider=llm_provider,
                llm_model=llm_model,
                llm_api_key=llm_api_key,
                llm_base_url=llm_base_url,
            )
            cleaned_name = self.resolver.sanitize(app_name)
            provider_label = f"{llm_provider}/{llm_model}" if llm_model else llm_provider
            self._progress(f"Classifying '{cleaned_name}' with {provider_label}...")
            return await llm_classifier.classify(cleaned_name)

        # ------------------------------------------------------------------ #
        # local_ml: collect metadata from all sources, then embed + vote.     #
        # ------------------------------------------------------------------ #
        classifier = self._get_local_classifier(local_model_name)

        self._progress(f"Searching metadata for: '{app_name}'...")
        source_tokens = await self.resolver.resolve(app_name)

        if not source_tokens:
            return "Others"

        predicted_categories = []
        self._progress("Classifying results...")

        for source_name, tokens in source_tokens.items():
            category = classifier.classify(tokens)
            predicted_categories.append(category)
            logger.debug(f"[CLASSIFIER] {source_name} -> {category}")

        real_categories = [category for category in predicted_categories if category != "Others"]
        if not real_categories:
            return "Others"

        counter = Counter(real_categories)
        return counter.most_common(1)[0][0]