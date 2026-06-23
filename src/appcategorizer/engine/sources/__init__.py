# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

from .apple import AppleSource
from .arch import ArchSource
from .debian import DebianSource
from .fedora import FedoraSource
from .flathub import FlathubSource
from .github import GithubSource
from .gog import GogSource
from .itch import ItchSource
from .microsoft import MicrosoftSource
from .myabandonware import MyAbandonwareSource
from .snapcraft import SnapcraftSource
from .steam import SteamSource
from .ubuntu import UbuntuSource
from .wikidata import WikidataSource

__all__ = [
    "AppleSource",
    "ArchSource",
    "DebianSource",
    "FedoraSource",
    "FlathubSource",
    "GithubSource",
    "GogSource",
    "ItchSource",
    "MicrosoftSource",
    "MyAbandonwareSource",
    "SnapcraftSource",
    "SteamSource",
    "UbuntuSource",
    "WikidataSource",
]
