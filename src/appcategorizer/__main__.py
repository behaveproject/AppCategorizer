# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

"""Enable `python -m appcategorizer <app name> ...`.

This is the PATH-independent way to run the CLI when the generated
`appcategorizer` console script is not on the system PATH (common on Windows
with Microsoft Store Python or the `py` launcher).
"""

from .cli import main_sync

if __name__ == "__main__":
    main_sync()
