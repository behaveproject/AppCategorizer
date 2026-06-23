# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import httpx
from .base import BaseSource

class FlathubSource(BaseSource):
    async def fetch(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        url = "https://flathub.org/api/v2/search"

        try:
            response = await client.post(
                url,
                json={"query": app_name, "filters": []},
                headers={**self.headers, "Content-Type": "application/json"}
            )
            if response.status_code != 200:
                return []

            data = response.json()
            apps = data.get("hits", data) if isinstance(data, dict) else data
            if not apps:
                return []

            app_data = apps[0]
            app_id = app_data.get("app_id", "")
            app_id_short = app_id.split(".")[-1] if app_id else ""

            if not self.is_relevant(app_name, app_data.get("name", ""), app_id, app_id_short):
                return []
            
            tokens = []
            tokens.append(app_data.get("name", ""))
            tokens.append(app_data.get("summary", ""))

            if "categories" in app_data:
                for cat in app_data["categories"]:
                    tokens.append(cat.get("name", "") if isinstance(cat, dict) else str(cat))

            return [t for t in tokens if t.strip()]

        except Exception as exc:
            self.log_failure("fetch app search", exc)
            return []
