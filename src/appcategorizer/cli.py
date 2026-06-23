# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import argparse
import asyncio
import contextlib
import logging
import sys

from rich.console import Console

from .core import DEFAULT_LOCAL_MODEL_NAME, Categorizer
from .engine.llm_classifier import KNOWN_PROVIDERS
from .engine.logger import logger, setup_logger

console = Console(stderr=True)

_LICENSE_TEXT = "AppCategorizer is licensed under the GNU LGPL 3 license only (LGPL-3.0-only)."
_PROJECT_URL = "https://github.com/behaveproject/AppCategorizer"


@contextlib.contextmanager
def _dummy_status():
    class Dummy:
        def update(self, msg: str) -> None:
            pass

    yield Dummy()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Categorize an application by name.",
        epilog=f"{_LICENSE_TEXT}\n{_PROJECT_URL}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("app_name", help="Application name to categorize")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logs")

    # --- Analysis mode ---
    parser.add_argument(
        "--mode",
        default="local_ml",
        choices=["local_ml", "cloud_llm"],
        help="Classification backend. 'local_ml' uses a local embedding model (default). "
             "'cloud_llm' sends the app name to a remote LLM.",
    )
    parser.add_argument(
        "--local-model",
        default=DEFAULT_LOCAL_MODEL_NAME,
        metavar="MODEL",
        help="Sentence-transformer model used in 'local_ml' mode. "
             f"Defaults to '{DEFAULT_LOCAL_MODEL_NAME}'.",
    )

    # --- LLM options (only used when --mode cloud_llm) ---
    llm_group = parser.add_argument_group(
        "LLM options",
        "Required when --mode cloud_llm.",
    )
    llm_group.add_argument(
        "--llm-provider",
        default=None,
        choices=KNOWN_PROVIDERS,
        metavar="PROVIDER",
        help=f"LLM provider to use. Supported: {', '.join(KNOWN_PROVIDERS)}.",
    )
    llm_group.add_argument(
        "--llm-model",
        default=None,
        metavar="MODEL",
        help="Cloud LLM model identifier (e.g. gpt-4o, claude-haiku-4-5-20251001, "
             "gemini-2.0-flash); only used with --mode cloud_llm. Falls back to a "
             "sensible default for each provider. For the local model, use --local-model.",
    )
    llm_group.add_argument(
        "--api-key",
        default=None,
        metavar="KEY",
        help="API key for the LLM provider. Falls back to the provider-specific "
             "environment variable or a .env file.",
    )
    llm_group.add_argument(
        "--llm-base-url",
        default=None,
        metavar="URL",
        help="Base URL override for the LLM API endpoint. "
             "Required for 'custom'; can override the default for 'ollama'.",
    )
    return parser


async def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Configure Rich logging only for the command-line interface.
    setup_logger(args.verbose)

    if not args.verbose:
        logger.setLevel(logging.WARNING)

    status_context = (
        console.status("[bold cyan]Starting...", spinner="dots")
        if not args.verbose
        else _dummy_status()
    )

    def show_progress(status_obj, msg: str) -> None:
        if args.verbose:
            logger.info(msg)
        else:
            status_obj.update(f"[bold cyan]{msg}")

    try:
        with status_context as status:
            engine = Categorizer(on_progress=lambda msg: show_progress(status, msg))
            final_category = await engine.resolve_and_classify(
                args.app_name,
                analysis_mode=args.mode,
                local_model_name=args.local_model,
                llm_provider=args.llm_provider,
                llm_model=args.llm_model,
                llm_api_key=args.api_key,
                llm_base_url=args.llm_base_url,
            )
    except Exception as exc:
        # In verbose mode, include the full traceback through the Rich handler.
        # In normal mode, just emit the error message so the spinner disappears
        # cleanly before the error line is printed.
        if args.verbose:
            logger.exception(str(exc))
        else:
            logger.error(str(exc))
        sys.exit(1)

    print(final_category)


def main_sync(argv: list[str] | None = None) -> None:
    asyncio.run(main(argv))


if __name__ == "__main__":
    main_sync()