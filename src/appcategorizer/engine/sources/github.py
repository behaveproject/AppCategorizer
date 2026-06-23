# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import os
import httpx
from .base import BaseSource

class GithubSource(BaseSource):
    def __init__(self):
        super().__init__()
        # Use a GitHub token when available to raise API rate limits.
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.headers["X-GitHub-Api-Version"] = "2022-11-28"
        self.headers["Accept"] = "application/vnd.github+json"

    async def fetch(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        try:
            # Search the GitHub API and limit results for performance.
            response = await client.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": f"{app_name} in:name",
                    "per_page": 5,
                },
                headers=self.headers,
            )
            
            if response.status_code != 200:
                return []

            items = response.json().get("items", [])
            if not items:
                return []

            # Select the best match by validating the repository name.
            for item in items:
                repo_name = item.get("name", "")
                full_name = item.get("full_name", "")

                if not self.is_relevant(app_name, repo_name, full_name):
                    continue

                tokens = []

                # Add the repository description.
                description = item.get("description") or ""
                if description:
                    tokens.append(description)

                # Add repository topics, for example ["browser", "privacy", "web"].
                topics = item.get("topics", [])
                tokens.extend(topics)

                # Remove empty values before classification.
                clean_tokens = [t.strip() for t in tokens if t.strip()]

                # Inspect all gathered text to infer the project type.
                full_text = " ".join(clean_tokens).lower()
                
                # Add a gaming hint when the repository looks game-related.
                if "game" in full_text or "emulator" in full_text:
                     clean_tokens.insert(0, "This is an open-source video game or gaming project hosted on GitHub.")
                else:
                     # Otherwise, default to a development-tool hint.
                     clean_tokens.insert(0, "This is an open-source software project, development tool, or application hosted on GitHub.")
                     
                return clean_tokens

            return []

        except Exception as exc:
            self.log_failure("fetch repository search", exc)
            return []
