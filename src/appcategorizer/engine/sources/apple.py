# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import httpx
from .base import BaseSource

class AppleSource(BaseSource):
    async def fetch(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        try:
            response = await client.get(
                "https://itunes.apple.com/search",
                params={"term": app_name, "entity": "software", "limit": 1},
                headers=self.headers,
            )
            if response.status_code != 200:
                return []

            data = response.json()
            if data.get("resultCount", 0) == 0:
                return []

            result = data["results"][0]
            if not self.is_relevant(app_name, result.get("trackName", "")):
                return []
            
            tokens = []

            # Add the primary category.
            if "primaryGenreName" in result:
                tokens.append(result["primaryGenreName"])
            
            # Add the full genre list.
            if "genres" in result:
                tokens.extend(result["genres"])
            
            # Add keywords from the short description when available.
            if "description" in result:
                # Keep only the first 200 characters.
                tokens.append(result["description"][:200])

            return tokens

        except Exception as exc:
            self.log_failure("fetch", exc)
            return []
