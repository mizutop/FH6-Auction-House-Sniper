"""购买 CSV 记录和声音/通知提醒。"""
from __future__ import annotations
import csv
import datetime as dt
from pathlib import Path


def log_purchase(log_path: str | Path, outcome: str, loop_seconds: float,
                 total: int) -> None:
    """追加一行到购买 CSV。如果是新文件则写入表头。"""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(
                ["timestamp", "outcome", "loop_seconds", "total_bought"])
        writer.writerow([
            dt.datetime.now().isoformat(timespec="seconds"),
            outcome, f"{loop_seconds:.1f}", total,
        ])


def notify_success(car_count: int, sound: bool, toast: bool) -> None:
    """购买成功后播放蜂鸣音 + Windows 通知。"""
    if sound:
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:  # noqa: BLE001  蜂鸣音失败不影响功能
            pass
    if toast:
        try:
            from win11toast import toast as show_toast
            show_toast("FH6 狙击工具",
                       f"已购得车辆（本会话共 {car_count} 辆）")
        except Exception:  # noqa: BLE001  通知失败不影响功能
            pass
