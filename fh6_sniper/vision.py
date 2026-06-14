"""屏幕识别：OpenCV 模板匹配和 HSV 颜色掩码。"""
from __future__ import annotations
from enum import Enum, auto
from pathlib import Path
import cv2
import numpy as np


class Screen(Enum):
    UNKNOWN = auto()
    SEARCH_CONFIG = auto()
    RESULTS_HAS_CARS = auto()
    RESULTS_EMPTY = auto()
    RESULTS_LOADING = auto()
    AUCTION_OPTIONS = auto()
    PLAYER_OPTIONS = auto()
    BUY_OUT = auto()
    BUYOUT_PROGRESS = auto()
    BUYOUT_SUCCESS = auto()
    BUYOUT_FAILED = auto()
    CLAIM_CAR = auto()
    AH_LANDING = auto()


TEMPLATE_SCREENS: dict[str, Screen] = {
    "search.png": Screen.SEARCH_CONFIG,
    "auction_details.png": Screen.RESULTS_HAS_CARS,
    "no_auctions.png": Screen.RESULTS_EMPTY,
    "auction_loading.png": Screen.RESULTS_LOADING,
    "auction_options.png": Screen.AUCTION_OPTIONS,
    "player_options.png": Screen.PLAYER_OPTIONS,
    "buy_out.png": Screen.BUY_OUT,
    "buy_out_bgoff.png": Screen.BUY_OUT,
    "buy_out_progress.png": Screen.BUYOUT_PROGRESS,
    "buy_out_progress_bgoff.png": Screen.BUYOUT_PROGRESS,
    "buyout_successful.png": Screen.BUYOUT_SUCCESS,
    "buyout_failed.png": Screen.BUYOUT_FAILED,
    "claim_car.png": Screen.CLAIM_CAR,
    "ah_landing.png": Screen.AH_LANDING,
}


def lime_mask(bgr: np.ndarray, lower: tuple, upper: tuple) -> np.ndarray:
    """根据 HSV 范围生成青绿色掩码。"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, np.array(lower, np.uint8), np.array(upper, np.uint8))


def largest_lime_bbox(bgr: np.ndarray, lower: tuple,
                       upper: tuple) -> tuple | None:
    """最大横幅状青绿色区域的外接矩形，若无则返回 None。"""
    mask = lime_mask(bgr, lower, upper)
    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0.0
    for c in contours:
        area = cv2.contourArea(c)
        if area < 2000:
            continue
        x, y, w, h = cv2.boundingRect(c)
        if h <= 0 or w / h < 4.0:        # 非横幅形状
            continue
        if area > best_area:
            best_area = area
            best = (x, y, w, h)
    return best


def _gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def match_template(scene: np.ndarray, template: np.ndarray) -> float:
    """模板在场景中的最佳 NCC 匹配分数。若模板过大则返回 0.0。"""
    s, t = _gray(scene), _gray(template)
    if t.shape[0] > s.shape[0] or t.shape[1] > s.shape[1]:
        return 0.0
    result = cv2.matchTemplate(s, t, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return float(max_val)


_DOWNSCALED_TEMPLATES: dict[int, np.ndarray] = {}


def _small(tmpl: np.ndarray) -> np.ndarray:
    key = id(tmpl)
    cached = _DOWNSCALED_TEMPLATES.get(key)
    if cached is None:
        cached = _downscale(tmpl)
        _DOWNSCALED_TEMPLATES[key] = cached
    return cached


def load_templates(template_dir: str | Path,
                   moving_background: bool = True) -> dict:
    """加载所有检测模板（灰度图）。若任何模板缺失则抛出异常。

    `moving_background` 选择加载哪组购买主体模板：
    True（默认）使用 BG-on 变体，False 使用 *_bgoff 变体。
    跳过另一组可为每次购买轮询节省几次全分辨率匹配。
    """
    out = {}
    for name in TEMPLATE_SCREENS:
        is_bgoff = name.endswith("_bgoff.png")
        if moving_background and is_bgoff:
            continue
        if not moving_background and _has_bgoff_variant(name):
            continue
        path = Path(template_dir) / name
        img = cv2.imread(str(path))
        if img is None:
            raise FileNotFoundError(f"模板缺失: {path}")
        gray = _gray(img)
        out[name] = gray
        _DOWNSCALED_TEMPLATES[id(gray)] = _downscale(gray)
    return out


def _has_bgoff_variant(name: str) -> bool:
    """如果此模板有注册的 *_bgoff 兄弟文件则返回 True。"""
    if name.endswith("_bgoff.png"):
        return False
    sibling = name[:-len(".png")] + "_bgoff.png"
    return sibling in TEMPLATE_SCREENS


# Distinctive results templates beat ah_landing (whose title also appears
# on the results screens).
_RESULTS_PRIORITY = ("auction_details.png", "no_auctions.png")

_MATCH_SCALE = 0.5


def _downscale(img: np.ndarray) -> np.ndarray:
    return cv2.resize(img, None, fx=_MATCH_SCALE, fy=_MATCH_SCALE,
                      interpolation=cv2.INTER_AREA)


# Where each template appears on a 1920x1080 frame, with padding.
TEMPLATE_REGIONS: dict[str, tuple] = {
    "search.png":             (472, 223, 1448, 471),
    "auction_details.png":    (889,  64, 1920, 294),
    "no_auctions.png":        (1113, 434, 1706, 690),
    "auction_loading.png":    (870, 180, 1840, 870),
    "auction_options.png":    (546, 276, 1374, 526),
    "player_options.png":     (580, 230, 1340, 486),
    "buy_out.png":               (520, 470, 1400, 620),
    "buy_out_bgoff.png":         (520, 470, 1400, 620),
    "buy_out_progress.png":      (520, 470, 1400, 620),
    "buy_out_progress_bgoff.png":(520, 470, 1400, 620),
    "buyout_successful.png":  (539, 334, 1374, 612),
    "buyout_failed.png":      (546, 378, 1374, 631),
    "claim_car.png":          (538, 359, 1374, 615),
    "ah_landing.png":         (16,   89,  387, 291),
}


# 必须以全分辨率匹配的模板。
# 购买主体和购买进度主体是短文本带裁剪；半分辨率会使文本模糊，
# 导致实时帧低于 0.80 阈值（~0.78 vs ~0.86）。
_FULL_RES_TEMPLATES = {
    "buy_out.png", "buy_out_bgoff.png",
    "buy_out_progress.png", "buy_out_progress_bgoff.png",
}


def screen_scores(scene_bgr: np.ndarray, templates: dict,
                   targets: set[Screen] | None = None) -> dict[str, float]:
    """每个模板的匹配分数，按区域裁剪。大部分模板以半分辨率运行；
    少数小文本带模板（见 _FULL_RES_TEMPLATES）以全分辨率运行。
    若 `targets` 是 Screen 集合，则仅评分这些模板（加上优先结果模板）。"""
    if targets is not None:
        wanted = set(_RESULTS_PRIORITY)
        wanted |= {n for n, scr in TEMPLATE_SCREENS.items() if scr in targets}
        templates = {n: t for n, t in templates.items() if n in wanted}
    gray = _gray(scene_bgr)
    h, w = gray.shape[:2]
    scores: dict[str, float] = {}
    for name, tmpl in templates.items():
        region = TEMPLATE_REGIONS.get(name)
        if region:
            x1, y1, x2, y2 = region
            crop = gray[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        else:
            crop = gray
        if name in _FULL_RES_TEMPLATES:
            scores[name] = match_template(crop, tmpl)
        else:
            scores[name] = match_template(_downscale(crop), _small(tmpl))
    return scores


def identify_screen(scene_bgr: np.ndarray, templates: dict,
                     threshold: float,
                     targets: set[Screen] | None = None) -> Screen:
    """返回高于 `threshold` 的最佳匹配 Screen，若无则返回 UNKNOWN。"""
    scores = screen_scores(scene_bgr, templates, targets=targets)
    for name in _RESULTS_PRIORITY:
        if scores.get(name, 0.0) >= threshold:
            return TEMPLATE_SCREENS[name]
    best_screen, best_score = Screen.UNKNOWN, threshold
    for name, score in scores.items():
        if score >= best_score:
            best_screen, best_score = TEMPLATE_SCREENS[name], score
    return best_screen


# 搜索配置界面的确认按钮区域（1920x1080）。
CONFIRM_ROW = (548, 714, 1372, 772)


def is_confirm_highlighted(scene_bgr: np.ndarray, lower: tuple,
                            upper: tuple,
                            region: tuple = CONFIRM_ROW) -> bool:
    """如果确认按钮显示青绿色高亮则返回 True。"""
    x1, y1, x2, y2 = region
    crop = scene_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return False
    mask = lime_mask(crop, lower, upper)
    return int(cv2.countNonZero(mask)) > 300


# 黄色「已售」印章 HSV 范围和每个插槽的区域。卡片以 202px 间距排列；
# 区域停在实时剩余时间标签和价格行图标上方。
SOLD_HSV_LOWER = (20, 120, 120)
SOLD_HSV_UPPER = (34, 255, 255)
SOLD_STAMP_REGION = (90, 185, 300, 295)

# A populated card has a digitally-rendered white UI body that produces
# pixels with high V and very low S. The FH6 moving-background scene shown
# through an empty slot is bright but never that pure - everything is tinted,
# textured, or has a colour cast. Counting these "pure-white" pixels gives a
# clean separator that works whether moving_background is on or off.
SLOT_POPULATED_WHITE_V_MIN = 230
SLOT_POPULATED_WHITE_S_MAX = 25
SLOT_POPULATED_WHITE_MIN = 30      # 每个插槽满足上述条件的最小像素数


def is_card_sold(scene_bgr: np.ndarray,
                  region: tuple = SOLD_STAMP_REGION) -> bool:
    """如果顶部结果卡片显示黄色「已售」印章则返回 True。"""
    x1, y1, x2, y2 = region
    crop = scene_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return False
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(SOLD_HSV_LOWER, np.uint8),
                       np.array(SOLD_HSV_UPPER, np.uint8))
    return int(cv2.countNonZero(mask)) > 800


SOLD_STAMP_REGIONS: tuple[tuple, ...] = (
    SOLD_STAMP_REGION,
    (90, 387, 300, 497),
    (90, 589, 300, 699),
    (90, 791, 300, 901),
)


def slot_states(scene_bgr: np.ndarray) -> tuple:
    """四个结果插槽的每个（已售，有卡片）状态。"""
    hsv = cv2.cvtColor(scene_bgr, cv2.COLOR_BGR2HSV)
    sold_mask = cv2.inRange(hsv,
                            np.array(SOLD_HSV_LOWER, np.uint8),
                            np.array(SOLD_HSV_UPPER, np.uint8))
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    out: list[tuple[bool, bool]] = []
    for (x1, y1, x2, y2) in SOLD_STAMP_REGIONS:
        sold = int(cv2.countNonZero(sold_mask[y1:y2, x1:x2])) > 800
        white = ((val[y1:y2, x1:x2] >= SLOT_POPULATED_WHITE_V_MIN)
                 & (sat[y1:y2, x1:x2] <= SLOT_POPULATED_WHITE_S_MAX))
        populated = int(white.sum()) > SLOT_POPULATED_WHITE_MIN
        out.append((sold, populated))
    return tuple(out)


def sold_slots(scene_bgr: np.ndarray) -> tuple:
    """四个结果插槽的每个「已售」标志。"""
    return tuple(sold for sold, _populated in slot_states(scene_bgr))


def first_buyable_slot(scene_bgr: np.ndarray) -> int:
    """返回 1-indexed 的第一个有卡片且未售出的插槽，若无则返回 0。"""
    for i, (sold, populated) in enumerate(slot_states(scene_bgr), start=1):
        if populated and not sold:
            return i
    return 0
