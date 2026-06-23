# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import httpx
from .base import BaseSource

class SteamSource(BaseSource):
    async def fetch(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        try:
            # Search for the Steam app ID.
            search_response = await client.get(
                "https://store.steampowered.com/api/storesearch/",
                params={"term": app_name, "l": "english", "cc": "US"},
                headers=self.headers,
            )
            if search_response.status_code != 200:
                return []

            search_data = search_response.json()
            items = search_data.get("items", [])
            if not items:
                return []
            
            if not self.is_relevant(app_name, items[0].get("name", "")):
                return []

            appid = items[0].get("id")
            if not appid:
                return []

            # Fetch genres and categories for the app.
            detail_response = await client.get(
                "https://store.steampowered.com/api/appdetails/",
                params={"appids": appid, "filters": "genres,categories"},
                headers=self.headers,
            )
            if detail_response.status_code != 200:
                return []

            detail_data = detail_response.json()
            app_data = detail_data.get(str(appid), {}).get("data", {})

            tokens = []
            for genre in app_data.get("genres", []):
                tokens.append(genre.get("description", ""))
            for cat in app_data.get("categories", []):
                tokens.append(cat.get("description", ""))

            return [t for t in tokens if t.strip()]

        except Exception as exc:
            self.log_failure("fetch store metadata", exc)
            return []
