# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import asyncio
import platform
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, DISABLED, END, LEFT, NORMAL, RIGHT, X, Y

from appcategorizer import Categorizer
from appcategorizer.engine.llm_classifier import KNOWN_PROVIDERS

# Pre-defined model lists per provider. The combobox is editable so the user
# can also type any model name that isn't listed here.
PROVIDER_MODELS: dict[str, list[str]] = {
    "openai":    ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini", "o3-mini"],
    "anthropic": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    "mistral":   ["mistral-large-latest", "mistral-small-latest", "open-mistral-nemo"],
    "gemini":    ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"],
    "ollama":    ["llama3.2", "llama3.1", "mistral", "phi3", "gemma2", "qwen2.5"],
    "custom":    [],
}

# Providers that require a base URL (shown as an extra field in Preferences).
_URL_PROVIDERS = {"ollama", "custom"}

# Light/dark theme pair. The app starts from the operating system preference
# and still lets the user override it for the current session.
_LIGHT_THEME = "litera"
_DARK_THEME  = "darkly"

_WINDOW_SIZE    = "640x700"
_WINDOW_MINSIZE = (580, 580)

# Shown in the footer (and mirrored in the CLI --help epilog).
_LICENSE_TEXT = "AppCategorizer is licensed under the GNU LGPL 3 license only (LGPL-3.0-only)."
_PROJECT_URL  = "https://github.com/behaveproject/AppCategorizer"

_TITLE_FONT  = ("TkDefaultFont", 21, "bold")
_RESULT_FONT = ("TkDefaultFont", 15, "bold")
_DIALOG_FONT = ("TkDefaultFont", 13, "bold")

# Small, quiet type for the footer license/link line.
_FOOTER_FONT      = ("TkDefaultFont", 9)
_FOOTER_LINK_FONT = ("TkDefaultFont", 9, "underline")

# Rotating accent colours used to turn a category name into a small coloured
# "chip" — the same trick GNOME Software, macOS Mail and Windows 11 use to
# make tags/labels easy to tell apart at a glance without needing icons.
_CHIP_PALETTE = ("primary", "success", "info", "warning", "danger", "secondary")
_HISTORY_LIMIT = 6


def _chip_style(label: str) -> str:
    return _CHIP_PALETTE[hash(label) % len(_CHIP_PALETTE)]


# How strongly muted captions lean toward the theme's foreground colour (vs.
# its background) — the same idea as GNOME's ".dim-label" (~55% opacity) and
# macOS's "secondary label colour": blended *relative* to the surface, so it
# stays legible in both themes instead of using one fixed grey that reads fine
# on a light background but nearly disappears on a dark one (darkly's
# "secondary" is #444 text on a #222 background — well below readable contrast).
_MUTED_RATIO = 0.6
_MUTED_STYLE = "Muted.TLabel"
_CARD_MUTED_STYLE = "CardMuted.TLabel"

# How far the progress track's tint sits from the background, toward the
# foreground — a gentle "raised surface" shift rather than a fixed grey.
# ttkbootstrap's `colors.light` is pinned to the same pale grey in both the
# light and dark theme, so reusing it for the track painted a bright, alien
# strip across the dark surface; blending relative to the live bg/fg keeps it
# a calm, barely-there variation in both themes.
_TRACK_RATIO = 0.12

# Same reasoning for the "card" surfaces (search bar, recent lookups): a
# fixed bootstyle="light" is the *same* pale grey in litera and darkly, so in
# dark mode it reads as a bright, mismatched patch wherever it peeks through.
# A small blend toward the foreground gives a subtle, theme-correct elevation
# — barely-there in light mode, gently raised in dark mode — like GNOME/Adwaita
# and Fluent's card surfaces.
_CARD_RATIO = 0.05
_CARD_STYLE = "Card.TFrame"
_CARD_LABEL_STYLE = "Card.TLabel"


def _blend(widget: tk.Widget, color_a: str, color_b: str, ratio: float) -> str:
    """Mix two colours; ratio=1 keeps color_a, ratio=0 yields color_b."""
    a = [channel // 256 for channel in widget.winfo_rgb(color_a)]
    b = [channel // 256 for channel in widget.winfo_rgb(color_b)]
    mixed = (round(a[i] * ratio + b[i] * (1 - ratio)) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def _system_prefers_dark() -> bool:
    """Return the OS light/dark preference when it is cheap and local to read."""
    if platform.system() != "Windows":
        return False

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


class FlatIndeterminateBar(ttk.Frame):
    """A calm, flat sliding indicator drawn on a Canvas.

    ttk's built-in Progressbar renders its moving block visibly shorter than
    its trough under this theme — a quirk baked into the theme's element
    geometry, not something a style option can fix — which looks like a pill
    floating inside an oversized capsule. Drawing both ourselves keeps the
    track and the block pixel-identical in height, closer to the slim, even
    indicators GNOME/Adwaita and Fluent use.
    """

    _HEIGHT = 4
    _BLOCK_FRACTION = 0.22
    _STEP = 0.012

    def __init__(self, parent: ttk.Frame, track_color: str, accent_color: str):
        super().__init__(parent, height=self._HEIGHT)
        self.pack_propagate(False)
        self._canvas = tk.Canvas(self, height=self._HEIGHT, highlightthickness=0, bd=0)
        self._canvas.pack(fill=BOTH, expand=True)
        self._track = self._canvas.create_rectangle(0, 0, 0, 0, width=0, fill=track_color)
        self._block = self._canvas.create_rectangle(0, 0, 0, 0, width=0, fill=accent_color)
        self._position = 0.0
        self._running = False
        self._after_id: str | None = None
        self._canvas.bind("<Configure>", lambda _e: self._draw())

    def set_colors(self, track_color: str, accent_color: str) -> None:
        self._canvas.itemconfigure(self._track, fill=track_color)
        self._canvas.itemconfigure(self._block, fill=accent_color)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tick()

    def stop(self) -> None:
        self._running = False
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
        self._position = 0.0
        self._draw()

    def _tick(self) -> None:
        if not self._running:
            return
        self._position = (self._position + self._STEP) % 1.0
        self._draw()
        self._after_id = self.after(16, self._tick)

    def _draw(self) -> None:
        width = self._canvas.winfo_width()
        height = self._canvas.winfo_height()
        if width <= 1:
            return
        self._canvas.coords(self._track, 0, 0, width, height)
        block_width = max(36, int(width * self._BLOCK_FRACTION))
        travel = width + block_width
        x = self._position * travel - block_width
        self._canvas.coords(self._block, x, 0, x + block_width, height)


class AppCategorizerGui:
    def __init__(self, root: ttk.Window):
        self.root = root
        self.root.title("App Categorizer")
        self.root.geometry(_WINDOW_SIZE)
        self.root.minsize(*_WINDOW_MINSIZE)

        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker: threading.Thread | None = None
        # Built once on the first lookup and reused, so the embedding model is
        # loaded into memory a single time instead of on every search.
        self._categorizer: Categorizer | None = None

        # Shared state
        self.app_name = tk.StringVar()
        self.status   = tk.StringVar(value="Ready when you are.")
        self.mode_var = tk.StringVar(value="local_ml")
        self.dark_var = tk.BooleanVar(value=self.root.style.theme_use() == _DARK_THEME)
        self._mode_caption = tk.StringVar()
        self._panel_link_text = tk.StringVar(value="Show settings panel")

        # LLM state — preserved across mode switches and panel open/close.
        self._llm_provider_var = tk.StringVar(value=KNOWN_PROVIDERS[0])
        self._llm_model_var    = tk.StringVar(value=PROVIDER_MODELS[KNOWN_PROVIDERS[0]][0])
        self._llm_api_key_var  = tk.StringVar()
        self._llm_base_url_var = tk.StringVar()

        # Session-only memory of recent lookups, newest first: (name, category, mode).
        self._history: list[tuple[str, str, str]] = []
        self._result_widget: tk.Widget | None = None
        self._preferences_visible = False
        self._details_visible = False
        self._pending: tuple[str, str] | None = None  # (name, mode) for the in-flight request

        for var in (self.mode_var, self._llm_provider_var, self._llm_model_var):
            var.trace_add("write", self._update_mode_caption)
        self._llm_provider_var.trace_add("write", self._on_provider_change)

        self._refresh_muted_style()
        self._refresh_card_style()
        self._build_ui()
        self._set_result_idle()
        self._render_history()
        self._update_mode_caption()

        self.root.after(100, self._drain_events)

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        self._scroll_canvas = tk.Canvas(self.root, highlightthickness=0, bd=0)
        self._scroll_canvas.configure(background=self.root.style.colors.bg)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=RIGHT, fill=Y)
        self._scroll_canvas.pack(side=LEFT, fill=BOTH, expand=True)

        outer = ttk.Frame(self._scroll_canvas, padding=24)
        self._scroll_window = self._scroll_canvas.create_window((0, 0), window=outer, anchor="nw")

        outer.bind("<Configure>", self._sync_scroll_region)
        self._scroll_canvas.bind("<Configure>", self._sync_scroll_width)
        self._scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self._build_header(outer)
        self._build_search(outer)
        self._build_preferences_panel(outer)
        self._build_result(outer)
        self._build_history_section(outer)
        self._build_details(outer)
        self._build_footer(outer)

    def _sync_scroll_region(self, _event: tk.Event | None = None) -> None:
        self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))

    def _sync_scroll_width(self, event: tk.Event) -> None:
        self._scroll_canvas.itemconfigure(self._scroll_window, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self._scroll_canvas.bbox("all") is None:
            return
        first, last = self._scroll_canvas.yview()
        if first <= 0 and last >= 1:
            return
        self._scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_header(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent)
        header.pack(fill=X, pady=(0, 18))

        titles = ttk.Frame(header)
        titles.pack(side=LEFT, fill=X, expand=True)
        ttk.Label(titles, text="App Categorizer", font=_TITLE_FONT).pack(anchor="w")
        ttk.Label(
            titles,
            text="Search for an application to see which category it belongs to.",
            style=_MUTED_STYLE,
        ).pack(anchor="w", pady=(4, 0))

        controls = ttk.Frame(header)
        controls.pack(side=RIGHT, anchor="n")
        ttk.Checkbutton(
            controls,
            text="Dark mode",
            variable=self.dark_var,
            command=self._toggle_theme,
            bootstyle="round-toggle",
        ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(
            controls,
            text="Preferences",
            command=self._open_preferences,
            bootstyle="secondary-outline",
        ).pack(side=LEFT)

    def _build_search(self, parent: ttk.Frame) -> None:
        self._search_card = ttk.Frame(parent, style=_CARD_STYLE)
        self._search_card.pack(fill=X, pady=(0, 16))

        search_row = ttk.Frame(self._search_card, padding=16, style=_CARD_STYLE)
        search_row.pack(fill=X)

        self.entry = ttk.Entry(search_row, textvariable=self.app_name, font=("TkDefaultFont", 13))
        self.entry.pack(side=LEFT, fill=X, expand=True, ipady=6)
        self.entry.bind("<Return>", lambda _: self.classify())

        self.button = ttk.Button(
            search_row,
            text="Classify",
            command=self.classify,
            bootstyle="primary",
            width=12,
        )
        self.button.pack(side=LEFT, padx=(10, 0))

        mode_row = ttk.Frame(self._search_card, padding=(16, 0, 16, 8), style=_CARD_STYLE)
        mode_row.pack(fill=X)

        caption = ttk.Label(
            mode_row,
            textvariable=self._mode_caption,
            style=_CARD_MUTED_STYLE,
            cursor="hand2",
        )
        caption.pack(side=LEFT)
        caption.bind("<Button-1>", lambda _e: self._open_preferences())

        ttk.Button(
            mode_row,
            textvariable=self._panel_link_text,
            command=self._open_preferences,
            bootstyle="link",
            padding=0,
        ).pack(side=LEFT, padx=(8, 0))

        ttk.Separator(self._search_card).pack(fill=X, padx=16, pady=(0, 8))

        status_row = ttk.Frame(self._search_card, padding=(16, 0, 16, 14), style=_CARD_STYLE)
        status_row.pack(fill=X)
        ttk.Label(status_row, textvariable=self.status, style=_CARD_MUTED_STYLE).pack(anchor="w")

        # A slim "something is happening" line, like GNOME/Adwaita and Fluent
        # use — only takes up space while a request is actually running (see
        # _set_busy), so at rest the card stays calm rather than carrying a
        # permanently empty bar.
        track, accent = self._progress_colors()
        self.progress = FlatIndeterminateBar(self._search_card, track_color=track, accent_color=accent)

        self.entry.focus_set()

    def _build_result(self, parent: ttk.Frame) -> None:
        # Plain frame, not a titled group-box: the chip reads as the natural
        # continuation of the search above it rather than a separate boxed
        # section competing for attention — closer to how GNOME/macOS surface
        # a single primary outcome (prominent, untitled, generously spaced).
        self._result_card = ttk.Frame(parent)
        self._result_card.pack(fill=X, pady=(4, 24))

    def _build_history_section(self, parent: ttk.Frame) -> None:
        # Heading lives outside the card (Settings-app style) and the card
        # itself is the same flat "light" surface as the search bar above —
        # one consistent card language instead of mixing it with bordered
        # group-boxes, which is what made the window feel busy.
        ttk.Label(parent, text="Recent lookups", style=_MUTED_STYLE).pack(anchor="w", pady=(0, 6))

        card = ttk.Frame(parent, style=_CARD_STYLE)
        card.pack(fill=BOTH, expand=True, pady=(0, 16))

        section = ttk.Frame(card, padding=16, style=_CARD_STYLE)
        section.pack(fill=BOTH, expand=True)

        ttk.Label(
            section,
            text="Click a lookup to bring its result back without searching again.",
            style=_CARD_MUTED_STYLE,
        ).pack(anchor="w", pady=(0, 10))

        self._history_list = ttk.Frame(section, style=_CARD_STYLE)
        self._history_list.pack(fill=BOTH, expand=True)

    def _build_details(self, parent: ttk.Frame) -> None:
        self._details_btn = ttk.Button(
            parent,
            text="▸  Show technical details",
            command=self._toggle_details,
            bootstyle="link",
            padding=0,
        )
        self._details_btn.pack(anchor="w")

        self._details_frame = ttk.Frame(parent)
        # Not packed yet — _toggle_details reveals it on demand.

        self.log = tk.Text(
            self._details_frame,
            height=6,
            wrap="word",
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=10,
        )
        self.log.pack(fill=BOTH, expand=True, pady=(8, 0))
        self.log.configure(state=DISABLED)

    def _build_footer(self, parent: ttk.Frame) -> None:
        # Kept as an attribute so _toggle_details can reveal the details panel
        # *above* the footer (with before=self._footer) instead of below it.
        self._footer = ttk.Frame(parent)
        self._footer.pack(fill=X, pady=(18, 0))

        ttk.Separator(self._footer).pack(fill=X, pady=(0, 8))
        ttk.Label(
            self._footer,
            text=_LICENSE_TEXT,
            style=_MUTED_STYLE,
            font=_FOOTER_FONT,
            wraplength=560,
            anchor="center",
            justify="center",
        ).pack(fill=X)
        link = ttk.Label(
            self._footer,
            text=_PROJECT_URL,
            style=_MUTED_STYLE,
            font=_FOOTER_LINK_FONT,
            cursor="hand2",
            anchor="center",
            justify="center",
        )
        link.pack(fill=X, pady=(1, 0))
        link.bind("<Button-1>", lambda _e: webbrowser.open(_PROJECT_URL))

    # ------------------------------------------------------------------ #
    # Preferences panel — analysis mode + cloud provider, all in one place #
    # ------------------------------------------------------------------ #

    def _build_preferences_panel(self, parent: ttk.Frame) -> None:
        self._prefs_panel = ttk.Frame(parent, style=_CARD_STYLE)
        # Packed on demand by _open_preferences.

        body = ttk.Frame(self._prefs_panel, padding=18, style=_CARD_STYLE)
        body.pack(fill=BOTH, expand=True)

        heading_row = ttk.Frame(body, style=_CARD_STYLE)
        heading_row.pack(fill=X)
        ttk.Label(heading_row, text="Preferences", font=_DIALOG_FONT, style=_CARD_LABEL_STYLE).pack(side=LEFT)
        ttk.Button(
            heading_row,
            text="Hide panel",
            command=self._open_preferences,
            bootstyle="link",
            padding=0,
        ).pack(side=RIGHT)

        ttk.Label(body, text="Analysis mode", font=_DIALOG_FONT, style=_CARD_LABEL_STYLE).pack(anchor="w", pady=(16, 0))
        ttk.Label(
            body,
            text="On-device ML runs fully offline. Cloud LLM sends the app name to a provider of your choice.",
            style=_CARD_MUTED_STYLE,
            wraplength=540,
        ).pack(anchor="w", pady=(4, 10))

        mode_row = ttk.Frame(body, style=_CARD_STYLE)
        mode_row.pack(anchor="w", pady=(0, 18))
        self._ml_radio = ttk.Radiobutton(
            mode_row, text="On-device ML", variable=self.mode_var, value="local_ml",
            command=self._on_mode_change, bootstyle="outline-toolbutton", width=16,
        )
        self._ml_radio.pack(side=LEFT)
        self._llm_radio = ttk.Radiobutton(
            mode_row, text="Cloud LLM", variable=self.mode_var, value="cloud_llm",
            command=self._on_mode_change, bootstyle="outline-toolbutton", width=16,
        )
        self._llm_radio.pack(side=LEFT, padx=(2, 0))

        # Hidden in "On-device ML" mode and expanded in place for Cloud LLM.
        self._provider_separator = ttk.Separator(body)
        self._provider_section = ttk.Frame(body, style=_CARD_STYLE)
        ttk.Label(
            self._provider_section,
            text="Cloud provider",
            font=_DIALOG_FONT,
            style=_CARD_LABEL_STYLE,
        ).pack(anchor="w")
        ttk.Label(
            self._provider_section,
            text="Pick a provider and model, then add credentials if the provider needs them.",
            style=_CARD_MUTED_STYLE,
            wraplength=540,
        ).pack(anchor="w", pady=(4, 14))

        self._provider_combo = self._add_panel_field(
            self._provider_section, "Provider", ttk.Combobox,
            textvariable=self._llm_provider_var, values=KNOWN_PROVIDERS, state="readonly",
        )
        self._model_combo = self._add_panel_field(
            self._provider_section, "Model", ttk.Combobox,
            textvariable=self._llm_model_var, values=PROVIDER_MODELS[KNOWN_PROVIDERS[0]],
        )
        self._add_panel_field(
            self._provider_section, "API key", ttk.Entry,
            textvariable=self._llm_api_key_var, show="•",
        )

        # Base URL — only relevant for self-hosted / custom providers.
        self._base_url_row = ttk.Frame(self._provider_section, style=_CARD_STYLE)
        ttk.Label(self._base_url_row, text="Base URL", width=10, anchor="w", style=_CARD_LABEL_STYLE).pack(side=LEFT)
        ttk.Entry(self._base_url_row, textvariable=self._llm_base_url_var).pack(side=LEFT, fill=X, expand=True)
        # Packed on demand by _refresh_base_url_row.

        self._refresh_provider_section()

    @staticmethod
    def _add_panel_field(parent: ttk.Frame, label: str, widget_cls: type, **kwargs) -> tk.Widget:
        row = ttk.Frame(parent, style=_CARD_STYLE)
        row.pack(fill=X, pady=(0, 10))
        ttk.Label(row, text=label, width=10, anchor="w", style=_CARD_LABEL_STYLE).pack(side=LEFT)
        field = widget_cls(row, **kwargs)
        field.pack(side=LEFT, fill=X, expand=True)
        return field

    def _open_preferences(self) -> None:
        self._preferences_visible = not self._preferences_visible
        self._set_preferences_visible(self._preferences_visible)

    def _set_preferences_visible(self, visible: bool) -> None:
        self._preferences_visible = visible
        if visible:
            self._prefs_panel.pack(fill=X, pady=(0, 18), after=self._search_card)
            self._panel_link_text.set("Hide settings panel")
            self._ml_radio.focus_set()
            self.root.after_idle(lambda: self._scroll_canvas.yview_moveto(0))
        else:
            self._prefs_panel.pack_forget()
            self._panel_link_text.set("Show settings panel")
            self.entry.focus_set()

    # ------------------------------------------------------------------ #
    # Appearance                                                           #
    # ------------------------------------------------------------------ #

    def _toggle_theme(self) -> None:
        self.root.style.theme_use(_DARK_THEME if self.dark_var.get() else _LIGHT_THEME)
        self._scroll_canvas.configure(background=self.root.style.colors.bg)
        track, accent = self._progress_colors()
        self.progress.set_colors(track_color=track, accent_color=accent)
        self._refresh_muted_style()
        self._refresh_card_style()

    def _refresh_card_style(self) -> None:
        colors = self.root.style.colors
        surface = _blend(self.root, colors.fg, colors.bg, _CARD_RATIO)
        self.root.style.configure(_CARD_STYLE, background=surface)
        self.root.style.configure(_CARD_LABEL_STYLE, background=surface, foreground=colors.fg)
        muted = _blend(self.root, colors.fg, colors.bg, _MUTED_RATIO)
        self.root.style.configure(_CARD_MUTED_STYLE, background=surface, foreground=muted)

    def _progress_colors(self) -> tuple[str, str]:
        colors = self.root.style.colors
        track = _blend(self.root, colors.fg, colors.bg, _TRACK_RATIO)
        return track, colors.primary

    def _refresh_muted_style(self) -> None:
        # Recomputed against the *current* theme's own foreground/background —
        # the muted grey shifts with the theme instead of staying fixed, which
        # is what keeps captions readable after switching to dark mode.
        colors = self.root.style.colors
        muted = _blend(self.root, colors.fg, colors.bg, _MUTED_RATIO)
        self.root.style.configure(_MUTED_STYLE, foreground=muted)

    # ------------------------------------------------------------------ #
    # Mode / provider state                                               #
    # ------------------------------------------------------------------ #

    def _on_mode_change(self) -> None:
        self._refresh_provider_section()
        self.root.after_idle(self._sync_scroll_region)

    def _refresh_provider_section(self) -> None:
        if self.mode_var.get() == "cloud_llm":
            self._provider_separator.pack(fill=X, pady=(0, 18))
            self._provider_section.pack(fill=X)
        else:
            self._provider_separator.pack_forget()
            self._provider_section.pack_forget()

    def _on_provider_change(self, *_args) -> None:
        provider = self._llm_provider_var.get()
        models = PROVIDER_MODELS.get(provider, [])
        self._model_combo["values"] = models
        if models and self._llm_model_var.get() not in models:
            self._llm_model_var.set(models[0])
        elif not models:
            self._llm_model_var.set("")
        self._refresh_base_url_row()

    def _refresh_base_url_row(self) -> None:
        if self._llm_provider_var.get() in _URL_PROVIDERS:
            self._base_url_row.pack(fill=X, pady=(0, 10))
        else:
            self._base_url_row.pack_forget()

    def _update_mode_caption(self, *_args) -> None:
        if self.mode_var.get() == "local_ml":
            self._mode_caption.set("On-device ML")
            return

        provider = self._llm_provider_var.get()
        model = self._llm_model_var.get()
        if provider and model:
            label = f"{provider} · {model}"
        else:
            label = provider or "no provider selected"
        self._mode_caption.set(f"Cloud LLM — {label}")

    # ------------------------------------------------------------------ #
    # Result display — a coloured "chip" once a category comes back       #
    # ------------------------------------------------------------------ #

    def _set_result_widget(self, **label_kwargs) -> None:
        if self._result_widget is not None:
            self._result_widget.destroy()
        self._result_widget = ttk.Label(self._result_card, **label_kwargs)
        self._result_widget.pack(anchor="w")

    def _set_result_idle(self) -> None:
        self._set_result_widget(text="No result yet", font=_RESULT_FONT, style=_MUTED_STYLE)

    def _set_result_busy(self) -> None:
        self._set_result_widget(text="Classifying…", font=_RESULT_FONT, style=_MUTED_STYLE)

    def _set_result_success(self, category: str) -> None:
        self._set_result_widget(
            text=f"  {category}  ",
            font=_RESULT_FONT,
            bootstyle=f"{_chip_style(category)}-inverse",
            padding=(8, 6),
        )

    def _set_result_error(self) -> None:
        self._set_result_widget(text="Couldn't classify that one", font=_RESULT_FONT, bootstyle="danger")

    # ------------------------------------------------------------------ #
    # Recent lookups — a small clickable history feed                     #
    # ------------------------------------------------------------------ #

    def _record_history(self, name: str, category: str, mode: str) -> None:
        self._history = [entry for entry in self._history if entry[0].lower() != name.lower()]
        self._history.insert(0, (name, category, mode))
        del self._history[_HISTORY_LIMIT:]
        self._render_history()

    def _render_history(self) -> None:
        for child in self._history_list.winfo_children():
            child.destroy()

        if not self._history:
            ttk.Label(
                self._history_list,
                text="Lookups you run will show up here so you can revisit them in one click.",
                style=_CARD_MUTED_STYLE,
            ).pack(anchor="w")
            return

        for index, (name, category, mode) in enumerate(self._history):
            if index > 0:
                ttk.Separator(self._history_list).pack(fill=X, pady=4)
            self._add_history_row(name, category, mode)

    def _add_history_row(self, name: str, category: str, mode: str) -> None:
        row = ttk.Frame(self._history_list, padding=(2, 6), style=_CARD_STYLE)
        row.pack(fill=X)

        name_label = ttk.Label(row, text=name, style=_CARD_LABEL_STYLE)
        name_label.pack(side=LEFT)

        mode_label = ttk.Label(row, text="On-device" if mode == "local_ml" else "Cloud", style=_CARD_MUTED_STYLE)
        mode_label.pack(side=RIGHT, padx=(0, 10))

        chip = ttk.Label(row, text=f" {category} ", bootstyle=f"{_chip_style(category)}-inverse", padding=(6, 2))
        chip.pack(side=RIGHT)

        on_click = lambda _e=None, n=name, c=category: self._recall_history_entry(n, c)
        for widget in (row, name_label, mode_label, chip):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", on_click)

    def _recall_history_entry(self, name: str, category: str) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        self.app_name.set(name)
        self.entry.icursor(END)
        self._set_result_success(category)
        self.status.set(f"Showing your last result for “{name}”.")

    # ------------------------------------------------------------------ #
    # Technical details disclosure                                         #
    # ------------------------------------------------------------------ #

    def _toggle_details(self) -> None:
        self._details_visible = not self._details_visible
        if self._details_visible:
            self._details_btn.configure(text="▾  Hide technical details")
            # before=self._footer keeps the license/link line pinned below the
            # details panel rather than letting details pack underneath it.
            self._details_frame.pack(fill=BOTH, expand=True, pady=(8, 0), before=self._footer)
        else:
            self._details_btn.configure(text="▸  Show technical details")
            self._details_frame.pack_forget()

    # ------------------------------------------------------------------ #
    # Classification                                                       #
    # ------------------------------------------------------------------ #

    def classify(self) -> None:
        name = self.app_name.get().strip()
        if not name:
            messagebox.showinfo("Application name required", "Enter an application name first.")
            self.entry.focus_set()
            return

        mode = self.mode_var.get()
        if mode == "cloud_llm" and not self._llm_provider_var.get():
            messagebox.showwarning("Provider required", "Select an LLM provider first.")
            self._set_preferences_visible(True)
            return

        if self.worker is not None and self.worker.is_alive():
            return

        self._set_result_busy()
        self.status.set("Starting…")
        self._clear_log()
        self._set_busy(True)
        self._pending = (name, mode)

        # Snapshot LLM params before handing off to the worker thread so that
        # any subsequent UI change does not affect the running request.
        llm_params = (
            {
                "llm_provider": self._llm_provider_var.get() or None,
                "llm_model":    self._llm_model_var.get() or None,
                "llm_api_key":  self._llm_api_key_var.get() or None,
                "llm_base_url": self._llm_base_url_var.get() or None,
            }
            if mode == "cloud_llm"
            else {}
        )

        self.worker = threading.Thread(
            target=self._classify_in_worker,
            args=(name, mode, llm_params),
            daemon=True,
        )
        self.worker.start()

    def _classify_in_worker(self, name: str, mode: str, llm_params: dict) -> None:
        def on_progress(message: str) -> None:
            self.events.put(("progress", message))

        async def run() -> str:
            if self._categorizer is None:
                self._categorizer = Categorizer(on_progress=on_progress)
            return await self._categorizer.resolve_and_classify(
                name,
                analysis_mode=mode,
                **llm_params,
            )

        try:
            category = asyncio.run(run())
        except Exception as exc:
            self.events.put(("error", f"{exc.__class__.__name__}: {exc}"))
        else:
            self.events.put(("result", category))

    # ------------------------------------------------------------------ #
    # Event draining / UI updates                                          #
    # ------------------------------------------------------------------ #

    def _drain_events(self) -> None:
        while True:
            try:
                event_type, message = self.events.get_nowait()
            except queue.Empty:
                break

            if event_type == "progress":
                self.status.set(message)
                self._append_log(message)
            elif event_type == "result":
                self._set_result_success(message)
                self.status.set("Done — ready for another one.")
                if self._pending is not None:
                    name, mode = self._pending
                    self._record_history(name, message, mode)
                    self._pending = None
                self._set_busy(False)
            elif event_type == "error":
                self._set_result_error()
                self.status.set(message)
                self._append_log(message)
                self._pending = None
                self._set_busy(False)

        self.root.after(100, self._drain_events)

    def _set_busy(self, busy: bool) -> None:
        state = DISABLED if busy else NORMAL
        self.button.configure(state=state)
        self.entry.configure(state=state)
        if busy:
            self.progress.pack(fill=X, padx=16, pady=(0, 16))
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.entry.focus_set()

    def _append_log(self, message: str) -> None:
        self.log.configure(state=NORMAL)
        self.log.insert(END, f"{message}\n")
        self.log.see(END)
        self.log.configure(state=DISABLED)

    def _clear_log(self) -> None:
        self.log.configure(state=NORMAL)
        self.log.delete("1.0", END)
        self.log.configure(state=DISABLED)


def main() -> None:
    root = ttk.Window(themename=_DARK_THEME if _system_prefers_dark() else _LIGHT_THEME)
    AppCategorizerGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
