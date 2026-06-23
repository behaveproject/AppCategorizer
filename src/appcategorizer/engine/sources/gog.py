# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import httpx
from .base import BaseSource

class GogSource(BaseSource):
    async def fetch(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        clean_query = app_name.replace(":", " ").replace("-", " ")
        clean_query = " ".join(clean_query.split())
        
        custom_headers = self.headers.copy()
        custom_headers["Accept-Language"] = "en-US,en;q=0.9"
        forced_cookies = {"gog_lc": "US_USD_en-US"}
        
        try:
            response = await client.get(
                "https://catalog.gog.com/v1/catalog",
                params={"limit": 5, "locale": "en-US", "query": clean_query},
                headers=custom_headers,
                cookies=forced_cookies,
                follow_redirects=True,
            )
            if response.status_code != 200:
                return []
                
            data = response.json()
            products = data.get("products", [])
            
            for product in products:
                title = product.get("title", "")
                slug = product.get("slug", "")
                
                if self.is_relevant(app_name, title, slug, slug.replace("_", " ")):
                    product_type = product.get("productType", "software") 
                    genres_data = product.get("genres", [])
                    genres = [g.get("name") for g in genres_data if g.get("name")]
                    
                    genre_str = ", ".join(genres)
                    semantic_injection = f"This is a {product_type.lower()} distributed on GOG. Categories: {genre_str}."
                    
                    return [semantic_injection]
                    
            # No matching product was found.
            return []
            
        except Exception as exc:
            self.log_failure("fetch catalog search", exc)
            return []
