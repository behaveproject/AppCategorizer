# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import logging
import warnings

def setup_logger(verbose: bool):
    from rich.logging import RichHandler

    logging.captureWarnings(True)
    
    warnings.filterwarnings("ignore", message=".*unauthenticated requests.*")
    warnings.filterwarnings("ignore", module=".*huggingface_hub.*")

    FORMAT = "%(message)s"
    
    logging.basicConfig(
        level=logging.WARNING,
        format=FORMAT,
        datefmt="[%H:%M:%S]",
        handlers=[RichHandler(show_path=False, rich_tracebacks=True, markup=True)]
    )
    
    app_logger = logging.getLogger("AppCategorizer")
    
    if verbose:
        app_logger.setLevel(logging.DEBUG)
        
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("py.warnings").setLevel(logging.ERROR)
    
    return app_logger

logger = logging.getLogger("AppCategorizer")
