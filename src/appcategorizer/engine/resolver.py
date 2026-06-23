# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import asyncio
import httpx
import re

from .logger import logger

class Resolver:
    # Hard ceiling for a single source. The shared httpx client uses a 5 s
    # timeout, but the Playwright-backed sources drive their own headless
    # browser and ignore it, so without this a hung browser could stall the
    # whole gather. Generous enough for the slowest source (MyAbandonware
    # waits up to ~10 s on Cloudflare) while still bounding the worst case.
    SOURCE_TIMEOUT = 30.0

    def __init__(self):
        # Sources pull in the heavy local-ML scraping stack (playwright, bs4,
        # rapidfuzz). Cloud mode only ever calls sanitize(), so we defer
        # building them until resolve() actually needs them — keeping
        # Resolver() (and therefore Categorizer()) cheap for cloud-only users.
        self._sources: list | None = None

    def _get_sources(self) -> list:
        if self._sources is None:
            try:
                from .sources import (
                    AppleSource,
                    ArchSource,
                    DebianSource,
                    FedoraSource,
                    FlathubSource,
                    GithubSource,
                    GogSource,
                    ItchSource,
                    MicrosoftSource,
                    MyAbandonwareSource,
                    SnapcraftSource,
                    SteamSource,
                    UbuntuSource,
                    WikidataSource,
                )
            except ImportError as exc:
                raise ImportError(
                    "local_ml mode requires the local backend dependencies. "
                    "Install them with: pip install 'appcategorizer[localml]'"
                ) from exc

            self._sources = [
                AppleSource(),
                FlathubSource(),
                SnapcraftSource(),
                SteamSource(),
                ArchSource(),
                DebianSource(),
                UbuntuSource(),
                FedoraSource(),
                GithubSource(),
                WikidataSource(),
                MicrosoftSource(),
                MyAbandonwareSource(),
                GogSource(),
                ItchSource(),
            ]

        return self._sources

    def sanitize(self, raw_name: str) -> str:
        name = raw_name.lower()
        name = re.sub(r'\.(exe|app|sh|bin|com|dmg|pkg)$', '', name)
        name = re.sub(r'[-_]', ' ', name)
        return name.strip()

    # Wrap source calls so each request can be logged at dispatch time.
    async def _fetch_with_log(self, source, client, app_name):
        source_name = source.__class__.__name__
        logger.debug(f"[START] Starting request for {source_name}")
        try:
            return await asyncio.wait_for(
                source.fetch(client, app_name), timeout=self.SOURCE_TIMEOUT
            )
        except Exception as e:
            logger.error(f"[CRITICAL_ERROR] Critical error in {source_name}: {e}")
            return e

    # Logging verbosity is handled by the shared logger configuration.
    async def resolve(self, raw_name: str) -> dict[str, list[str]]:
        app_name = self.sanitize(raw_name)
        results_by_source = {}
        sources = self._get_sources()

        logger.info(f"Starting resolution with {len(sources)} parallel sources...")

        async with httpx.AsyncClient(timeout=5.0) as client:
            # Use the wrapper instead of calling source.fetch directly.
            tasks = [self._fetch_with_log(source, client, app_name) for source in sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, res in enumerate(results):
                source_name = sources[i].__class__.__name__
                
                if isinstance(res, list):
                    if res:
                        results_by_source[source_name] = res
                        logger.debug(f"[FOUND] {source_name} found: {res}")
                    else:
                        logger.debug(f"[EMPTY] {source_name} found nothing.")
                else:
                    logger.error(f"[ERROR] {source_name} returned an exception: {res}")

        return results_by_source
