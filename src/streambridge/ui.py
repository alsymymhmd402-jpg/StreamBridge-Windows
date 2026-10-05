"""TikTok-inspired Tkinter desktop UI; media workers never depend on the visible page."""
from __future__ import annotations

import queue
import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np
from PIL import Image, ImageTk

from .audio import list_output_devices
from .core import InvalidStreamUrl, validate_stream_url
from .engine import DEFAULT_SETTINGS, StreamBridgeEngine

BG = "#080B12"
SIDEBAR = "#0C111B"
PANEL = "#111927"
PANEL_ALT = "#0D1522"
TEXT = "#F4F7FB"
MUTED = "#91A0B5"
CYAN = "#25F4EE"
PINK = "#FE2C55"
GREEN = "#38D996"
YELLOW = "#F6C75B"
RED = "#FF6B7F"
BORDER = "#202B3D"

NAV_ITEMS = [
    ("home", "⌂", "Home"),
    ("preview", "◉", "Live Preview"),
    ("status", "◈", "Bridge Status"),
    ("logs", "≡", "Logs & Diagnostics"),
    ("fx", "✦", "Media FX"),
    ("settings", "⚙", "Settings"),
]


class StreamBridgeApp(tk.Tk):
    def __init__(self, initial_url: str = "") -> None:
        super().__init__()
        self.title("StreamBridge 1.1.0 — Virtual Camera")
        self.geometry("1240x820")
        self.minsize(1020, 700)
        self.configure(bg=BG)
        self.worker: StreamBridgeEngine | None = None
        self.preview_var = tk.BooleanVar(value=True)
        self.url_var = tk.StringVar(value=initial_url)
        self.resolution_var = tk.StringVar(value="720p • 1280 × 720")
        self.fps_var = tk.StringVar(value="30 FPS")
        self.camera_name_var = tk.StringVar(value="Unity Video Capture")
        self.audio_device_var = tk.StringVar(value="")
        self.audio_devices: dict[str, int] = {}
        self.visual_enabled_var = tk.BooleanVar(value=False)
        self.speed_enabled_var = tk.BooleanVar(value=False)
        self.audio_enabled_var = tk.BooleanVar(value=False)
        self.brightness_var = tk.DoubleVar(value=0)
        self.contrast_var = tk.DoubleVar(value=100)
        self.hue_var = tk.DoubleVar(value=0)
        self.speed_var = tk.DoubleVar(value=1.0)
        self.pitch_var = tk.DoubleVar(value=1.0)
        self.volume_var = tk.DoubleVar(value=80)
        self._photo = None
        self._last_display_frame: np.ndarray | None = None
        self._closing = False
        self._last_error = False
        self._current_page = "home"
        self._adjustment_after: str | None = None
        self._last_metrics = {"fps": 0.0, "frames": 0, "signal": "WAITING", "resolution": "1280×720", "target_fps": 30}
        self._log_lines: list[str] = []
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        self.after(100, self._refresh_audio_devices)
        self.after(40, self._poll_worker)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()

        main = tk.Frame(self, bg=BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        header = tk.Frame(main, bg=BG, height=70)
        header.grid(row=0, column=0, sticky="ew", padx=30, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)
        tk.Label(header, text="STREAMBRIDGE  /  WINDOWS VIRTUAL CAMERA", bg=BG, fg=CYAN,
                 font=("Segoe UI", 10, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(header, text="Direct input  ·  Local processing  ·  DirectShow output", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9), anchor="w").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.status_chip = tk.Label(header, text="●  STOPPED", bg="#172233", fg=MUTED,
                                    font=("Segoe UI", 9, "bold"), padx=14, pady=9)
        self.status_chip.grid(row=0, column=1, rowspan=2, sticky="e")

        self.page_stack = tk.Frame(main, bg=BG)
        self.page_stack.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 25))
        self.page_stack.grid_rowconfigure(0, weight=1)
        self.page_stack.grid_columnconfigure(0, weight=1)
        self.pages: dict[str, tk.Frame] = {}
        for key, _icon, _label in NAV_ITEMS:
            page = tk.Frame(self.page_stack, bg=BG)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page
        self._build_home_page(self.pages["home"])
        self._build_preview_page(self.pages["preview"])
        self._build_status_page(self.pages["status"])
        self._build_logs_page(self.pages["logs"])
        self._build_fx_page(self.pages["fx"])
        self._build_settings_page(self.pages["settings"])
        self._show_page("home")

    def _build_sidebar(self) -> None:
        side = tk.Frame(self, bg=SIDEBAR, width=225, highlightthickness=1, highlightbackground=BORDER)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        side.grid_rowconfigure(8, weight=1)
        logo = tk.Frame(side, bg=SIDEBAR)
        logo.pack(fill="x", padx=20, pady=(27, 35))
        mark = tk.Canvas(logo, width=42, height=42, bg=SIDEBAR, highlightthickness=0)
        mark.pack(side="left")
        mark.create_oval(2, 2, 40, 40, outline=PINK, width=3)
        mark.create_line(14, 12, 14, 30, fill=CYAN, width=4, capstyle="round")
        mark.create_line(14, 12, 28, 12, fill=CYAN, width=4, capstyle="round")
        mark.create_line(14, 21, 26, 21, fill=CYAN, width=4, capstyle="round")
        brand = tk.Frame(logo, bg=SIDEBAR)
        brand.pack(side="left", padx=(10, 0))
        tk.Label(brand, text="STREAM", bg=SIDEBAR, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(brand, text="BRIDGE  1.1.0", bg=SIDEBAR, fg=CYAN, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(side, text="WORKSPACE", bg=SIDEBAR, fg="#59687D", font=("Segoe UI", 8, "bold"),
                 anchor="w").pack(fill="x", padx=22, pady=(0, 8))
        self.nav_buttons: dict[str, tk.Button] = {}
        for key, icon, label in NAV_ITEMS:
            btn = tk.Button(
                side, text=f"{icon}   {label}", command=lambda page=key: self._show_page(page),
                anchor="w", bg=SIDEBAR, fg=MUTED, activebackground="#182335", activeforeground=TEXT,
                relief="flat", bd=0, padx=19, pady=12, font=("Segoe UI", 10, "bold"), cursor="hand2"
            )
            btn.pack(fill="x", padx=10, pady=2)
            self.nav_buttons[key] = btn
        bottom = tk.Frame(side, bg="#101925", highlightthickness=1, highlightbackground=BORDER)
        bottom.pack(side="bottom", fill="x", padx=14, pady=16)
        tk.Label(bottom, text="LOCAL OUTPUT", bg="#101925", fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(10, 3))
        tk.Label(bottom, text="DirectShow · UnityCapture", bg="#101925", fg=CYAN,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(0, 10))

    def _show_page(self, key: str) -> None:
        self._current_page = key
        self.pages[key].tkraise()
        for page_key, button in self.nav_buttons.items():
            active = page_key == key
            button.configure(
                bg="#192435" if active else SIDEBAR,
                fg=CYAN if active else MUTED,
                highlightthickness=2 if active else 0,
                highlightbackground=PINK if active else SIDEBAR,
            )
        if key == "preview":
            self.after(40, self._redraw_latest)

    def _page_title(self, parent: tk.Frame, title: str, subtitle: str) -> None:
        tk.Label(parent, text=title, bg=BG, fg=TEXT, font=("Segoe UI", 22, "bold"), anchor="w").pack(fill="x", pady=(2, 3))
        tk.Label(parent, text=subtitle, bg=BG, fg=MUTED, font=("Segoe UI", 10), anchor="w").pack(fill="x", pady=(0, 18))

    def _card(self, parent: tk.Widget, *, padding: int = 18) -> tk.Frame:
        card = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        card._content_pad = padding  # type: ignore[attr-defined]
        return card

    def _build_home_page(self, page: tk.Frame) -> None:
        self._page_title(page, "Home / Dashboard", "Paste a direct live-stream URL and send it to your Windows virtual camera.")
        url_card = self._card(page)
        url_card.pack(fill="x", pady=(0, 16))
        tk.Label(url_card, text="DIRECT STREAM URL", bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(15, 5))
        tk.Label(url_card, text="HLS / M3U8  ·  RTSP / RTSPS  ·  HTTP / HTTPS", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(0, 10))
        input_row = tk.Frame(url_card, bg=PANEL)
        input_row.pack(fill="x", padx=18)
        input_row.grid_columnconfigure(0, weight=1)
        self.url_entry = tk.Entry(
            input_row, textvariable=self.url_var, bg="#080E19", fg=TEXT, insertbackground=CYAN,
            relief="flat", font=("Segoe UI", 11), highlightthickness=1,
            highlightbackground="#273449", highlightcolor=CYAN
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", ipady=12)
        self.url_entry.configure(insertwidth=2)
        self._install_paste_support(self.url_entry)
        paste_button = tk.Button(input_row, text="Paste", command=self._paste_into_entry, bg="#193040", fg=CYAN,
                                 activebackground="#254458", activeforeground=TEXT, relief="flat", bd=0,
                                 font=("Segoe UI", 10, "bold"), padx=18, pady=11, cursor="hand2")
        paste_button.grid(row=0, column=1, padx=(10, 0), sticky="ns")

        action = tk.Frame(url_card, bg=PANEL)
        action.pack(fill="x", padx=18, pady=(14, 16))
        self.start_button = tk.Button(action, text="START STREAM BRIDGE", command=self._toggle_stream,
                                      bg=PINK, fg="white", activebackground="#ff5274", activeforeground="white",
                                      relief="flat", bd=0, font=("Segoe UI", 10, "bold"), padx=24, pady=12,
                                      cursor="hand2")
        self.start_button.pack(side="left")
        self.home_preview_check = tk.Checkbutton(
            action, text="Enable UI Preview", variable=self.preview_var, command=self._on_preview_toggle,
            bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=CYAN,
            selectcolor="#080E19", font=("Segoe UI", 9), relief="flat", highlightthickness=0
        )
        self.home_preview_check.pack(side="right", padx=8)
        self.home_status_text = tk.Label(url_card, text="Ready · Install UnityCapture once to register the camera",
                                         bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.home_status_text.pack(fill="x", padx=18, pady=(0, 14))

        tk.Label(page, text="LIVE DIAGNOSTICS", bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", pady=(2, 9))
        cards = tk.Frame(page, bg=BG)
        cards.pack(fill="x", pady=(0, 15))
        for col in range(4):
            cards.grid_columnconfigure(col, weight=1, uniform="status")
        self.home_values = {}
        for col, (key, title, initial, color) in enumerate([
            ("stream", "SOURCE", "STOPPED", MUTED),
            ("camera", "VIRTUAL CAMERA", "NOT STARTED", MUTED),
            ("video", "VIDEO OUTPUT", "-- FPS", CYAN),
            ("audio", "AUDIO ROUTE", "OFF", MUTED),
        ]):
            card = self._card(cards, padding=13)
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 7, 0 if col == 3 else 7))
            tk.Label(card, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=13, pady=(12, 7))
            value = tk.Label(card, text=initial, bg=PANEL, fg=color, font=("Segoe UI", 10, "bold"), anchor="w")
            value.pack(fill="x", padx=13, pady=(0, 13))
            self.home_values[key] = value

        info = self._card(page)
        info.pack(fill="x")
        tk.Label(info, text="QUICK SETUP", bg=PANEL, fg=CYAN, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=18, pady=(14, 4))
        tk.Label(info, text="1. Install UnityCapture once.  2. Paste a direct stream link.  3. Start the bridge, then select Unity Video Capture in LIVE Studio/OBS.",
                 bg=PANEL, fg=TEXT, font=("Segoe UI", 9), anchor="w", wraplength=850, justify="left").pack(fill="x", padx=18, pady=(0, 15))

    def _install_paste_support(self, entry: tk.Entry) -> None:
        menu = tk.Menu(self, tearoff=0, bg=PANEL, fg=TEXT, activebackground="#203047", activeforeground=CYAN)
        menu.add_command(label="Cut", command=lambda: self._entry_action(entry, "cut"))
        menu.add_command(label="Copy", command=lambda: self._entry_action(entry, "copy"))
        menu.add_command(label="Paste", command=self._paste_into_entry)
        menu.add_separator()
        menu.add_command(label="Select all", command=lambda: (entry.select_range(0, tk.END), entry.icursor(tk.END)))

        def popup(event):
            entry.focus_set()
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return "break"

        entry.bind("<Button-3>", popup)
        entry.bind("<Button-2>", popup)
        entry.bind("<Control-v>", lambda _event: self._paste_into_entry())
        entry.bind("<Control-V>", lambda _event: self._paste_into_entry())
        entry.bind("<Shift-Insert>", lambda _event: self._paste_into_entry())

    def _entry_action(self, entry: tk.Entry, action: str) -> None:
        try:
            selected = entry.selection_get()
        except tk.TclError:
            selected = ""
        if not selected:
            return
        if action == "copy":
            self.clipboard_clear()
            self.clipboard_append(selected)
        elif action == "cut":
            self.clipboard_clear()
            self.clipboard_append(selected)
            entry.delete("sel.first", "sel.last")

    def _paste_into_entry(self, _event=None):
        try:
            pasted = self.clipboard_get()
        except tk.TclError:
            self._set_status("Clipboard is empty or does not contain text", YELLOW)
            return "break"
        try:
            self.url_entry.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.url_entry.insert(tk.INSERT, pasted.strip())
        self.url_entry.focus_set()
        self._set_status("URL pasted from clipboard", CYAN)
        return "break"

    def _build_preview_page(self, page: tk.Frame) -> None:
        self._page_title(page, "Live Preview", "The video shown here is the same processed frame sent to UnityCapture.")
        top = tk.Frame(page, bg=BG)
        top.pack(fill="x", pady=(0, 10))
        self.preview_check = tk.Checkbutton(
            top, text="Enable UI Preview", variable=self.preview_var, command=self._on_preview_toggle,
            bg=BG, fg=TEXT, activebackground=BG, activeforeground=CYAN,
            selectcolor=PANEL, font=("Segoe UI", 9), relief="flat", highlightthickness=0
        )
        self.preview_check.pack(side="left")
        self.preview_dimensions = tk.Label(top, text="1280 × 720  ·  30 FPS", bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold"))
        self.preview_dimensions.pack(side="right")
        self.preview_panel = tk.Frame(page, bg="#050912", highlightthickness=1, highlightbackground=BORDER)
        self.preview_panel.pack(fill="both", expand=True)
        self.preview_label = tk.Label(self.preview_panel, text="Preview appears here after the stream starts\n\nCamera output remains independent of this page",
                                      bg="#050912", fg=MUTED, font=("Segoe UI", 13), compound="center", anchor="center")
        self.preview_label.pack(fill="both", expand=True, padx=12, pady=12)
        self.preview_label.bind("<Configure>", lambda _event: self._redraw_latest())

    def _build_status_page(self, page: tk.Frame) -> None:
        self._page_title(page, "Bridge Status", "Local camera state, stream input and media output telemetry.")
        self.status_rows: dict[str, tk.Label] = {}
        for key, title, initial in [
            ("source", "Stream source", "Waiting for input"),
            ("camera", "DirectShow virtual camera", "Not started"),
            ("video", "Video format", "1280×720 · 30 FPS"),
            ("fps", "Frames delivered", "0 frames · -- FPS"),
            ("audio", "Virtual audio output", "Disabled"),
            ("adjust", "Media processing", "Default / neutral"),
        ]:
            row = self._card(page)
            row.pack(fill="x", pady=6)
            left = tk.Frame(row, bg=PANEL)
            left.pack(fill="x", padx=18, pady=14)
            tk.Label(left, text=title.upper(), bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), width=24, anchor="w").pack(side="left")
            value = tk.Label(left, text=initial, bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold"), anchor="w")
            value.pack(side="left", padx=(10, 0))
            self.status_rows[key] = value

    def _build_logs_page(self, page: tk.Frame) -> None:
        self._page_title(page, "Logs & Diagnostics", "Timestamped lifecycle, reconnect and audio-routing events.")
        frame = self._card(page)
        frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(frame, bg="#080E19", fg="#B9C7D8", insertbackground=CYAN,
                                relief="flat", wrap="word", font=("Consolas", 9), padx=14, pady=12,
                                state="disabled", height=18)
        scroll = ttk.Scrollbar(frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=12)
        scroll.pack(side="right", fill="y", padx=(0, 12), pady=12)
        buttons = tk.Frame(page, bg=BG)
        buttons.pack(fill="x", pady=(12, 0))
        tk.Button(buttons, text="Clear logs", command=self._clear_logs, bg="#182435", fg=TEXT,
                  relief="flat", bd=0, padx=16, pady=9, cursor="hand2").pack(side="right")

    def _clear_logs(self) -> None:
        self._log_lines.clear()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state="disabled")

    def _build_fx_page(self, page: tk.Frame) -> None:
        self._page_title(page, "Media FX / Adjustments", "Subtle adjustments are applied to the output frame or audio route.")
        canvas = tk.Canvas(page, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        inner_window = canvas.create_window((0, 0), window=inner, anchor="nw", width=850)
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(inner_window, width=max(1, event.width)))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        visual_controls = self._build_fx_group(inner, "Visual Fine-Tuning", self.visual_enabled_var, "Brightness, contrast and hue are applied to each frame before DirectShow output.")
        self._add_slider(visual_controls, "Brightness", self.brightness_var, -12, 12, 1, lambda v: f"{int(float(v)):+d}%")
        self._add_slider(visual_controls, "Contrast", self.contrast_var, 90, 110, 1, lambda v: f"{int(float(v))}%")
        self._add_slider(visual_controls, "Hue shift", self.hue_var, -10, 10, 0.5, lambda v: f"{float(v):+.1f}°")

        speed_controls = self._build_fx_group(inner, "Playback Speed", self.speed_enabled_var, "A small 0.98×–1.03× tempo change restarts the decoder; camera sending stays active.")
        self._add_slider(speed_controls, "Speed", self.speed_var, 0.98, 1.03, 0.001, lambda v: f"{float(v):.3f}×")

        audio_controls = self._build_fx_group(inner, "Audio Fine-Tuning", self.audio_enabled_var, "Routes audio to a selected virtual audio device; it does not travel inside the video-camera device.")
        self._add_slider(audio_controls, "Pitch shift", self.pitch_var, 0.98, 1.03, 0.001, lambda v: f"{float(v):.3f}×")
        self._add_slider(audio_controls, "Volume", self.volume_var, 0, 100, 1, lambda v: f"{int(float(v))}%")
        self.audio_fx_note = tk.Label(inner, text="Install VB-CABLE and select its CABLE Input playback endpoint in Settings.",
                                      bg=BG, fg=YELLOW, font=("Segoe UI", 9), anchor="w", wraplength=790, justify="left")
        self.audio_fx_note.pack(fill="x", pady=(3, 18))

    def _build_fx_group(self, parent: tk.Frame, title: str, enabled: tk.BooleanVar, description: str) -> tk.Frame:
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 6))
        head = tk.Frame(card, bg=PANEL)
        head.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(head, text=title.upper(), bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Checkbutton(head, text="Enable", variable=enabled, command=self._schedule_adjustment_apply,
                       bg=PANEL, fg=CYAN, activebackground=PANEL, activeforeground=TEXT,
                       selectcolor="#080E19", font=("Segoe UI", 9, "bold"), relief="flat",
                       highlightthickness=0).pack(side="right")
        tk.Label(card, text=description, bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w",
                 wraplength=800, justify="left").pack(fill="x", padx=16, pady=(0, 8))
        controls = tk.Frame(card, bg=PANEL)
        controls.pack(fill="x", padx=10, pady=(0, 10))
        return controls

    def _add_slider(self, parent: tk.Frame, label: str, variable: tk.DoubleVar,
                    lower: float, upper: float, resolution: float, formatter) -> None:
        panel_bg = str(parent.cget("bg"))
        row = tk.Frame(parent, bg=panel_bg)
        row.pack(fill="x", padx=8, pady=2)
        row.grid_columnconfigure(1, weight=1)
        tk.Label(row, text=label, bg=panel_bg, fg=TEXT, font=("Segoe UI", 9), width=17, anchor="w").grid(row=0, column=0, sticky="w")
        scale = tk.Scale(row, from_=lower, to=upper, resolution=resolution, orient="horizontal",
                         variable=variable, showvalue=False, command=self._on_slider_value,
                         bg=panel_bg, fg=TEXT, troughcolor="#202B3D", activebackground=CYAN,
                         highlightthickness=0, sliderlength=20, bd=0, length=450)
        scale.grid(row=0, column=1, sticky="ew", padx=12)
        value_label = tk.Label(row, text=formatter(variable.get()), bg=panel_bg, fg=CYAN,
                               font=("Consolas", 9, "bold"), width=9, anchor="e")
        value_label.grid(row=0, column=2, sticky="e")
        variable.trace_add("write", lambda *_args, var=variable, lab=value_label, fmt=formatter: lab.configure(text=fmt(var.get())))

    def _on_slider_value(self, _value=None) -> None:
        self._schedule_adjustment_apply()

    def _build_settings_page(self, page: tk.Frame) -> None:
        self._page_title(page, "Settings", "Camera format, preview and audio-device preferences.")
        format_card = self._card(page)
        format_card.pack(fill="x", pady=(0, 12))
        tk.Label(format_card, text="CAMERA OUTPUT", bg=PANEL, fg=CYAN, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=18, pady=(15, 9))
        row = tk.Frame(format_card, bg=PANEL)
        row.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(row, text="Resolution", bg=PANEL, fg=TEXT, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.resolution_combo = ttk.Combobox(row, textvariable=self.resolution_var, state="readonly", width=25,
                                             values=["720p • 1280 × 720", "1080p • 1920 × 1080"])
        self.resolution_combo.grid(row=0, column=1, sticky="w", padx=(0, 24))
        tk.Label(row, text="Frame rate", bg=PANEL, fg=TEXT, font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.fps_combo = ttk.Combobox(row, textvariable=self.fps_var, state="readonly", width=12,
                                      values=["30 FPS", "60 FPS"])
        self.fps_combo.grid(row=0, column=3, sticky="w")
        self.resolution_combo.bind("<<ComboboxSelected>>", self._on_static_setting_change)
        self.fps_combo.bind("<<ComboboxSelected>>", self._on_static_setting_change)
        tk.Label(format_card, text="Resolution / FPS apply when the bridge starts; stop and restart after changing them.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(0, 13))

        device_card = self._card(page)
        device_card.pack(fill="x", pady=(0, 12))
        tk.Label(device_card, text="VIRTUAL CAMERA DEVICE", bg=PANEL, fg=CYAN, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=18, pady=(15, 8))
        device_row = tk.Frame(device_card, bg=PANEL)
        device_row.pack(fill="x", padx=18, pady=(0, 10))
        device_row.grid_columnconfigure(0, weight=1)
        self.camera_name_entry = tk.Entry(device_row, textvariable=self.camera_name_var, bg="#080E19", fg=TEXT,
                                          insertbackground=CYAN, relief="flat", font=("Segoe UI", 10),
                                          highlightthickness=1, highlightbackground="#273449", highlightcolor=CYAN)
        self.camera_name_entry.grid(row=0, column=0, sticky="ew", ipady=9)
        tk.Label(device_card, text="Default device: Unity Video Capture (UnityCapture driver must be installed separately).",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(0, 13))

        audio_card = self._card(page)
        audio_card.pack(fill="x")
        tk.Label(audio_card, text="VIRTUAL AUDIO ROUTE", bg=PANEL, fg=CYAN, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=18, pady=(15, 7))
        tk.Label(audio_card, text="To send broadcast audio to TikTok/OBS, install VB-CABLE and choose its CABLE Input playback device below. Then choose CABLE Output as the microphone inside the streaming app.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w", wraplength=820, justify="left").pack(fill="x", padx=18, pady=(0, 10))
        audio_row = tk.Frame(audio_card, bg=PANEL)
        audio_row.pack(fill="x", padx=18, pady=(0, 8))
        audio_row.grid_columnconfigure(0, weight=1)
        self.audio_device_combo = ttk.Combobox(audio_row, textvariable=self.audio_device_var, state="readonly")
        self.audio_device_combo.grid(row=0, column=0, sticky="ew", ipady=4)
        tk.Button(audio_row, text="Refresh devices", command=self._refresh_audio_devices, bg="#193040", fg=CYAN,
                  activebackground="#254458", activeforeground=TEXT, relief="flat", bd=0,
                  font=("Segoe UI", 9, "bold"), padx=14, pady=8, cursor="hand2").grid(row=0, column=1, padx=(9, 0))
        self.audio_device_status = tk.Label(audio_card, text="Audio is optional; the virtual camera itself carries video only.",
                                            bg=PANEL, fg=YELLOW, font=("Segoe UI", 9), anchor="w")
        self.audio_device_status.pack(fill="x", padx=18, pady=(0, 14))

        self._configure_ttk()

    def _configure_ttk(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", fieldbackground="#080E19", background="#192435", foreground=TEXT,
                        arrowcolor=CYAN, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", "#080E19")], foreground=[("readonly", TEXT)])
        style.configure("Vertical.TScrollbar", background="#192435", troughcolor=BG, arrowcolor=CYAN)

    def _resolution(self) -> tuple[int, int]:
        return (1920, 1080) if self.resolution_var.get().startswith("1080p") else (1280, 720)

    def _audio_device_index(self) -> int | None:
        return self.audio_devices.get(self.audio_device_var.get())

    def _refresh_audio_devices(self) -> None:
        try:
            devices = list_output_devices()
        except Exception as exc:
            self.audio_device_status.configure(text=f"Audio device scan failed ({type(exc).__name__}). Install VB-CABLE to enable virtual audio.", fg=YELLOW)
            self.audio_device_combo.configure(values=[])
            return
        self.audio_devices = {f"{item['index']} · {item['name']}": int(item["index"]) for item in devices}
        names = list(self.audio_devices)
        self.audio_device_combo.configure(values=names)
        current = self.audio_device_var.get()
        if current not in self.audio_devices:
            cable = next((name for name in names if "cable input" in name.lower()), "")
            self.audio_device_var.set(cable or (names[0] if names else ""))
        if names:
            self.audio_device_status.configure(text=f"Found {len(names)} stereo output device(s). Choose CABLE Input for virtual-mic routing.", fg=GREEN)
        else:
            self.audio_device_status.configure(text="No stereo output endpoints found. Install VB-CABLE, then refresh this list.", fg=YELLOW)

    def _on_static_setting_change(self, _event=None) -> None:
        if self.worker and self.worker.is_alive():
            self._set_status("Resolution/FPS change saved for the next start; restart the bridge to apply", YELLOW)
        self._update_status_page()

    def _get_adjustments(self) -> dict:
        width, height = self._resolution()
        fps = 60 if self.fps_var.get().startswith("60") else 30
        return {
            "width": width,
            "height": height,
            "fps": fps,
            "camera_device": self.camera_name_var.get().strip() or DEFAULT_SETTINGS["camera_device"],
            "visual_enabled": self.visual_enabled_var.get(),
            "brightness": float(self.brightness_var.get()) * 2.0 if self.visual_enabled_var.get() else 0.0,
            "contrast": float(self.contrast_var.get()) / 100.0 if self.visual_enabled_var.get() else 1.0,
            "hue_shift": float(self.hue_var.get()) if self.visual_enabled_var.get() else 0.0,
            "speed": float(self.speed_var.get()) if self.speed_enabled_var.get() else 1.0,
            "audio_enabled": self.audio_enabled_var.get(),
            "audio_device": self._audio_device_index(),
            "audio_pitch": float(self.pitch_var.get()) if self.audio_enabled_var.get() else 1.0,
            "audio_volume": float(self.volume_var.get()) / 100.0 if self.audio_enabled_var.get() else 0.8,
        }

    def _schedule_adjustment_apply(self) -> None:
        if self._adjustment_after:
            try:
                self.after_cancel(self._adjustment_after)
            except tk.TclError:
                pass
        self._adjustment_after = self.after(300, self._apply_adjustments)

    def _apply_adjustments(self) -> None:
        self._adjustment_after = None
        settings = self._get_adjustments()
        if self.worker and self.worker.is_alive():
            live_keys = (
                "visual_enabled", "brightness", "contrast", "hue_shift", "speed",
                "audio_enabled", "audio_device", "audio_pitch", "audio_volume",
            )
            live_settings = {key: settings[key] for key in live_keys}
            self.worker.update_adjustments(**live_settings)
            self._set_status("Media adjustments applied · camera output continues", CYAN)
        self._update_status_page()

    def _build_engine_settings(self) -> dict:
        settings = dict(DEFAULT_SETTINGS)
        settings.update(self._get_adjustments())
        return settings

    def _toggle_stream(self) -> None:
        if self.worker and self.worker.is_alive():
            self._set_status("Stopping stream…", YELLOW)
            self.start_button.configure(state="disabled", text="STOPPING…", bg="#334155", fg=TEXT)
            self.worker.request_stop()
            return
        try:
            url = validate_stream_url(self.url_var.get())
        except InvalidStreamUrl as exc:
            messagebox.showerror("Invalid direct stream URL", str(exc), parent=self)
            self.url_entry.focus_set()
            return
        settings = self._build_engine_settings()
        if settings["audio_enabled"] and settings["audio_device"] is None:
            messagebox.showwarning("Audio device required", "Video will still start. For virtual audio, install VB-CABLE, refresh output devices, and select CABLE Input.", parent=self)
        self.worker = StreamBridgeEngine(url, settings=settings)
        self.worker.set_preview_enabled(self.preview_var.get())
        self._last_error = False
        self.start_button.configure(text="STOP STREAM", bg=PINK, fg="white", state="normal")
        self._set_status("Starting virtual camera…", YELLOW)
        self._last_metrics = {"fps": 0.0, "frames": 0, "signal": "CONNECTING", "resolution": f"{settings['width']}×{settings['height']}", "target_fps": settings["fps"]}
        self._append_log("APP", f"Starting bridge for {self._redact_url(url)}")
        self.worker.start()

    @staticmethod
    def _redact_url(url: str) -> str:
        # Keep diagnostics useful without writing tokenized query values to logs.
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        return f"{parsed.scheme}://{parsed.hostname or ''}{parsed.path}"

    def _on_preview_toggle(self) -> None:
        enabled = self.preview_var.get()
        if self.worker and self.worker.is_alive():
            self.worker.set_preview_enabled(enabled)
        if not enabled:
            self._photo = None
            self._last_display_frame = None
            self.preview_label.configure(image="", text="PREVIEW HIDDEN\nVirtual camera output continues in the background")
            self._set_status("UI preview hidden · output continues", CYAN)
        else:
            self.preview_label.configure(text="Waiting for the next frame…")
            self._set_status("UI preview enabled", CYAN)

    def _poll_worker(self) -> None:
        worker = self.worker
        if worker:
            while True:
                try:
                    kind, payload = worker.events.get_nowait()
                except queue.Empty:
                    break
                if kind == "status":
                    lower = str(payload).lower()
                    color = GREEN if "live stream connected" in lower or "virtual camera ready" in lower else YELLOW
                    self._set_status(str(payload), color)
                    self._append_log("VIDEO", str(payload))
                elif kind == "camera":
                    self.home_values["camera"].configure(text="READY", fg=GREEN)
                    self.status_rows["camera"].configure(text=str(payload), fg=GREEN)
                    self._append_log("CAMERA", str(payload))
                elif kind == "metrics":
                    self._last_metrics = payload
                    self.home_values["video"].configure(text=f"{payload.get('fps', 0):.1f} FPS", fg=CYAN)
                    self.home_values["stream"].configure(text=payload.get("signal", "WAITING"),
                                                          fg=GREEN if payload.get("signal") == "LIVE" else YELLOW)
                    self.preview_dimensions.configure(text=f"{payload.get('resolution', '1280×720')}  ·  {payload.get('target_fps', 30)} FPS")
                    self.status_rows["source"].configure(text=payload.get("signal", "WAITING"),
                                                          fg=GREEN if payload.get("signal") == "LIVE" else YELLOW)
                    self.status_rows["video"].configure(text=f"{payload.get('resolution', '1280×720')} · {payload.get('target_fps', 30)} FPS")
                    self.status_rows["fps"].configure(text=f"{payload.get('frames', 0)} frames · {payload.get('fps', 0):.1f} FPS")
                elif kind == "audio_status":
                    text = str(payload)
                    color = GREEN if "audio live" in text.lower() or "route ready" in text.lower() else MUTED
                    self.home_values["audio"].configure(text=text[:24], fg=color)
                    self.status_rows["audio"].configure(text=text, fg=color)
                    self.audio_device_status.configure(text=text, fg=color)
                    self._append_log("AUDIO", text)
                elif kind == "audio_error":
                    self.home_values["audio"].configure(text="ROUTE ERROR", fg=YELLOW)
                    self.status_rows["audio"].configure(text=str(payload), fg=YELLOW)
                    self.audio_device_status.configure(text=str(payload), fg=YELLOW)
                    self._append_log("AUDIO ERROR", str(payload))
                elif kind == "fatal":
                    self._last_error = True
                    self._set_status(str(payload), RED)
                    self.home_values["camera"].configure(text="UNAVAILABLE", fg=RED)
                    self.status_rows["camera"].configure(text=str(payload), fg=RED)
                    self._append_log("FATAL", str(payload))
                    messagebox.showerror("Virtual camera error", str(payload), parent=self)
                elif kind == "finished":
                    self.start_button.configure(text="START STREAM BRIDGE", bg=PINK, fg="white", state="normal")
                    if not self._closing and not self._last_error:
                        self._last_metrics["signal"] = "STOPPED"
                        self.home_values["stream"].configure(text="STOPPED", fg=MUTED)
                        self._set_status("Output stopped · Start again when ready", MUTED)
                        self.home_values["camera"].configure(text="NOT STARTED", fg=MUTED)
                        self.status_rows["camera"].configure(text="Not started", fg=MUTED)
                        self._append_log("APP", "Output stopped")
                    self.home_values["video"].configure(text=f"{self._last_metrics.get('fps', 0):.1f} FPS", fg=MUTED)
            self._update_status_page()
            if self.preview_var.get() and self._current_page == "preview":
                newest = None
                while True:
                    try:
                        newest = worker.preview_frames.get_nowait()
                    except queue.Empty:
                        break
                if newest is not None:
                    self._show_frame(newest)
        if self._closing:
            if not worker or not worker.is_alive():
                self.destroy()
                return
        self.after(40, self._poll_worker)

    def _update_status_page(self) -> None:
        settings = self._get_adjustments()
        if hasattr(self, "status_rows"):
            enabled = []
            if settings["visual_enabled"]:
                enabled.append("Visual FX")
            if settings["speed"] != 1.0:
                enabled.append(f"Speed {settings['speed']:.3f}×")
            if settings["audio_enabled"]:
                enabled.append(f"Audio pitch {settings['audio_pitch']:.3f}×")
            self.status_rows["adjust"].configure(text=", ".join(enabled) if enabled else "Default / neutral")

    def _append_log(self, category: str, text: str) -> None:
        from datetime import datetime
        line = f"{datetime.now().strftime('%H:%M:%S')}  [{category}]  {text}"
        self._log_lines.append(line)
        self._log_lines = self._log_lines[-500:]
        if hasattr(self, "log_text"):
            self.log_text.configure(state="normal")
            self.log_text.insert(tk.END, line + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state="disabled")

    def _set_status(self, text: str, color: str) -> None:
        self.status_chip.configure(text=f"●  {self._status_label(text, color)}", fg=color)
        if hasattr(self, "home_status_text"):
            self.home_status_text.configure(text=text, fg=color)

    @staticmethod
    def _status_label(text: str, color: str) -> str:
        lower = text.lower()
        if "live" in lower or "sending frames" in lower:
            return "LIVE"
        if "reconnect" in lower or "signal lost" in lower or color == YELLOW:
            return "RECONNECTING"
        if "camera ready" in lower:
            return "CAMERA READY"
        if "stopping" in lower:
            return "STOPPING"
        if color == RED:
            return "ERROR"
        if color == MUTED:
            return "STOPPED"
        return "STARTING"

    def _show_frame(self, bgr: np.ndarray) -> None:
        if not self.preview_var.get() or self._current_page != "preview":
            return
        self._last_display_frame = bgr.copy()
        rgb = np.ascontiguousarray(bgr[:, :, ::-1])
        image = Image.fromarray(rgb, "RGB")
        w = max(2, self.preview_label.winfo_width() - 20)
        h = max(2, self.preview_label.winfo_height() - 20)
        image.thumbnail((w, h), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(image)
        self.preview_label.configure(image=self._photo, text="")

    def _redraw_latest(self) -> None:
        if self._last_display_frame is not None and self._current_page == "preview" and self.preview_var.get():
            self._show_frame(self._last_display_frame)

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            self._closing = True
            self.worker.request_stop()
            self._set_status("Stopping output before exit…", YELLOW)
        else:
            self.destroy()
