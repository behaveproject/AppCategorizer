# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import httpx
from .base import BaseSource

class WikidataSource(BaseSource):
    def __init__(self):
        super().__init__()
        self.headers["User-Agent"] = "appcategorizer/1.0 (https://github.com/behaveproject/appcategorizer)"

    async def fetch(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        qid = await self._search_entity(client, app_name)
        if not qid:
            return []
        tokens = await self._fetch_entity(client, app_name, qid)
        return tokens

    async def _search_entity(self, client: httpx.AsyncClient, app_name: str) -> str | None:
        try:
            response = await client.get(
                "https://www.wikidata.org/w/api.php",
                params={
                    "action": "wbsearchentities",
                    "search": app_name,
                    "format": "json",
                    "language": "en",
                    "type": "item",
                    "limit": 5,
                },
                headers=self.headers,
            )
            if response.status_code != 200:
                return None

            results = response.json().get("search", [])
            if not results:
                return None

            # Prefer an exact label or alias match.
            for result in results:
                label = result.get("label", "")
                if self.is_relevant(app_name, label):
                    return result.get("id")

            return None

        except Exception as exc:
            self.log_failure("search entity", exc)
            return None

    async def _fetch_entity(
        self, client: httpx.AsyncClient, app_name: str, qid: str
    ) -> list[str]:
        try:
            response = await client.get(
                "https://www.wikidata.org/w/api.php",
                params={
                    "action": "wbgetentities",
                    "ids": qid,
                    "format": "json",
                    "languages": "en",
                    # Fetch the description and classification claims.
                    "props": "descriptions|claims",
                },
                headers=self.headers,
            )
            if response.status_code != 200:
                return []

            entity = response.json().get("entities", {}).get(qid, {})
            tokens = []

            # English description.
            desc = entity.get("descriptions", {}).get("en", {}).get("value", "")
            if desc:
                tokens.append(desc)

            # P31 = "instance of" (ex: "web browser", "video game")
            # P136 = "genre"
            # P452 = "industry"
            claims = entity.get("claims", {})
            for prop in ["P31", "P136", "P452"]:
                for claim in claims.get(prop, []):
                    value = (
                        claim.get("mainsnak", {})
                        .get("datavalue", {})
                        .get("value", {})
                    )
                    if isinstance(value, dict) and "id" in value:
                        # Resolve the QID into a readable label.
                        label = await self._resolve_label(client, value["id"])
                        if label:
                            tokens.append(label)

            return [t for t in tokens if t.strip()]

        except Exception as exc:
            self.log_failure("fetch entity", exc)
            return []

    async def _resolve_label(self, client: httpx.AsyncClient, qid: str) -> str:
        """Resolve a QID to an English label, for example Q11500 -> 'web browser'."""
        try:
            response = await client.get(
                "https://www.wikidata.org/w/api.php",
                params={
                    "action": "wbgetentities",
                    "ids": qid,
                    "format": "json",
                    "languages": "en",
                    "props": "labels",
                },
                headers=self.headers,
            )
            entity = response.json().get("entities", {}).get(qid, {})
            return entity.get("labels", {}).get("en", {}).get("value", "")
        except Exception as exc:
            self.log_failure("resolve label", exc)
            return ""
