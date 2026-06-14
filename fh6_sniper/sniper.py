"""狙击状态机和测试用的 GameIO 包装。"""
from __future__ import annotations
import logging
import random
import time
from collections.abc import Callable
from . import actions, capture, paths, vision
from .config import Config, save_config
from .vision import Screen

log = logging.getLogger("fh6.sniper")


def _names(screens: set) -> str:
    return "{" + ", ".join(sorted(s.name for s in screens)) + "}"


class GameIO:
    """连接捕获 + 视觉 + 输入的胶水层。可替换以进行测试。"""

    def __init__(self, cfg: Config, templates: dict):
        self.cfg = cfg
        self.templates = templates
        self._last_screen = None

    def screen(self, targets: set[Screen] | None = None) -> Screen:
        """识别当前画面。如果 `targets` 是 Screen 集合，
        则仅匹配这些（加上优先结果模板和上次已知画面）。"""
        if (targets is not None and self._last_screen is not None
                and self._last_screen != Screen.UNKNOWN):
            targets = targets | {self._last_screen}
        frame = capture.grab_screen(self.cfg.window_title)
        result = vision.identify_screen(
            frame, self.templates, self.cfg.match_threshold, targets=targets)
        if result != self._last_screen:
            log.info("screen -> %s", result.name)
            self._last_screen = result
        return result

    def focused(self) -> bool:
        """检查 FH6 窗口是否为前景窗口。"""
        return capture.is_game_focused(self.cfg.window_title)

    def confirm_highlighted(self) -> bool:
        frame = capture.grab_screen(self.cfg.window_title)
        lo, hi = self.cfg.effective_lime_bounds()
        return vision.is_confirm_highlighted(frame, lo, hi)

    def card_sold(self) -> bool:
        frame = capture.grab_screen(self.cfg.window_title)
        return vision.is_card_sold(frame)

    def first_buyable_slot(self) -> int:
        frame = capture.grab_screen(self.cfg.window_title)
        return vision.first_buyable_slot(frame)

    def slot_states(self) -> tuple:
        """每个插槽的（已售，有卡片）标志。用于渲染等待门控。"""
        frame = capture.grab_screen(self.cfg.window_title)
        return vision.slot_states(frame)

    def press(self, name: str, times: int = 1) -> None:
        log.info("按键 %s%s", name, f" x{times}" if times > 1 else "")
        actions.tap_key(name, times,
                        self.cfg.key_hold_ms, self.cfg.between_keys_ms,
                        use_win32=self.cfg.win32_api_input)


class Sniper:
    """通过 GameIO 驱动拍卖行循环。"""

    def __init__(self, io: GameIO, cfg: Config,
                 clock=time.monotonic, sleeper=time.sleep,
                 on_purchase: Callable | None = None,
                 on_status: Callable | None = None,
                 on_stats: Callable | None = None):
        self.io = io
        self.cfg = cfg
        self.clock = clock
        self.sleeper = sleeper
        self.on_purchase = on_purchase
        self.on_status = on_status
        self.on_stats = on_stats
        self.cars_bought = 0
        self.searches = 0
        self.failed_buyouts = 0
        self.started_at = None
        self._stop = False
        # 一键式自动切换 BG 恢复保护。buy_out 和 buy_out_progress
        # 是唯一 BG 敏感的模板；当等待确认对话框超时时我们翻转标志，
        # 重新加载模板，重试一次，此后即使第二次尝试也失败也不再自动切换。
        self._auto_bg_toggled = False
        # 一旦本会话中识别到任何已知画面即为 True。
        # 尚未 _oriented 时的 recover_failed 通常意味着游戏语言不是英文
        # （模板只匹配英文界面）。
        self._oriented = False

    def request_stop(self) -> None:
        self._stop = True

    def _status(self, text: str) -> None:
        log.info("[status] %s", text)
        if self.on_status:
            self.on_status(text)

    def _emit_stats(self) -> None:
        if self.on_stats:
            self.on_stats(self.searches, self.cars_bought,
                          self.failed_buyouts)

    def _poll_delay(self) -> None:
        lo, hi = self.cfg.poll_interval_ms
        self.sleeper(random.uniform(lo, hi) / 1000.0)

    def _guard_focus(self) -> None:
        """阻塞直到 FH6 是前景窗口。进入时设置一次「已暂停」状态，而非每次滴答。"""
        if self.cfg.win32_api_input:
            return
        if self.io.focused():
            return
        self._status("已暂停：FH6 未聚焦")
        while not self.io.focused():
            if self._stop:
                return
            self.sleeper(0.5)

    def _press(self, name: str, times: int = 1) -> None:
        """发送按键，但仅在 FH6 有焦点时。"""
        self._guard_focus()
        if self._stop:
            return
        self.io.press(name, times)

    def _wait_for_populated_slots(self, timeout: float) -> bool:
        """阻塞等待 `timeout` 秒，直到 FH6 渲染出至少一张卡片。

        RESULTS_HAS_CARS 青绿色横幅比卡片 UI 完全绘制早 1-2 帧出现。
        如果在较早帧上调用 first_buyable_slot，会发现零个有效插槽并错误报告"全部已售"。
        在迭代之间紧密轮询 slot_states（5ms 间隔，非全局轮询节奏），
        因为此等待只在结果页面上运行且持续时间短。
        一旦看到有效插槽返回 True，超时返回 False（调用者仍应继续）。"""
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            if self._stop:
                return False
            for _sold, populated in self.io.slot_states():
                if populated:
                    return True
            # 5ms 间隔：防止紧密循环使单核饱和，并为基于 FakeClock 的测试
            # 提供推进虚拟时钟的方式，使超时确定性地触发。
            self.sleeper(0.005)
        log.info("等待有效插槽超时（%.1fs）", timeout)
        return False

    def _try_toggle_moving_background(self) -> bool:
        """验证备用变体确实匹配当前帧后，自动切换 moving_background。

        在 buy_out wait_for 超时时触发。buy_out 和 buy_out_progress
        是唯一 BG 敏感的模板，但超时也可能由缓慢渲染或瞬态问题引起——
        不总是 BG 不匹配。为避免在这些误报上损坏用户配置，
        本方法加载相反标志的模板并针对新帧运行 identify_screen。
        仅当备用变体确实识别出 BUY_OUT 或 PLAYER_OPTIONS 时才提交切换
        （替换 io.templates、保存配置、设置一次性保护）。

        如果提交了切换（调用者应重试等待）则返回 True；
        如果本会话已尝试过或备用变体也不匹配则返回 False（此时回退到恢复）。"""
        if self._auto_bg_toggled:
            return False
        cfg = self.cfg
        new_value = not cfg.moving_background
        try:
            candidate = vision.load_templates(
                paths.app_dir() / cfg.template_dir,
                moving_background=new_value)
        except Exception:  # noqa: BLE001  失败时跳过自动切换
            log.exception("自动切换：加载备用模板失败")
            return False
        frame = capture.grab_screen(cfg.window_title)
        result = vision.identify_screen(
            frame, candidate, cfg.match_threshold,
            targets={Screen.BUY_OUT, Screen.PLAYER_OPTIONS})
        if result not in (Screen.BUY_OUT, Screen.PLAYER_OPTIONS):
            log.info("自动切换：备用变体同样不匹配 — 超时非 BG 不匹配导致")
            return False
        self.io.templates = candidate
        cfg.moving_background = new_value
        try:
            save_config(cfg, paths.app_dir() / "config.json")
        except Exception:  # noqa: BLE001  持久化失败但运行时切换保留
            log.exception("自动切换：save_config 失败（运行时切换保留，持久化未执行）")
        self._auto_bg_toggled = True
        log.info("自动切换移动背景 -> %s "
                 "（已验证帧；模板已切换，已保存至 config.json）", new_value)
        self._status(f"已自动切换移动背景 -> {new_value}")
        return True

    def wait_for(self, screens: set, timeout: float) -> Screen | None:
        """轮询直到当前画面在 `screens` 中，或超时。
        在 _guard_focus 中花费的时间不计入超时。"""
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            if self._stop:
                return None
            before = self.clock()
            self._guard_focus()
            if self._stop:
                return None
            deadline += self.clock() - before
            current = self.io.screen(targets=screens)
            if current in screens:
                log.info("wait_for %s -> %s", _names(screens), current.name)
                return current
            self._poll_delay()
        log.info("wait_for %s -> 超时（%.0fs）", _names(screens), timeout)
        return None

    def _press_until(self, key: str, from_screen, targets: set,
                     settle: float = 0.7, reach: float = 8.0,
                     attempts: int = 4) -> Screen | None:
        """按下 `key` 直到到达目标画面。如果画面未在 `settle` 内离开
        `from_screen`，则重试按键。"""
        inner_targets = targets | {from_screen}
        for _ in range(attempts):
            if self._stop:
                return None
            self._press(key)
            deadline = self.clock() + settle
            while self.clock() < deadline:
                if self._stop:
                    return None
                s = self.io.screen(targets=inner_targets)
                if s in targets:
                    return s
                if s != from_screen:
                    return self.wait_for(targets, reach)
                self._poll_delay()
        return None

    def _goto_search_config(self) -> bool:
        """到达搜索配置画面。返回是否成功。"""
        s = self.io.screen()
        for _ in range(10):
            if self._stop:
                return False
            if s == Screen.SEARCH_CONFIG:
                self._oriented = True
                return True
            if s == Screen.AH_LANDING:
                self._oriented = True
                return self._enter_search_from_landing(known=s)
            if s == Screen.UNKNOWN:
                self.sleeper(0.3)
                s = self.io.screen()
                continue
            self._oriented = True
            self._press("esc")
            s = self._await_settle(prev=s)
        if self._oriented:
            self._status("无法定位：请在拍卖行中启动机器人")
        else:
            self._status("无法定位：请将游戏语言设置为英文")
        return False

    def _enter_search_from_landing(self, known: Screen | None = None) -> bool:
        """从拍卖行首页菜单打开搜索拍卖。"""
        self._status("正在打开搜索拍卖")
        for attempt in range(1, 5):
            if self._stop:
                return False
            s = known if known is not None else self.io.screen()
            known = None
            log.info("enter_search 尝试 %d：screen=%s", attempt, s.name)
            if s == Screen.SEARCH_CONFIG:
                return True
            if s == Screen.UNKNOWN:
                self.sleeper(0.6)
                continue
            if s != Screen.AH_LANDING:
                self._press("esc")
                self.sleeper(0.3)
                continue
            # 首页菜单需要片刻才能准备好接收输入；此延迟防止首个 Enter 被丢弃。
            self.sleeper(0.2)
            self._press("enter")
            if self.wait_for({Screen.SEARCH_CONFIG}, 0.9) is not None:
                return True
        log.info("enter_search：4 次尝试后放弃")
        return False

    def _navigate_to_confirm(self) -> bool:
        """按向下键直到确认按钮高亮。"""
        for _ in range(12):
            if self._stop:
                return False
            if self.io.confirm_highlighted():
                return True
            self._press("down")
        return self.io.confirm_highlighted()

    def _recover(self) -> str:
        """按 ESC 退回到搜索配置或拍卖行首页。

        避免在单个 UNKNOWN 帧上按 ESC（可能是过渡闪烁），
        但在画面持续 UNKNOWN 后按 ESC。持续的 UNKNOWN 通常意味着
        我们处于没有模板的弹出窗口（例如「出价」对话框）需要退出。
        ESC 只关闭弹出窗口，从不确认任何内容。"""
        self._status("正在恢复")
        s = self.io.screen()
        unknown_streak = 0
        for _ in range(10):
            if self._stop:
                return "recover_failed"
            if s in (Screen.SEARCH_CONFIG, Screen.AH_LANDING):
                return "recovered"
            if s == Screen.UNKNOWN:
                unknown_streak += 1
                if unknown_streak >= 4:           # 约 1.2s 卡在 UNKNOWN
                    self._press("esc")
                    unknown_streak = 0
                    s = self._await_settle(prev=s)
                    continue
                self.sleeper(0.3)
                s = self.io.screen()
                continue
            unknown_streak = 0
            self._press("esc")
            s = self._await_settle(prev=s)
        log.info("恢复：放弃")
        return "recover_failed"

    def _await_settle(self, prev: Screen, timeout: float = 1.2) -> Screen:
        """等待画面稳定到一个已知状态（不同于 `prev`），或超时。通常在 ESC 后使用。"""
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            if self._stop:
                return Screen.UNKNOWN
            self._poll_delay()
            s = self.io.screen()
            if s != Screen.UNKNOWN and s != prev:
                return s
        return Screen.UNKNOWN

    def _back_to_landing(self, known: Screen | None = None) -> None:
        """按 ESC 退回到拍卖行首页菜单，无论当前在几层深。"""
        s = known if known is not None else self.io.screen()
        for _ in range(6):
            if self._stop:
                return
            if s == Screen.AH_LANDING:
                return
            if s == Screen.UNKNOWN:
                self.sleeper(0.3)
                s = self.io.screen()
                continue
            self._press("esc")
            s = self._await_settle(prev=s)

    def _escape_player_options(self) -> str:
        """从已售车辆可能打开的玩家选项菜单中 ESC 退出。
        即使画面为 UNKNOWN 也会按 ESC；停在 AH_LANDING。

        返回 "no_cars" —— 车辆在我们狙击前已被售出，
        这算作一次错过的搜索，而非失败的购买。"""
        self._status("列表已售罄，跳过")
        for _ in range(6):
            if self._stop:
                return "recover_failed"
            if self.io.screen() == Screen.AH_LANDING:
                return "no_cars"
            self._press("esc")
            self.sleeper(0.6)
        return "no_cars"

    def _confirm_yes(self) -> Screen | None:
        """在购买确认对话框上按「是」并观察画面。

        状态机：
        - **BUY_OUT**（确认仍在显示）：Enter 被丢弃，重新按下。
        - **BUYOUT_PROGRESS**：请求已发送，慢速轮询，等待结果。
        - **BUYOUT_SUCCESS / BUYOUT_FAILED**：完成。
        - **UNKNOWN**：短暂继续轮询，然后放弃（可能是我们没有模板的弹出窗口，
          例如因为 Down 键丢失而出现的「出价」对话框）。

        初始预算 5s —— 如果从未看到任何可识别的购买画面，则限制轮询时间。
        一旦知道请求已发送（BUYOUT_PROGRESS），延长至 `cfg.timeout_outcome_s`。"""
        cfg = self.cfg
        self._press("enter")
        deadline = self.clock() + 5.0          # 初始：5s 等待看到某些内容
        in_flight = False
        enter_attempts = 1
        targets = {Screen.BUY_OUT, Screen.BUYOUT_PROGRESS,
                   Screen.BUYOUT_SUCCESS, Screen.BUYOUT_FAILED}
        while self.clock() < deadline:
            if self._stop:
                return None
            before = self.clock()
            self._guard_focus()
            if self._stop:
                return None
            deadline += self.clock() - before
            s = self.io.screen(targets=targets)
            if s in (Screen.BUYOUT_SUCCESS, Screen.BUYOUT_FAILED):
                return s
            if s == Screen.BUY_OUT and enter_attempts < 4:
                self._press("enter")
                enter_attempts += 1
            elif s == Screen.BUYOUT_PROGRESS and not in_flight:
                in_flight = True
                deadline = self.clock() + cfg.timeout_outcome_s
            if in_flight:
                self.sleeper(0.2)              # 5 Hz - 请求已发送，慢速轮询
            else:
                self._poll_delay()             # ~15 Hz - 仍在确定状态
        return None

    def _collect(self) -> None:
        """收取赢得的车辆。「领取车辆」弹窗有两个阶段，都识别为 CLAIM_CAR；
        按回车直到画面离开它。"""
        self._status("正在收取车辆")
        if self._press_until("y", Screen.RESULTS_HAS_CARS,
                             {Screen.AUCTION_OPTIONS}) is None:
            return
        if self._press_until("enter", Screen.AUCTION_OPTIONS,
                             {Screen.CLAIM_CAR}) is None:
            return
        deadline = self.clock() + self.cfg.timeout_claim_s
        while self.clock() < deadline:
            if self._stop:
                return
            s = self.io.screen()
            if s == Screen.CLAIM_CAR:
                self._press("enter")
                self.sleeper(1.0)
            elif s == Screen.UNKNOWN:
                self.sleeper(0.3)
            else:
                return

    def run_once(self) -> str:
        """一次狙击尝试。

        返回: bought | failed | no_cars | recovered | recover_failed.
        """
        log.info("--- run_once ---")
        cfg = self.cfg
        if not self._goto_search_config():
            return "recover_failed"

        self._status("正在搜索")
        if not self._navigate_to_confirm():
            return self._recover()
        result = self._press_until(
            "enter", Screen.SEARCH_CONFIG,
            {Screen.RESULTS_HAS_CARS, Screen.RESULTS_EMPTY},
            reach=cfg.timeout_results_s)
        if result is not Screen.RESULTS_HAS_CARS:
            self._back_to_landing(known=result)
            return "no_cars"

        # RESULTS_HAS_CARS 横幅在卡片 UI 本身之前渲染。
        # 在检查插槽状态前等待至少一张有内容的卡片，
        # 否则 first_buyable_slot 在未渲染的帧上返回 0，
        # 机器人会错误报告"全部已售"。
        self._wait_for_populated_slots(1.5)

        slot = self.io.first_buyable_slot()
        if slot == 0:
            self._status("所有列表已售罄，跳过")
            self._back_to_landing(known=result)
            return "no_cars"

        self._status("找到车辆，正在购买")
        for _ in range(slot - 1):
            self._press("down")

        if slot > 1 and self.io.first_buyable_slot() != slot:
            self._status("导航期间列表已售出，跳过")
            self._back_to_landing(known=result)
            return "no_cars"

        seen = self._press_until(
            "y", Screen.RESULTS_HAS_CARS,
            {Screen.AUCTION_OPTIONS, Screen.PLAYER_OPTIONS})
        if seen == Screen.PLAYER_OPTIONS:
            return self._escape_player_options()
        if seen is None:
            return self._recover()

        # 不重试 down+enter。丢失的 Down 会使「出价」高亮，
        # 因此重试的 Enter 可能会出价。
        self._press("down")
        if cfg.buyout_select_delay_ms:
            self.sleeper(cfg.buyout_select_delay_ms / 1000.0)
        self._press("enter")
        # 紧凑的 1.0s 等待：典型 BUY_OUT 对话框渲染时间为 200-400ms，
        # 因此 1.0s 约 3 倍余量，同时在 moving_background 标志错误
        # 且模板从不匹配时削减 1.5s 的浪费时间。
        seen = self.wait_for({Screen.BUY_OUT, Screen.PLAYER_OPTIONS}, 1.0)
        if seen == Screen.PLAYER_OPTIONS:
            return self._escape_player_options()
        if seen is None and self._try_toggle_moving_background():
            seen = self.wait_for(
                {Screen.BUY_OUT, Screen.PLAYER_OPTIONS}, 1.0)
            if seen == Screen.PLAYER_OPTIONS:
                return self._escape_player_options()
        if seen is None:
            return self._recover()

        outcome = self._confirm_yes()
        if outcome is None:
            return self._recover()

        self._press("enter")            # 关闭结果弹出窗口

        if outcome == Screen.BUYOUT_FAILED:
            self._back_to_landing()
            return "failed"

        if cfg.collect_after_buyout:
            self._collect()
        self._back_to_landing()
        return "bought"

    def _auto_stop_reached(self) -> bool:
        cfg = self.cfg
        if not cfg.auto_stop_enabled:
            return False
        if self.cars_bought >= cfg.max_cars:
            return True
        elapsed_min = (self.clock() - self.started_at) / 60.0
        return elapsed_min >= cfg.max_minutes

    def run(self) -> str:
        """循环狙击尝试，直到停止或满足自动停止条件。

        返回: stopped | auto_stop | recover_failed.
        """
        self.started_at = self.clock()
        log.info("=== 狙击开始 ===")
        self._status("运行中")
        while not self._stop:
            if self._auto_stop_reached():
                self._status("自动停止条件已满足")
                return "auto_stop"
            self._guard_focus()
            if self._stop:
                break
            t0 = self.clock()
            outcome = self.run_once()
            log.info("run_once 结果: %s", outcome)
            self.searches += 1
            if outcome == "recover_failed":
                self._emit_stats()
                if self._oriented:
                    self._status("已停止：无法恢复")
                else:
                    self._status("已停止：请将游戏语言设置为英文")
                return "recover_failed"
            if outcome == "failed":
                self.failed_buyouts += 1
            if outcome == "bought":
                self.cars_bought += 1
                loop_s = self.clock() - t0
                self._status(f"已购 {self.cars_bought} 辆车")
                if self.on_purchase:
                    self.on_purchase(loop_s, self.cars_bought)
            self._emit_stats()
            self.sleeper(self.cfg.loop_pace_s)
        self._status("已停止")
        return "stopped"
