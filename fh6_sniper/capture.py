"""屏幕捕获和窗口焦点辅助函数。"""
from __future__ import annotations
import logging
import time
import numpy as np
import cv2
import win32con
import win32gui

_log = logging.getLogger("fh6.capture")

CANON = (1920, 1080)

_camera = None
_camera_unavailable = False
_hwnd_cache: dict[str, int] = {}


def find_window(title: str) -> int:
    """返回具有指定标题的可见窗口的 hwnd，若未找到则返回 0。"""
    cached = _hwnd_cache.get(title)
    if cached and win32gui.IsWindow(cached):
        return cached
    matches: list[int] = []

    def _collect(hwnd: int, _) -> None:
        if win32gui.IsWindowVisible(hwnd):
            if win32gui.GetWindowText(hwnd).strip() == title:
                matches.append(hwnd)

    win32gui.EnumWindows(_collect, None)
    hwnd = matches[0] if matches else 0
    if hwnd:
        _hwnd_cache[title] = hwnd
    return hwnd


def client_rect(hwnd: int) -> tuple[int, int, int, int]:
    """返回窗口客户区域的 (left, top, width, height)。"""
    cl, ct, cr, cb = win32gui.GetClientRect(hwnd)
    width, height = cr - cl, cb - ct
    sx, sy = win32gui.ClientToScreen(hwnd, (cl, ct))
    return sx, sy, width, height


def using_dxgi() -> bool:
    return _camera is not None and not _camera_unavailable


def _grab_dxgi(region):
    global _camera, _camera_unavailable
    if _camera_unavailable:
        return None
    try:
        import bettercam
        if _camera is None:
            _camera = bettercam.create(output_idx=0, output_color="BGR")
        for _ in range(5):
            frame = _camera.grab(region=region) if region else _camera.grab()
            if frame is not None:
                return np.ascontiguousarray(frame)
            time.sleep(0.008)
        return None
    except Exception:  # noqa: BLE001  bettercam 初始化失败则回退
        _camera_unavailable = True
        return None


def _grab_mss(region):
    import mss
    with mss.MSS() as sct:
        if region:
            area = {"left": region[0], "top": region[1],
                    "width": region[2] - region[0],
                    "height": region[3] - region[1]}
        else:
            area = sct.monitors[1]
        shot = sct.grab(area)
        return np.ascontiguousarray(np.array(shot)[:, :, :3])


_capture_failing = False

# Treat any pixel below this 0-255 grayscale value as solid-black background.
_BLACK_THRESHOLD = 6
# Refuse to strip bars if doing so removes more than this fraction of either
# axis. Guards against dark scenes / load screens that look like a black bar.
_MAX_STRIP_FRACTION = 0.5
# Aspect-ratio tolerance: within this fraction of 16:9 counts as 16:9.
_ASPECT_EPS = 0.01


def _symmetric_strip(near: int, far: int) -> int:
    """如果 near 和 far 看起来像对称黑边则返回每侧裁剪量，否则返回 0。
    自然的深色区域不对称；真正的信箱/遮幅黑边是居中的，因此两侧应在容差范围内一致。"""
    if near == 0 and far == 0:
        return 0
    tol = max(5, int(max(near, far) * 0.10))
    if abs(near - far) > tol:
        return 0
    return min(near, far)


def _detect_strip_box(frame: np.ndarray) -> tuple[int, ...] | None:
    """返回 (top, bottom, left, right) 内矩形坐标以裁剪对称黑边，若无则返回 None。"""
    if frame.size == 0:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    row_lit = gray.max(axis=1) >= _BLACK_THRESHOLD
    col_lit = gray.max(axis=0) >= _BLACK_THRESHOLD
    if not row_lit.any() or not col_lit.any():
        return None
    top_dark = int(np.argmax(row_lit))
    bottom_dark = int(np.argmax(row_lit[::-1]))
    left_dark = int(np.argmax(col_lit))
    right_dark = int(np.argmax(col_lit[::-1]))
    vert = _symmetric_strip(top_dark, bottom_dark)
    horiz = _symmetric_strip(left_dark, right_dark)
    if vert == 0 and horiz == 0:
        return None
    new_h = h - 2 * vert
    new_w = w - 2 * horiz
    if new_h < h * _MAX_STRIP_FRACTION or new_w < w * _MAX_STRIP_FRACTION:
        return None
    return (vert, h - vert, horiz, w - horiz)


def _strip_black_bars(frame: np.ndarray) -> np.ndarray:
    """直接应用对称黑边裁剪。对测试和单次使用有用的轻量包装。"""
    box = _detect_strip_box(frame)
    if box is None:
        return frame
    t, b, l, r = box
    return frame[t:b, l:r]


def _detect_aspect_box(h: int, w: int) -> tuple[int, ...] | None:
    """返回最大居中 16:9 子矩形的 (top, bottom, left, right)，
    若 (h, w) 已在容差内匹配 16:9 则返回 None。"""
    if h == 0 or w == 0:
        return None
    target = CANON[0] / CANON[1]                     # 16/9
    current = w / h
    if abs(current - target) <= _ASPECT_EPS:
        return None
    if current > target:                             # 画面过宽
        crop_w = int(round(h * target))
        x = (w - crop_w) // 2
        return (0, h, x, x + crop_w)
    crop_h = int(round(w / target))                  # 画面过高
    y = (h - crop_h) // 2
    return (y, y + crop_h, 0, w)


# Plan: cached crop boxes + resize flag, keyed on the input frame shape.
# Computed once from a real game frame, then reused on every poll - turns
# normalisation into a pair of array slices plus an optional resize.
_plan: dict | None = None


def _build_plan(frame: np.ndarray) -> dict:
    strip = _detect_strip_box(frame)
    if strip:
        t, b, l, r = strip
        h, w = b - t, r - l
    else:
        h, w = frame.shape[:2]
    aspect = _detect_aspect_box(h, w)
    if aspect:
        t2, b2, l2, r2 = aspect
        h, w = b2 - t2, r2 - l2
    return {
        "input_shape": frame.shape,
        "strip": strip,
        "aspect": aspect,
        "needs_resize": (w, h) != CANON,
    }


def reset_normalize_plan() -> None:
    """丢弃缓存的规范化计划，使下一次 normalize_frame 重新检测。
    当捕获区域或游戏设置改变时调用（例如用户点击开始时）。"""
    global _plan
    _plan = None


def normalize_frame(frame: np.ndarray) -> np.ndarray:
    """应用缓存的黑边裁剪 / 16:9 裁剪 / 1080p 缩放计划；
    若尚无可用的计划或输入形状改变，则根据此帧构建计划。"""
    global _plan
    if frame is None or frame.size == 0:
        return np.zeros((CANON[1], CANON[0], 3), dtype=np.uint8)
    if _plan is None or _plan["input_shape"] != frame.shape:
        # Skip caching a plan derived from a totally blank frame (capture
        # failure fallback). Without this, a transient blank stays cached.
        if frame.max() < _BLACK_THRESHOLD:
            return cv2.resize(frame, CANON, interpolation=cv2.INTER_AREA) \
                if (frame.shape[1], frame.shape[0]) != CANON else frame
        _plan = _build_plan(frame)
        _log.info("normalize plan: input=%s strip=%s aspect=%s resize=%s",
                  frame.shape, _plan["strip"], _plan["aspect"],
                  _plan["needs_resize"])
    plan = _plan
    if plan["strip"]:
        t, b, l, r = plan["strip"]
        frame = frame[t:b, l:r]
    if plan["aspect"]:
        t, b, l, r = plan["aspect"]
        frame = frame[t:b, l:r]
    if plan["needs_resize"]:
        frame = cv2.resize(frame, CANON, interpolation=cv2.INTER_AREA)
    return frame


def grab_screen(window_title: str | None = None) -> np.ndarray:
    """捕获 BGR 1920x1080 帧。DXGI 失败时回退到 mss；
    若两个后端都失败则返回空白帧。"""
    global _capture_failing
    region = None
    if window_title:
        hwnd = find_window(window_title)
        if hwnd:
            x, y, w, h = client_rect(hwnd)
            if w > 0 and h > 0:
                region = (x, y, x + w, y + h)
    frame = _grab_dxgi(region)
    if frame is None:
        try:
            frame = _grab_mss(region)
        except Exception:  # noqa: BLE001  MSS 也失败
            if not _capture_failing:
                _log.warning("捕获失败")
                _capture_failing = True
            frame = None
    if frame is None:
        return np.zeros((CANON[1], CANON[0], 3), dtype=np.uint8)
    if _capture_failing:
        _log.info("捕获已恢复")
        _capture_failing = False
    return normalize_frame(frame)


def foreground_title() -> str:
    return win32gui.GetWindowText(win32gui.GetForegroundWindow())


def is_game_focused(expected_title: str,
                    title_getter=foreground_title) -> bool:
    return title_getter().strip() == expected_title


def focus_window(title: str) -> bool:
    """将指定窗口置于前台。成功返回 True。"""
    hwnd = find_window(title)
    if not hwnd:
        return False
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:  # noqa: BLE001  SetForegroundWindow 可能失败
        return False
