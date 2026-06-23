# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import httpx
from urllib.parse import quote
from .base import BaseSource

class SnapcraftSource(BaseSource):
    async def fetch(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        # Try a direct lookup by name first.
        tokens = await self._fetch_by_name(client, app_name)
        if tokens:
            return tokens
        # Fall back to search when the direct lookup fails.
        return await self._fetch_by_search(client, app_name)

    async def _fetch_by_name(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        url = f"https://api.snapcraft.io/v2/snaps/info/{quote(app_name, safe='')}"
        try:
            response = await client.get(
                url,
                headers={**self.headers, "Snap-Device-Series": "16"},
                params={"fields": "title,name,summary,categories"}
            )
            if response.status_code != 200:
                return []

            data = response.json()

            # name is at the root, while title and summary live under "snap".
            snap = data.get("snap", {})
            package_name = data.get("name", "")
            display_name = snap.get("title", "")

            if not self.is_relevant(app_name, display_name, package_name):
                return []

            tokens = [display_name, snap.get("summary", "")]
            for cat in snap.get("categories", []):
                tokens.append(cat.get("name", "") if isinstance(cat, dict) else str(cat))

            return [t for t in tokens if t.strip()]

        except Exception as exc:
            self.log_failure("fetch snap by name", exc)
            return []

    async def _fetch_by_search(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        try:
            response = await client.get(
                "https://api.snapcraft.io/v2/snaps/find",
                headers={**self.headers, "Snap-Device-Series": "16"},
                params={"q": app_name, "fields": "title,name,summary,categories"}
            )
            if response.status_code != 200:
                return []

            results = response.json().get("results", [])
            if not results:
                return []

            for result in results:
                snap = result.get("snap", result)
                package_name = snap.get("name", "")
                display_name = snap.get("title", "")

                if not self.is_relevant(app_name, display_name, package_name):
                    continue

                tokens = [display_name, snap.get("summary", "")]
                for cat in snap.get("categories", []):
                    tokens.append(cat.get("name", "") if isinstance(cat, dict) else str(cat))

                return [t for t in tokens if t.strip()]

            return []

        except Exception as exc:
            self.log_failure("fetch snap search", exc)
            return []
