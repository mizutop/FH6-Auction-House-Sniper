"""始终置顶的狙击覆盖状态层。"""
from __future__ import annotations
import ctypes
import time
import tkinter as tk

_BG       = "#15161a"
_CARD     = "#1e1f25"
_DIVIDER  = "#2e2f37"
_LIME     = "#c6f000"
_TEXT     = "#f4f4f6"
_DIM      = "#83858f"
_FAINT    = "#5c5e68"
_AMBER    = "#f0a83c"
_RED      = "#e2685f"
_STOP     = "#e0524b"
_STOP_HV  = "#c43f39"
_START_HV = "#b0d800"

_STOPPED_WORDS = ("idle", "stopped", "auto-stop", "lost", "could not", "crashed",
                   "空闲", "停止", "自动停止", "丢失", "无法", "崩溃")

_SETTINGS_FIELDS = (
    # (group, key, label, kind, options)
    ("反馈",             "collect_after_buyout",   "自动收取赢得的车辆",     "bool", None),
    ("反馈",             "moving_background",      "移动背景模式（FH6 视频）", "bool", None),
    ("反馈",             "notify_sound",           "成功时播放提示音",       "bool", None),
    ("反馈",             "notify_toast",           "成功时显示 Windows 通知", "bool", None),
    ("反馈",             "hdr_mode",               "HDR 模式（扩大青绿色检测范围）", "bool", None),
    ("反馈",             "overlay_capturable",     "在截图和录制中显示覆盖层", "bool", None),
    ("反馈",             "win32_api_input",        "Win32 API 输入（后台按键）", "bool", None),
    ("狙击行为",         "match_threshold",        "匹配阈值",              "slider", (0.50, 1.00, 0.01)),
    ("狙击行为",         "loop_pace_s",            "循环间隔（秒）",         "float",  None),
    ("狙击行为",         "buyout_select_delay_ms", "直购选择延迟（毫秒）",   "int",  None),
    ("自动停止",         "max_cars",               "最大车辆数",             "int",    None),
    ("自动停止",         "max_minutes",            "最大分钟数",             "float",  None),
    ("热键",             "hotkey_start_stop",      "启动/停止热键",          "str",    None),
    ("热键",             "hotkey_panic",           "紧急停止热键",           "str",    None),
)


class Overlay:
    """Tk 状态 HUD。run() 阻塞于 tk 主循环。"""

    def __init__(self, hide_from_capture: bool = True):
        self.root = tk.Tk()
        self.root.title("FH6 狙击工具")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.configure(bg=_BG)

        self._status_var = tk.StringVar(value="空闲")
        self._bought_var = tk.StringVar(value="0")
        self._searches_var = tk.StringVar(value="0")
        self._fails_var = tk.StringVar(value="0")
        self._time_var = tk.StringVar(value="00:00")
        self._active = False
        self._started = None
        self._drag = (0, 0)
        self._btn_base = _LIME
        self._btn_hover = _START_HV
        self._save_callback = None
        self._tab_widgets: dict[str, tuple] = {}
        self._tab_frames: dict[str, tk.Frame] = {}
        self._active_tab = "状态"
        self._field_vars: dict[str, tk.Variable] = {}
        self._field_widgets: dict[str, tk.Widget] = {}
        self._threshold_label = None
        self._save_msg_var = tk.StringVar(value="")
        self._save_msg_label = None
        self._save_msg_after = None
        self._section_state: dict = {}
        self._settings_canvas = None
        self._settings_interior = None
        self._settings_scrollbar = None

        self._build()
        self._show_tab("状态")
        self.root.update_idletasks()
        self.root.geometry(f"344x{self.root.winfo_reqheight()}+24+24")
        self.set_capturable(not hide_from_capture)
        self._tick()

    def set_capturable(self, capturable: bool) -> None:
        """切换覆盖层是否在屏幕捕获中可见。
        False 时应用 WDA_EXCLUDEFROMCAPTURE；True 时恢复 WDA_NONE。"""
        try:
            user32 = ctypes.windll.user32
            hwnd = self.root.winfo_id()
            parent = user32.GetParent(hwnd)
            while parent:
                hwnd = parent
                parent = user32.GetParent(hwnd)
            affinity = 0x00 if capturable else 0x11
            user32.SetWindowDisplayAffinity(hwnd, affinity)
        except Exception:  # noqa: BLE001  SetWindowDisplayAffinity 可能失败
            pass

    def _build(self):
        root = self.root
        tk.Frame(root, bg=_LIME, height=3).pack(fill="x")

        header = tk.Frame(root, bg=_BG)
        header.pack(fill="x", padx=18, pady=(15, 0))
        self._dot = tk.Label(header, text="●", bg=_BG, fg=_DIM,
                             font=("Segoe UI", 10))
        self._dot.pack(side="left")
        brand = tk.Label(header, text="  FH6", bg=_BG, fg=_LIME,
                         font=("Segoe UI", 11, "bold"))
        brand.pack(side="left")
        name = tk.Label(header, text=" 狙击", bg=_BG, fg=_TEXT,
                        font=("Segoe UI", 11, "bold"))
        name.pack(side="left")
        close = tk.Label(header, text="✕", bg=_BG, fg=_DIM,
                         font=("Segoe UI", 11), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda _e: self.root.destroy())
        close.bind("<Enter>", lambda _e: close.config(fg=_TEXT))
        close.bind("<Leave>", lambda _e: close.config(fg=_DIM))
        for w in (header, self._dot, brand, name):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        tk.Frame(root, bg=_DIVIDER, height=1).pack(
            fill="x", padx=18, pady=(14, 0))

        self._build_tab_bar(root)

        self._body = tk.Frame(root, bg=_BG)
        self._body.pack(fill="both", expand=True)
        self._build_status_tab(self._body)
        self._build_settings_tab(self._body)

        tk.Label(root, text="F8  启动 / 停止    F9  紧急停止",
                 bg=_BG, fg=_DIM, font=("Segoe UI", 8)).pack(pady=(12, 15))

    def _build_tab_bar(self, root):
        bar = tk.Frame(root, bg=_BG)
        bar.pack(fill="x", padx=18, pady=(8, 0))
        for tab in ("状态", "设置"):
            cell = tk.Frame(bar, bg=_BG)
            cell.pack(side="left", expand=True, fill="x")
            lbl = tk.Label(cell, text=tab, bg=_BG, fg=_DIM,
                           font=("Segoe UI", 9, "bold"),
                           pady=8, cursor="hand2")
            lbl.pack(fill="x")
            underline = tk.Frame(cell, bg=_DIVIDER, height=2)
            underline.pack(fill="x")
            for w in (cell, lbl, underline):
                w.bind("<Button-1>", lambda _e, t=tab: self._show_tab(t))
            self._tab_widgets[tab] = (lbl, underline)

    def _build_status_tab(self, parent):
        frame = tk.Frame(parent, bg=_BG)
        self._status = tk.Label(
            frame, textvariable=self._status_var, bg=_BG, fg=_LIME,
            font=("Segoe UI", 13), anchor="center", justify="center",
            wraplength=300, height=2)
        self._status.pack(fill="x", padx=18, pady=(11, 0))

        self._build_stats(frame)

        self._btn = tk.Button(
            frame, text="开始", font=("Segoe UI", 10, "bold"),
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
            height=2)
        self._btn.pack(fill="x", padx=18, pady=(14, 0))
        self._btn.bind("<Enter>",
                       lambda _e: self._btn.config(bg=self._btn_hover))
        self._btn.bind("<Leave>",
                       lambda _e: self._btn.config(bg=self._btn_base))
        self._set_button(running=False)
        self._tab_frames["状态"] = frame

    def _build_stats(self, parent):
        card = tk.Frame(parent, bg=_CARD)
        card.pack(fill="x", padx=18, pady=(13, 0))
        cells = (("已购", self._bought_var, _LIME),
                 ("搜索", self._searches_var, _TEXT),
                 ("失败", self._fails_var, _RED),
                 ("运行", self._time_var, _TEXT))
        for i, (caption, var, color) in enumerate(cells):
            if i:
                tk.Frame(card, bg=_DIVIDER, width=1).pack(
                    side="left", fill="y", pady=12)
            cell = tk.Frame(card, bg=_CARD)
            cell.pack(side="left", expand=True, fill="both")
            tk.Label(cell, textvariable=var, bg=_CARD, fg=color,
                     font=("Segoe UI", 15, "bold")).pack(pady=(12, 0))
            tk.Label(cell, text=caption, bg=_CARD, fg=_FAINT,
                     font=("Segoe UI", 8)).pack(pady=(2, 12))

    def _build_settings_tab(self, parent):
        frame = tk.Frame(parent, bg=_BG)
        scroll_wrap = tk.Frame(frame, bg=_BG)
        scroll_wrap.pack(fill="both", expand=True)

        self._settings_canvas = tk.Canvas(
            scroll_wrap, bg=_BG, highlightthickness=0, bd=0)
        self._settings_canvas.pack(side="left", fill="both", expand=True)
        self._settings_scrollbar = tk.Scrollbar(
            scroll_wrap, orient="vertical",
            command=self._settings_canvas.yview)
        self._settings_canvas.configure(
            yscrollcommand=self._settings_scrollbar.set)

        self._settings_interior = tk.Frame(self._settings_canvas, bg=_BG)
        win_id = self._settings_canvas.create_window(
            (0, 0), window=self._settings_interior, anchor="nw")

        def _on_interior(_e):
            self._settings_canvas.configure(
                scrollregion=self._settings_canvas.bbox("all"))

        def _on_canvas(e):
            self._settings_canvas.itemconfigure(win_id, width=e.width)

        self._settings_interior.bind("<Configure>", _on_interior)
        self._settings_canvas.bind("<Configure>", _on_canvas)

        # Bucket fields by group, preserving order
        buckets: dict[str, list] = {}
        order: list[str] = []
        for g, key, label, kind, opts in _SETTINGS_FIELDS:
            if g not in buckets:
                buckets[g] = []
                order.append(g)
            buckets[g].append((key, label, kind, opts))

        for group in order:
            if group == "反馈":
                self._build_feedback_section(
                    self._settings_interior, group, buckets[group])
            else:
                self._build_collapsible_section(
                    self._settings_interior, group, buckets[group])

        # Save section sits outside the scroll so it's always reachable
        self._save_msg_label = tk.Label(
            frame, textvariable=self._save_msg_var, bg=_BG, fg=_LIME,
            font=("Segoe UI", 8), anchor="center")
        self._save_msg_label.pack(fill="x", padx=18, pady=(8, 0))

        self._save_btn = tk.Button(
            frame, text="保存设置", font=("Segoe UI", 10, "bold"),
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
            bg=_LIME, fg=_BG, activebackground=_START_HV,
            activeforeground=_BG, height=2, command=self._on_save_clicked)
        self._save_btn.pack(fill="x", padx=18, pady=(4, 0))
        self._save_btn.bind("<Enter>",
                            lambda _e: self._save_btn.config(bg=_START_HV))
        self._save_btn.bind("<Leave>",
                            lambda _e: self._save_btn.config(bg=_LIME))
        self._tab_frames["设置"] = frame

    def _build_section_header(self, parent, title, with_chevron=False):
        """构建分区标题。返回 (header_frame, chevron_or_None)。"""
        cursor = "hand2" if with_chevron else ""
        header = tk.Frame(parent, bg=_BG, cursor=cursor)
        header.pack(fill="x", padx=18, pady=(10, 0))
        chevron = None
        if with_chevron:
            chevron = tk.Label(header, text="▶", bg=_BG, fg=_LIME,
                               font=("Segoe UI", 9), cursor="hand2")
            chevron.pack(side="right")
        tk.Label(header, text=title, bg=_BG, fg=_LIME,
                 font=("Segoe UI", 9, "bold"), anchor="w",
                 cursor=cursor).pack(side="left", fill="x", expand=True)
        tk.Frame(parent, bg=_DIVIDER, height=1).pack(
            fill="x", padx=18, pady=(3, 0))
        return header, chevron

    def _build_feedback_section(self, parent, group, fields):
        self._build_section_header(parent, group, with_chevron=False)
        grid = tk.Frame(parent, bg=_BG)
        grid.pack(fill="x", padx=18, pady=(4, 0))
        for i, (key, label, _kind, _opts) in enumerate(fields):
            cell = tk.Frame(grid, bg=_BG)
            cell.grid(row=i // 2, column=i % 2, sticky="ew",
                      padx=(0, 4) if i % 2 == 0 else (4, 0), pady=3)
            self._make_check_widget(cell, key, label)
        grid.grid_columnconfigure(0, weight=1, uniform="fb")
        grid.grid_columnconfigure(1, weight=1, uniform="fb")

    def _build_collapsible_section(self, parent, group, fields):
        section = tk.Frame(parent, bg=_BG)
        section.pack(fill="x")
        header, chevron = self._build_section_header(
            section, group, with_chevron=True)
        content = tk.Frame(section, bg=_BG)
        # Content is NOT packed initially - collapsed by default

        for key, label, kind, opts in fields:
            if kind == "slider":
                self._build_slider(content, key, label, *opts)
            elif kind == "bool":
                row = tk.Frame(content, bg=_BG)
                row.pack(fill="x", padx=18, pady=(3, 0))
                self._make_check_widget(row, key, label)
            else:
                self._build_entry(content, key, label, kind)

        state = {"open": False, "content": content, "chevron": chevron}
        self._section_state[group] = state

        def _toggle(_e=None):
            state["open"] = not state["open"]
            if state["open"]:
                content.pack(fill="x")
                chevron.config(text="▼")
            else:
                content.pack_forget()
                chevron.config(text="▶")
            self._refit_settings()

        for w in (header, chevron):
            w.bind("<Button-1>", _toggle)
        for child in header.winfo_children():
            child.bind("<Button-1>", _toggle)

    def _build_slider(self, parent, key, label, lo, hi, step):
        row = tk.Frame(parent, bg=_BG)
        row.pack(fill="x", padx=18, pady=(6, 0))
        value_lbl = tk.Label(row, text=f"{label.upper()} ({lo:.2f})",
                             bg=_BG, fg=_DIM, font=("Segoe UI", 8),
                             anchor="w")
        value_lbl.pack(fill="x")
        var = tk.DoubleVar(value=lo)
        canvas = tk.Canvas(row, bg=_BG, height=20, highlightthickness=0,
                           bd=0, cursor="hand2")
        canvas.pack(fill="x", pady=(3, 1))

        def _frac():
            v = max(lo, min(hi, float(var.get())))
            return (v - lo) / (hi - lo)

        def _draw():
            w = canvas.winfo_width()
            if w <= 1:
                return
            canvas.delete("all")
            cy = 10
            canvas.create_rectangle(0, cy - 2, w, cy + 2,
                                    fill=_DIVIDER, outline="")
            x = _frac() * w
            if x > 0:
                canvas.create_rectangle(0, cy - 2, x, cy + 2,
                                        fill=_LIME, outline="")
            r = 6
            canvas.create_oval(x - r, cy - r, x + r, cy + r,
                               fill=_LIME, outline=_BG, width=2)
            value_lbl.config(
                text=f"{label.upper()} ({float(var.get()):.2f})")

        def _from_x(e):
            w = max(1, canvas.winfo_width())
            f = max(0.0, min(1.0, e.x / w))
            v = lo + f * (hi - lo)
            v = round(v / step) * step
            var.set(max(lo, min(hi, v)))

        canvas.bind("<Configure>", lambda _e: _draw())
        canvas.bind("<Button-1>", _from_x)
        canvas.bind("<B1-Motion>", _from_x)
        var.trace_add("write", lambda *_a: _draw())

        self._field_vars[key] = var
        self._field_widgets[key] = canvas
        if key == "match_threshold":
            self._threshold_label = value_lbl

    def _build_entry(self, parent, key, label, kind):
        row = tk.Frame(parent, bg=_BG)
        row.pack(fill="x", padx=18, pady=(6, 0))
        tk.Label(row, text=label.upper(), bg=_BG, fg=_DIM,
                 font=("Segoe UI", 8), anchor="w").pack(fill="x")
        var = tk.StringVar()
        entry = tk.Entry(row, textvariable=var, bg=_CARD, fg=_TEXT,
                         insertbackground=_TEXT, relief="flat",
                         font=("Segoe UI", 10), bd=0,
                         highlightthickness=1,
                         highlightbackground=_DIVIDER,
                         highlightcolor=_LIME)
        entry.pack(fill="x", ipady=4, pady=(2, 0))
        self._field_vars[key] = var
        self._field_widgets[key] = entry
        var._kind = kind        # tag for parsing on save

    def _make_check_widget(self, parent, key, label):
        """在 parent 中构建复选框。调用者负责布局。"""
        var = tk.BooleanVar(value=False)
        box = tk.Frame(parent, width=16, height=16, bg=_BG,
                       highlightthickness=2, highlightbackground=_DIM,
                       cursor="hand2")
        box.pack_propagate(False)
        box.pack(side="right", padx=(6, 2))
        text = tk.Label(parent, text=label.upper(), bg=_BG, fg=_TEXT,
                        font=("Segoe UI", 8), anchor="w", cursor="hand2",
                        wraplength=120, justify="left")
        text.pack(side="left", fill="x", expand=True)

        def _toggle(_e=None):
            var.set(not var.get())

        def _render(*_a):
            if var.get():
                box.config(bg=_LIME, highlightbackground=_LIME)
            else:
                box.config(bg=_BG, highlightbackground=_DIM)

        for w in (parent, text, box):
            w.bind("<Button-1>", _toggle)
        var.trace_add("write", _render)
        self._field_vars[key] = var
        self._field_widgets[key] = box

    def _show_tab(self, tab: str):
        for name, (lbl, underline) in self._tab_widgets.items():
            active = (name == tab)
            lbl.config(fg=_TEXT if active else _DIM)
            underline.config(bg=_LIME if active else _DIVIDER)
        for name, frame in self._tab_frames.items():
            frame.pack_forget()
        self._tab_frames[tab].pack(fill="both", expand=True)
        self._active_tab = tab
        try:
            if tab == "设置":
                self._refit_settings()
                self.root.bind_all("<MouseWheel>", self._on_wheel_settings)
            else:
                self.root.unbind_all("<MouseWheel>")
                self.root.update_idletasks()
                x = self.root.winfo_x()
                y = self.root.winfo_y()
                self.root.geometry(
                    f"344x{self.root.winfo_reqheight()}+{x}+{y}")
        except Exception:  # noqa: BLE001  调整大小时可能出错，不影响功能
            pass

    def _on_wheel_settings(self, event):
        if self._settings_canvas is None:
            return
        try:
            self._settings_canvas.yview_scroll(
                int(-event.delta / 120), "units")
        except Exception:  # noqa: BLE001  滚动时可能出错
            pass

    def _refit_settings(self):
        """调整画布和窗口大小以适应设置内容，上限为屏幕高度。"""
        if self._settings_canvas is None or self._settings_interior is None:
            return
        try:
            self.root.update_idletasks()
            interior_h = self._settings_interior.winfo_reqheight()
            self._settings_canvas.configure(height=max(40, interior_h))
            self.root.update_idletasks()
            desired = self.root.winfo_reqheight()
            max_h = self.root.winfo_screenheight() - 80
            if desired > max_h:
                excess = desired - max_h
                self._settings_canvas.configure(
                    height=max(80, interior_h - excess))
                self.root.update_idletasks()
                desired = self.root.winfo_reqheight()
                if not self._settings_scrollbar.winfo_ismapped():
                    self._settings_scrollbar.pack(
                        side="right", fill="y", before=self._settings_canvas)
            else:
                if self._settings_scrollbar.winfo_ismapped():
                    self._settings_scrollbar.pack_forget()
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            self.root.geometry(f"344x{desired}+{x}+{y}")
        except Exception:  # noqa: BLE001  调整大小时可能出错
            pass

    def _drag_start(self, e):
        self._drag = (e.x_root - self.root.winfo_x(),
                      e.y_root - self.root.winfo_y())

    def _drag_move(self, e):
        self.root.geometry(
            f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _set_button(self, running: bool):
        if running:
            text, base, hover, fg = "停止", _STOP, _STOP_HV, "#ffffff"
        else:
            text, base, hover, fg = "开始", _LIME, _START_HV, _BG
        self._btn_base, self._btn_hover = base, hover
        self._btn.config(text=text, bg=base, fg=fg,
                         activebackground=hover, activeforeground=fg)

    @staticmethod
    def _state_of(text: str) -> str:
        """根据状态文本判断当前状态：running / paused / stopped。"""
        low = text.lower()
        if "paused" in low or "暂停" in text:
            return "paused"
        if any(w in low for w in _STOPPED_WORDS):
            return "stopped"
        return "running"

    def _apply_status(self, text: str):
        self._status_var.set(text)
        state = self._state_of(text)
        self._dot.config(
            fg={"running": _LIME, "paused": _AMBER, "stopped": _DIM}[state])
        self._status.config(
            fg={"running": _LIME, "paused": _AMBER, "stopped": _DIM}[state])
        running = state != "stopped"
        self._set_button(running)
        if running and self._started is None:    # first ever start, init timer
            self._started = time.monotonic()
            self._time_var.set("00:00")
        # Stats accumulate across stop/start cycles and only clear
        # when the overlay is closed.
        self._active = running

    def _apply_stats(self, searches: int, bought: int, fails: int):
        self._searches_var.set(str(searches))
        self._bought_var.set(str(bought))
        self._fails_var.set(str(fails))

    def _tick(self):
        if self._active and self._started is not None:
            m, s = divmod(int(time.monotonic() - self._started), 60)
            self._time_var.set(f"{m:02d}:{s:02d}")
        try:
            self.root.after(1000, self._tick)
        except RuntimeError:
            pass

    def bind_settings(self, cfg) -> None:
        """从 Config 对象填充设置控件。"""
        for _grp, key, _lbl, _kind, _opts in _SETTINGS_FIELDS:
            if not hasattr(cfg, key):
                continue
            value = getattr(cfg, key)
            var = self._field_vars[key]
            if isinstance(var, tk.BooleanVar):
                var.set(bool(value))
            elif isinstance(var, tk.DoubleVar):
                var.set(float(value))
            else:
                var.set(str(value))
        if self._threshold_label is not None:
            v = float(self._field_vars["match_threshold"].get())
            self._threshold_label.config(
                text=f"匹配阈值 ({v:.2f})")

    def on_save(self, callback) -> None:
        """将保存按钮连接到回调 callback(values_dict) -> error_msg or None。"""
        self._save_callback = callback

    def _collect_values(self):
        """将控件值解析为带类型的字典；返回 (values, error)。"""
        out: dict = {}
        for _grp, key, label, kind, _opts in _SETTINGS_FIELDS:
            var = self._field_vars[key]
            raw = var.get()
            try:
                if kind == "bool":
                    out[key] = bool(raw)
                elif kind == "slider" or kind == "float":
                    out[key] = float(raw)
                elif kind == "int":
                    out[key] = int(float(raw))     # tolerate "180.0"
                else:
                    out[key] = str(raw).strip()
            except (ValueError, TypeError):
                return None, f"无效值：{label}"
        return out, None

    def _on_save_clicked(self):
        values, err = self._collect_values()
        if err:
            self._show_save_msg(err, _RED)
            return
        if self._save_callback is None:
            self._show_save_msg("已保存", _LIME)
            return
        try:
            result = self._save_callback(values)
        except Exception as exc:                   # surface callback failure
            self._show_save_msg(f"保存失败: {exc}", _RED)
            return
        if result:
            self._show_save_msg(str(result), _RED)
        else:
            self._show_save_msg("已保存", _LIME)

    def _show_save_msg(self, text: str, color: str):
        self._save_msg_var.set(text)
        if self._save_msg_label is not None:
            self._save_msg_label.config(fg=color)
        if self._save_msg_after is not None:
            try:
                self.root.after_cancel(self._save_msg_after)
            except Exception:  # noqa: BLE001  取消定时器可能失败
                pass
        self._save_msg_after = self.root.after(
            2500, lambda: self._save_msg_var.set(""))

    def set_status(self, text: str):
        """线程安全的状态更新。"""
        try:
            self.root.after(0, self._apply_status, text)
        except RuntimeError:
            pass

    def set_stats(self, searches: int, bought: int, fails: int):
        """线程安全的统计更新。"""
        try:
            self.root.after(0, self._apply_stats, searches, bought, fails)
        except RuntimeError:
            pass

    def on_toggle(self, callback):
        """将开始/停止按钮连接到回调。"""
        self._btn.config(command=callback)

    def run(self):
        self.root.mainloop()

    def close(self):
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001  窗口可能已销毁
            pass
