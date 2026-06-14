"""带随机化时序的键盘输入。"""
from __future__ import annotations
import logging
import random
import time
import win32gui
import win32con
from pynput.keyboard import Key, Controller

log = logging.getLogger("fh6.actions")

_DEFAULT_KEYBOARD = Controller()


def get_hwnd(window_title: str = "Forza Horizon 6") -> int:
    """获取 Forza Horizon 6 游戏窗口的窗口句柄。"""
    hwnd = win32gui.FindWindow(None, window_title)
    if not hwnd:
        log.warning("未找到 Forza Horizon 6 窗口")
    return hwnd


KEY_MAP: dict[str, Key | str] = {
    "enter": Key.enter,
    "esc": Key.esc,
    "up": Key.up,
    "down": Key.down,
    "y": "y",
}

VK_CODES: dict[str, int] = {
    "enter": 0x0D,
    "esc": 0x1B,
    "up": 0x26,
    "down": 0x28,
    "y": 0x59,
}


def _rand_seconds(ms_range: tuple[float, float]) -> float:
    return random.uniform(ms_range[0], ms_range[1]) / 1000.0


def press_key(name: str, key_hold_ms: tuple, between_keys_ms: tuple,
              use_win32: bool = False, keyboard=_DEFAULT_KEYBOARD,
              sleep=time.sleep) -> None:
    if use_win32:
        press_key_vk(name, key_hold_ms, between_keys_ms, sleep)
    else:
        press_key_fg(name, key_hold_ms, between_keys_ms, keyboard, sleep)


def press_key_fg(name: str, key_hold_ms: tuple, between_keys_ms: tuple,
                 keyboard=_DEFAULT_KEYBOARD, sleep=time.sleep) -> None:
    """按下单个按键，带随机化的保持时间和按下后间隔。"""
    key = KEY_MAP[name]
    keyboard.press(key)
    sleep(_rand_seconds(key_hold_ms))
    keyboard.release(key)
    sleep(_rand_seconds(between_keys_ms))


def press_key_vk(name: str, key_hold_ms: tuple, between_keys_ms: tuple,
                 sleep=time.sleep) -> None:
    """使用 Win32 API 按下单个按键，带随机化的保持时间和按下后间隔。"""
    hwnd = get_hwnd()
    if not hwnd:
        return
    vk_code = VK_CODES[name]
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, 0)
    sleep(_rand_seconds(key_hold_ms))
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, 0)
    sleep(_rand_seconds(between_keys_ms))


def tap_key(name: str, times: int, key_hold_ms: tuple, between_keys_ms: tuple,
            use_win32: bool = False, keyboard=_DEFAULT_KEYBOARD,
            sleep=time.sleep) -> None:
    """将按键 `name` 按下 `times` 次。"""
    for _ in range(times):
        press_key(name, key_hold_ms, between_keys_ms,
                  use_win32, keyboard, sleep)
