# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import re
import httpx
from rapidfuzz import fuzz
from ..logger import logger

class BaseSource:
    NAME_SIMILARITY_THRESHOLD = 75

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def fetch(self, client: httpx.AsyncClient, app_name: str) -> list[str]:
        raise NotImplementedError

    def log_failure(self, operation: str, exc: Exception) -> None:
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
        logger.debug(
            f"[{self.__class__.__name__}] {operation} failed: "
            f"{exc.__class__.__name__}: {message}"
        )

    def is_relevant(self, queried_name: str, *candidate_names: str) -> bool:
        
        def normalize(s):
            return re.sub(r'\s+', '', s.lower().strip())

        q = queried_name.lower().strip()

        for returned_name in candidate_names:
            if not returned_name:
                continue
            r = returned_name.lower().strip()

            if q == r:
                return True
            if normalize(q) == normalize(r):
                return True

            if r.startswith(q):
                rest = r[len(q):]
                if len(q) >= 5 and rest.startswith(('-', '_')):
                    return True

            if q.startswith(r) and len(r) >= 5:
                return True
            
            if r.startswith(q) and len(q) >= 4:
                return True

            score = fuzz.token_set_ratio(q, r)
            if score >= self.NAME_SIMILARITY_THRESHOLD:
                return True

        return False
