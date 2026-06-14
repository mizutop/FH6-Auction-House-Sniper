"""入口点：连接配置、模板、狙击、覆盖层和热键。"""
from __future__ import annotations
import json
import logging
import sys
import threading
from dataclasses import asdict
from pynput import keyboard
from . import capture, notifier, paths, vision
from .config import Config, load_config, save_config
from .overlay import Overlay
from .sniper import GameIO, Sniper


def _log_config(cfg: Config) -> None:
    """将加载的配置以 JSON 单行记录到日志。
    有助于排查用户提交的日志——可以看到会话开始时机器人的配置。"""
    body = asdict(cfg)
    declared = set(cfg.__dataclass_fields__)
    for key, value in cfg.__dict__.items():           # include extras
        if key not in declared:
            body[key] = value
    body = {k: list(v) if isinstance(v, tuple) else v for k, v in body.items()}
    logging.getLogger("fh6").info("config snapshot: %s",
                                   json.dumps(body, sort_keys=True))


def _setup_logging():
    log_path = paths.app_dir() / "logs" / "sniper.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s %(message)s", "%H:%M:%S")
    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(fmt)
    root = logging.getLogger("fh6")
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(file_handler)
    if sys.stderr is not None:          # no console under --windowed exe
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)
    return log_path


def main() -> None:
    log_path = _setup_logging()
    logging.getLogger("fh6").info("FH6 狙击工具启动（日志: %s）", log_path)
    cfg = load_config(paths.app_dir() / "config.json")
    _log_config(cfg)
    templates = vision.load_templates(
        paths.app_dir() / cfg.template_dir,
        moving_background=cfg.moving_background)
    io = GameIO(cfg, templates)
    overlay = Overlay(
        hide_from_capture=not getattr(cfg, "overlay_capturable", False))

    state: dict = {
        "sniper": None,
        "thread": None,
        # display-side running totals - accumulate across stop/start cycles
        # so the overlay's stats don't reset every run.
        "display": {"searches": 0, "bought": 0, "fails": 0},
        # last raw values seen from the current Sniper - used to compute
        # deltas (new Sniper instances start their internal counters at 0).
        "last_bot_stats": (0, 0, 0),
    }
    purchase_log = paths.app_dir() / cfg.log_path

    def on_purchase(loop_seconds: float, total: int) -> None:
        notifier.log_purchase(purchase_log, "bought", loop_seconds, total)
        notifier.notify_success(total, cfg.notify_sound, cfg.notify_toast)

    def on_stats(searches: int, bought: int, fails: int) -> None:
        last_s, last_b, last_f = state["last_bot_stats"]
        d = state["display"]
        d["searches"] += max(0, searches - last_s)
        d["bought"]   += max(0, bought   - last_b)
        d["fails"]    += max(0, fails    - last_f)
        state["last_bot_stats"] = (searches, bought, fails)
        overlay.set_stats(d["searches"], d["bought"], d["fails"])

    def start() -> None:
        if state["thread"] and state["thread"].is_alive():
            return
        capture.focus_window(cfg.window_title)
        capture.reset_normalize_plan()             # detect crop afresh each run
        state["last_bot_stats"] = (0, 0, 0)        # new Sniper, fresh deltas
        sniper = Sniper(io, cfg, on_purchase=on_purchase,
                        on_status=overlay.set_status,
                        on_stats=on_stats)

        def _run_safe() -> None:
            try:
                sniper.run()
            except Exception:  # noqa: BLE001  捕获所有异常以防止线程无声退出
                logging.getLogger("fh6.main").exception(
                    "sniper 线程崩溃")
                try:
                    overlay.set_status("崩溃：请查看 sniper.log")
                except Exception:  # noqa: BLE001  覆盖层可能已销毁
                    pass

        thread = threading.Thread(target=_run_safe, daemon=True)
        state["sniper"], state["thread"] = sniper, thread
        thread.start()

    def stop() -> None:
        if state["sniper"]:
            state["sniper"].request_stop()

    def toggle() -> None:
        if state["thread"] and state["thread"].is_alive():
            stop()
        else:
            start()

    hotkeys_ref: dict = {"listener": None}

    def _bind_hotkeys(start_stop: str, panic: str) -> None:
        listener = keyboard.GlobalHotKeys({start_stop: toggle, panic: stop})
        listener.start()
        hotkeys_ref["listener"] = listener

    _bind_hotkeys(cfg.hotkey_start_stop, cfg.hotkey_panic)

    def apply_settings(values: dict) -> str | None:
        """将设置字典原地应用到 cfg；持久化；按需重新加载。返回错误消息或 None。"""
        log = logging.getLogger("fh6.settings")
        prev_bg = cfg.moving_background
        prev_start = cfg.hotkey_start_stop
        prev_panic = cfg.hotkey_panic
        prev_capturable = getattr(cfg, "overlay_capturable", False)
        diffs = []
        for key, value in values.items():
            old = getattr(cfg, key, None)
            if old != value:
                diffs.append(f"{key} {old!r} -> {value!r}")
            setattr(cfg, key, value)
        if diffs:
            log.info("settings changed: %s", ", ".join(diffs))
        if cfg.overlay_capturable != prev_capturable:
            overlay.set_capturable(cfg.overlay_capturable)
            log.info("overlay capturable -> %s", cfg.overlay_capturable)
        try:
            save_config(cfg, paths.app_dir() / "config.json")
        except (OSError, PermissionError) as exc:
            log.exception("save_config failed")
            return f"无法保存配置: {exc}"
        if cfg.moving_background != prev_bg:
            try:
                io.templates = vision.load_templates(
                    paths.app_dir() / cfg.template_dir,
                    moving_background=cfg.moving_background)
                log.info("templates reloaded (moving_background=%s)",
                         cfg.moving_background)
            except (OSError, Exception) as exc:
                log.exception("template reload failed")
                return f"已保存，但模板重新加载失败: {exc}"
        if (cfg.hotkey_start_stop != prev_start
                or cfg.hotkey_panic != prev_panic):
            try:
                if hotkeys_ref["listener"] is not None:
                    hotkeys_ref["listener"].stop()
                _bind_hotkeys(cfg.hotkey_start_stop, cfg.hotkey_panic)
                log.info("hotkeys rebound (%s / %s)",
                         cfg.hotkey_start_stop, cfg.hotkey_panic)
            except Exception as exc:  # noqa: BLE001  pynput 可能失败
                log.exception("hotkey rebind failed")
                return f"已保存，但热键重新绑定失败: {exc}"
        return None

    overlay.bind_settings(cfg)
    overlay.on_save(apply_settings)
    overlay.on_toggle(toggle)
    overlay.set_status("空闲")
    try:
        overlay.run()
    finally:
        stop()
        listener = hotkeys_ref["listener"]
        if listener is not None:
            listener.stop()


if __name__ == "__main__":
    main()
