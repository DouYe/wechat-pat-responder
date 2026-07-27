import asyncio
import ctypes
import hashlib
import json
import os
import queue
import random
import re
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path

APP_VERSION = "1.0.0"
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent

for vendor_name in ("vendor", "vendor3"):
    candidate = APP_DIR / vendor_name
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
        sys.path.insert(0, str(candidate / "win32"))
        sys.path.insert(0, str(candidate / "pythonwin"))
        dll_dir = candidate / "pywin32_system32"
        if hasattr(os, "add_dll_directory") and dll_dir.is_dir():
            os.add_dll_directory(str(dll_dir))

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from PIL import Image, ImageChops
import win32gui
import win32ui
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapDecoder
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage import FileAccessMode, StorageFile


user32 = ctypes.windll.user32
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
PIL_TEMP_DIR = Path(tempfile.gettempdir()) / "WeChatPatResponder"
PIL_TEMP_DIR.mkdir(parents=True, exist_ok=True)
CAPTURE_PATH = (PIL_TEMP_DIR / "wechat_chat_capture.png").resolve()
SIDEBAR_CAPTURE_PATH = (PIL_TEMP_DIR / "wechat_sidebar_capture.png").resolve()
EVENT_LOG_PATH = APP_DIR / "tickle_events.log"
STATE_PATH = APP_DIR / "tickle_state.json"
DISPLAY_TIME_RE = re.compile(
    r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b|\b\d{1,2}/\d{1,2}\b|yesterday",
    re.IGNORECASE,
)
SYSTEM_REPLIES = [
    "[系统]拍击已受理",
    "[系统]用户被拍醒",
    "[系统]响应超时",
    "[系统]检测到爪子",
    "[系统]拍击过载",
]
RED_PACKET_REPLIES = [
    "抽中红包，找我兑奖",
    "红包彩蛋已激活",
    "中奖啦，线下领取",
]


def find_wechat_window():
    candidates = []

    @EnumWindowsProc
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        class_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_name, 256)
        title_text = title.value.strip()
        class_text = class_name.value
        if (
            title_text.lower() in {"weixin", "wechat", "微信"}
            or (
                "qwindow" in class_text.lower()
                and ("weixin" in title_text.lower() or "wechat" in title_text.lower())
            )
        ):
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
            candidates.append((area, hwnd, title_text))
        return True

    user32.EnumWindows(callback, 0)
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def find_sidebar_divider(image):
    """Locate the draggable vertical divider between the list and current chat."""
    gray = image.convert("L")
    width, height = gray.size
    start = max(180, int(width * 0.22))
    end = min(520, int(width * 0.60))
    best_score = -1.0
    best_x = min(310, max(250, int(width * 0.34)))

    for x in range(start, end):
        left_column = gray.crop((x - 1, 20, x, height - 20))
        right_column = gray.crop((x, 20, x + 1, height - 20))
        histogram = ImageChops.difference(left_column, right_column).histogram()
        total = max(1, sum(histogram))
        score = sum(histogram[8:]) / total
        if score > best_score:
            best_score = score
            best_x = x
    return best_x


def capture_wechat(hwnd):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top
    if width < 500 or height < 350:
        raise RuntimeError("微信窗口太小或已最小化，请恢复主窗口。")

    window_dc = win32gui.GetWindowDC(hwnd)
    source_dc = win32ui.CreateDCFromHandle(window_dc)
    memory_dc = source_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(source_dc, width, height)
    memory_dc.SelectObject(bitmap)

    try:
        ok = user32.PrintWindow(hwnd, memory_dc.GetSafeHdc(), 2)
        if not ok:
            raise RuntimeError("PrintWindow 无法抓取微信窗口。")
        info = bitmap.GetInfo()
        data = bitmap.GetBitmapBits(True)
        image = Image.frombuffer(
            "RGB",
            (info["bmWidth"], info["bmHeight"]),
            data,
            "raw",
            "BGRX",
            0,
            1,
        ).copy()
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        memory_dc.DeleteDC()
        source_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, window_dc)

    # 左侧会话栏可以由用户拖动宽度，因此每次从画面中定位分隔线。
    divider = find_sidebar_divider(image)
    sidebar_left = 65
    sidebar_top = int(height * 0.08)
    sidebar_bottom = height - 12

    # 聊天记录区排除左侧列表和底部输入框。
    crop_left = divider
    crop_top = int(height * 0.08)
    crop_right = width - 10
    crop_bottom = int(height * 0.79)
    chat_image = image.crop((crop_left, crop_top, crop_right, crop_bottom))
    sidebar_image = image.crop(
        (sidebar_left, sidebar_top, divider, sidebar_bottom)
    )
    chat_image.save(CAPTURE_PATH)
    sidebar_image.save(SIDEBAR_CAPTURE_PATH)
    return (
        chat_image,
        sidebar_image,
        (left, top, right, bottom),
        {
            "divider": divider,
            "sidebar_left": sidebar_left,
            "sidebar_top": sidebar_top,
        },
    )


async def recognize_image(path):
    file = await StorageFile.get_file_from_path_async(str(path))
    stream = await file.open_async(FileAccessMode.READ)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    try:
        engine = OcrEngine.try_create_from_language(Language("en-US"))
    except Exception:
        engine = None
    if engine is None:
        engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError("Windows OCR 不可用。")
    result = await engine.recognize_async(bitmap)

    lines = []
    for line in result.lines:
        words = list(line.words)
        if words:
            top = min(float(word.bounding_rect.y) for word in words)
            bottom = max(
                float(word.bounding_rect.y + word.bounding_rect.height) for word in words
            )
        else:
            top = bottom = 0.0
        lines.append({"text": line.text, "top": top, "bottom": bottom})
    return engine.recognizer_language.language_tag, result.text, lines


async def recognize_capture():
    return await recognize_image(CAPTURE_PATH)


def normalize(value):
    return re.sub(r"\s+", " ", value.strip().lower())


def record_tickle_event(row_id, text, wechat_time):
    detected_at = time.strftime("%Y-%m-%d %H:%M:%S")
    with EVENT_LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(
            f"{detected_at}\t{wechat_time or '-'}\t{row_id}\t{text}\n"
        )
    return detected_at


def load_tickle_state():
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("state must be an object")
        return {
            "counts": dict(data.get("counts", {})),
            "streaks": dict(data.get("streaks", {})),
            "last_seen": dict(data.get("last_seen", {})),
        }
    except Exception:
        return {"counts": {}, "streaks": {}, "last_seen": {}}


def save_tickle_state(state):
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def row_metadata(lines, target_line, trigger_phrases):
    target_center = (target_line["top"] + target_line["bottom"]) / 2
    nearby = [
        line
        for line in lines
        if abs(((line["top"] + line["bottom"]) / 2) - target_center) <= 38
    ]

    display_time = ""
    for line in nearby:
        match = DISPLAY_TIME_RE.search(line["text"])
        if match:
            display_time = match.group(0)
            break

    title_candidates = []
    for line in nearby:
        candidate_text = normalize(line["text"])
        if line["top"] >= target_line["top"]:
            continue
        if DISPLAY_TIME_RE.search(candidate_text):
            continue
        if any(phrase and phrase in candidate_text for phrase in trigger_phrases):
            continue
        title_candidates.append(line)

    if title_candidates:
        title = max(title_candidates, key=lambda item: item["top"])["text"]
        row_id = normalize(title)
    else:
        # 没读到标题时使用行位置；新消息通常仍会移动到稳定的列表行。
        row_id = f"row-{round(target_line['top'] / 58)}"
    return display_time, row_id


def matching_lines(lines, trigger_phrases, source_image=None):
    matches = []
    for line in lines:
        text = normalize(line["text"])
        phrase = next((p for p in trigger_phrases if p and p in text), None)
        if not phrase:
            continue
        key = f"{text}|{round(line['top'] / 8)}"
        if source_image is not None:
            row_top = max(0, int(line["top"] - 32))
            row_bottom = min(source_image.height, int(line["bottom"] + 32))
            row = source_image.crop((0, row_top, source_image.width, row_bottom))
            row = row.convert("L").resize((96, 24))
            digest = hashlib.sha1(row.tobytes()).hexdigest()[:12]
            key = f"{key}|{digest}"
        display_time, row_id = row_metadata(lines, line, trigger_phrases)
        matches.append(
            (
                key,
                line["text"],
                line["top"],
                line["bottom"],
                display_time,
                row_id,
            )
        )
    return matches


def sidebar_row_is_selected(sidebar_image, line_top, line_bottom):
    """Detect WeChat's green selected-row background around a preview line."""
    row_top = max(0, int(line_top - 34))
    row_bottom = min(sidebar_image.height, int(line_bottom + 18))
    row = sidebar_image.crop((0, row_top, sidebar_image.width, row_bottom)).convert(
        "RGB"
    )
    pixels = list(row.getdata())
    if not pixels:
        return False
    green_pixels = sum(
        1
        for red, green, blue in pixels
        if green >= 95 and green >= red + 18 and green >= blue + 8
    )
    return green_pixels / len(pixels) >= 0.22


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"微信拍一拍随机回复器 v{APP_VERSION}")
        self.root.geometry("780x690")
        self.root.minsize(700, 590)
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.confirmed_once = False
        self.last_window_rect = None
        self.tickle_state = load_tickle_state()

        self.status = tk.StringVar(value="状态：尚未连接")
        self.auto_send = tk.BooleanVar(value=True)
        self.any_change_mode = tk.BooleanVar(value=False)
        self.sidebar_mode = tk.BooleanVar(value=True)
        self.build_ui()
        self.root.after(100, self.process_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.log("随机行为已就绪：抽象短句、计数器、连击、系统消息和红包彩蛋。")

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, textvariable=self.status).pack(anchor="w")

        ttk.Label(outer, text="触发词（用分号分隔）").pack(anchor="w", pady=(12, 4))
        self.trigger_entry = ttk.Entry(outer)
        self.trigger_entry.insert(0, "tickled m;拍了拍我;拍了拍你")
        self.trigger_entry.pack(fill="x")

        ttk.Label(outer, text="随机回复（每行一条，最多 12 个字符）").pack(
            anchor="w", pady=(12, 4)
        )
        self.replies = scrolledtext.ScrolledText(outer, height=6, wrap="word")
        self.replies.insert(
            "1.0",
            "你把我拍醒了\n"
            "别拍了，会秃\n"
            "再拍就收费啦\n"
            "拍一下五毛钱\n"
            "谁在召唤本尊\n"
            "检测到一只手\n"
            "你成功激活我\n"
            "手感怎么样呀\n"
            "有事请先投币\n"
            "拍我干嘛呀\n"
            "系统正在装死\n"
            "我刚刚掉线了\n"
            "拍轻点，会碎\n"
            "再拍发票给你\n"
            "响应超时，装傻\n"
            "触发隐藏彩蛋\n"
            "已收到你的爪\n"
            "别闹，我在潜水\n"
            "叮！随机回应\n"
            "拍得不错，下次别拍\n"
            "你拍到了空气\n"
            "本人正在加载\n"
            "灵魂暂时外借\n"
            "你的手有想法\n"
            "我被拍成二维码\n"
            "刚才是谁震我\n"
            "此人没有实体\n"
            "拍一下少根头发\n"
            "你碰到缓存了\n"
            "我的CPU疼\n"
            "请勿敲击玻璃\n"
            "人类行为已记录\n"
            "你把次元拍歪了\n"
            "该部位暂无响应\n"
            "拍击已被宇宙收录\n"
            "我在桌下重启\n"
            "你的手需要冷静\n"
            "已为你呼叫保安\n"
            "这一下拍到明天\n"
            "我不是西瓜\n"
            "检测到碳基生物\n"
            "我正在假装在线\n"
            "你拍的是替身\n"
            "主体意识未连接\n"
            "这拍子不太对\n"
            "世界线发生偏移\n"
            "你触发了空气墙\n"
            "服务器表示害怕\n"
            "不要打扰像素\n"
            "已自动变成石头\n"
            "拍击被猫咪拦截\n"
            "大脑已停止服务\n"
            "你的拍击被退货\n"
            "本人今日不宜触碰\n"
            "这一拍很有哲学\n"
            "请稍后再拍灵魂\n"
            "拍击正在排队\n"
            "你惊动了服务器\n"
            "我刚从二维回来\n"
            "请不要刷新本人",
        )
        self.replies.pack(fill="x")

        ttk.Checkbutton(
            outer,
            text="同时监控当前聊天变化（默认关闭；关闭时只监控左栏）",
            variable=self.any_change_mode,
        ).pack(anchor="w", pady=(10, 0))

        ttk.Checkbutton(
            outer,
            text="监控左侧会话列表：发现新的 tickled m 后打开并随机回复",
            variable=self.sidebar_mode,
        ).pack(anchor="w", pady=(4, 0))

        ttk.Checkbutton(
            outer,
            text="检测后自动发送到当前打开的微信会话",
            variable=self.auto_send,
        ).pack(anchor="w", pady=(4, 4))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(6, 8))
        self.start_button = ttk.Button(buttons, text="开始监控", command=self.toggle)
        self.start_button.pack(side="left")
        ttk.Button(buttons, text="单次 OCR 测试", command=self.test_once).pack(
            side="left", padx=8
        )
        ttk.Button(buttons, text="测试随机结果", command=self.test_reply).pack(
            side="left"
        )

        ttk.Label(outer, text="最近一次 OCR（只显示当前聊天区）").pack(
            anchor="w", pady=(6, 4)
        )
        self.ocr_preview = scrolledtext.ScrolledText(
            outer, height=6, wrap="word", state="disabled"
        )
        self.ocr_preview.pack(fill="both", expand=True)

        ttk.Label(outer, text="运行日志").pack(anchor="w", pady=(10, 4))
        self.log_box = scrolledtext.ScrolledText(
            outer, height=8, wrap="word", state="disabled"
        )
        self.log_box.pack(fill="both", expand=True)

    def log(self, text):
        stamp = time.strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{stamp}] {text}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def set_preview(self, text):
        self.ocr_preview.configure(state="normal")
        self.ocr_preview.delete("1.0", "end")
        self.ocr_preview.insert("1.0", text or "(没有识别到文字)")
        self.ocr_preview.configure(state="disabled")

    def get_triggers(self):
        return [
            normalize(item)
            for item in self.trigger_entry.get().split(";")
            if normalize(item)
        ]

    def get_replies(self):
        return [
            line.strip()[:12]
            for line in self.replies.get("1.0", "end").splitlines()
            if line.strip()
        ]

    def toggle(self):
        if self.worker and self.worker.is_alive():
            self.stop_event.set()
            self.start_button.configure(text="开始监控")
            self.log("正在停止监控……")
            return

        triggers = self.get_triggers()
        if not triggers:
            messagebox.showwarning("缺少触发词", "请至少填写一个触发词。")
            return
        self.stop_event.clear()
        change_mode = self.any_change_mode.get()
        sidebar_mode = self.sidebar_mode.get()
        self.worker = threading.Thread(
            target=self.monitor_loop,
            args=(triggers, change_mode, sidebar_mode),
            daemon=True,
        )
        self.worker.start()
        self.start_button.configure(text="停止监控")
        self.log("监控已启动；首次扫描只保存当前画面，不会发送。")

    def test_once(self):
        threading.Thread(target=self.single_scan, daemon=True).start()

    def single_scan(self):
        try:
            hwnd = find_wechat_window()
            if not hwnd:
                raise RuntimeError("未找到微信主窗口，请先打开 Weixin。")
            _, sidebar_image, rect, _ = capture_wechat(hwnd)
            language, text, lines = asyncio.run(recognize_capture())
            _, sidebar_text, sidebar_lines = asyncio.run(
                recognize_image(SIDEBAR_CAPTURE_PATH)
            )
            matches = matching_lines(lines, self.get_triggers())
            sidebar_matches = matching_lines(
                sidebar_lines, self.get_triggers(), sidebar_image
            )
            preview = (
                "【当前聊天区】\n"
                f"{text or '(没有识别到文字)'}\n\n"
                "【左侧会话列表】\n"
                f"{sidebar_text or '(没有识别到文字)'}"
            )
            self.events.put(
                (
                    "scan",
                    language,
                    preview,
                    len(matches),
                    len(sidebar_matches),
                    rect,
                )
            )
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def monitor_loop(self, triggers, change_mode, sidebar_mode):
        seen = set()
        sidebar_seen = set()
        sidebar_times = {}
        previous_sidebar_rows = set()
        last_sidebar_trigger_at = {}
        baseline_ready = False
        cooldown_until = 0.0
        previous_visual = None
        while not self.stop_event.is_set():
            try:
                hwnd = find_wechat_window()
                if not hwnd:
                    self.events.put(("status", "状态：未找到微信主窗口"))
                    self.stop_event.wait(2.0)
                    continue

                chat_image, sidebar_image, rect, layout = capture_wechat(hwnd)
                visual = chat_image.convert("L").resize((160, 120))
                language, text, lines = asyncio.run(recognize_capture())
                matches = matching_lines(lines, triggers)
                keys = {item[0] for item in matches}
                _, sidebar_text, sidebar_lines = asyncio.run(
                    recognize_image(SIDEBAR_CAPTURE_PATH)
                )
                sidebar_matches = matching_lines(
                    sidebar_lines, triggers, sidebar_image
                )
                sidebar_keys = {item[0] for item in sidebar_matches}
                current_sidebar_rows = {item[5] for item in sidebar_matches}
                preview = (
                    "【当前聊天区】\n"
                    f"{text or '(没有识别到文字)'}\n\n"
                    "【左侧会话列表】\n"
                    f"{sidebar_text or '(没有识别到文字)'}"
                )
                self.events.put(
                    (
                        "scan",
                        language,
                        preview,
                        len(matches),
                        len(sidebar_matches),
                        rect,
                    )
                )

                if not baseline_ready:
                    seen.update(keys)
                    sidebar_seen.update(sidebar_keys)
                    for item in sidebar_matches:
                        if item[4]:
                            sidebar_times[item[5]] = item[4]
                    previous_sidebar_rows = current_sidebar_rows
                    previous_visual = visual
                    baseline_ready = True
                    self.events.put(
                        (
                            "log",
                            "已保存当前聊天和左侧会话列表基线；现在等待新的变化。",
                        )
                    )
                else:
                    difference = ImageChops.difference(previous_visual, visual)
                    histogram = difference.histogram()
                    changed_ratio = sum(histogram[18:]) / max(1, sum(histogram))

                    new_sidebar_matches = []
                    current_clock = time.strftime("%H:%M")
                    for item in sidebar_matches:
                        row_id = item[5]
                        display_time = item[4]
                        previous_time = sidebar_times.get(row_id, "")
                        appeared_again = row_id not in previous_sidebar_rows
                        time_changed = (
                            bool(display_time)
                            and bool(previous_time)
                            and display_time != previous_time
                        )
                        row_state_changed_now = (
                            item[0] not in sidebar_seen
                            and display_time == current_clock
                        )
                        recently_triggered = (
                            time.monotonic()
                            - last_sidebar_trigger_at.get(row_id, 0.0)
                            < 2.5
                        )
                        if (
                            appeared_again
                            or time_changed
                            or row_state_changed_now
                        ) and not recently_triggered:
                            new_sidebar_matches.append(item)

                    if sidebar_mode and new_sidebar_matches:
                        # 新会话通常会移动到列表顶部；选择最靠上的新匹配项。
                        newest = min(new_sidebar_matches, key=lambda item: item[2])
                        last_sidebar_trigger_at[newest[5]] = time.monotonic()
                        sidebar_seen.update(sidebar_keys)
                        seen.update(keys)
                        previous_visual = visual
                        row_center = (newest[2] + newest[3]) / 2
                        already_selected = sidebar_row_is_selected(
                            sidebar_image, newest[2], newest[3]
                        )
                        if not already_selected:
                            self.open_sidebar_conversation(
                                hwnd, rect, layout, row_center
                            )
                        observed_time = newest[4] or "-"
                        detected_at = record_tickle_event(
                            newest[5], newest[1], observed_time
                        )
                        self.events.put(
                            (
                                "trigger",
                                f"左侧列表发现「{newest[1]}」"
                                f"｜拍拍时间 {observed_time}"
                                f"｜检测时间 {detected_at}"
                                f"｜{'目标已打开，跳过点击' if already_selected else '已打开目标会话'}",
                                hwnd,
                                rect,
                                {"mode": "action", "row_id": newest[5]},
                            )
                        )
                    elif time.time() < cooldown_until:
                        seen.update(keys)
                        sidebar_seen.update(sidebar_keys)
                        previous_visual = visual
                    else:
                        if change_mode and changed_ratio >= 0.0015:
                            seen.update(keys)
                            sidebar_seen.update(sidebar_keys)
                            previous_visual = visual
                            cooldown_until = time.time() + 8.0
                            self.events.put(
                                (
                                    "trigger",
                                    f"聊天区域发生变化（{changed_ratio:.2%}）",
                                    hwnd,
                                    rect,
                                    "",
                                )
                            )
                        elif not change_mode and not sidebar_mode:
                            new_matches = [
                                item for item in matches if item[0] not in seen
                            ]
                            if new_matches:
                                newest = max(new_matches, key=lambda item: item[2])
                                seen.update(keys)
                                sidebar_seen.update(sidebar_keys)
                                previous_visual = visual
                                cooldown_until = time.time() + 15.0
                                self.events.put(
                                    ("trigger", newest[1], hwnd, rect, None)
                                )
                            else:
                                previous_visual = visual
                        else:
                            sidebar_seen.update(sidebar_keys)
                            previous_visual = visual

                    for item in sidebar_matches:
                        if item[4]:
                            sidebar_times[item[5]] = item[4]
                    previous_sidebar_rows = current_sidebar_rows

                # 控制集合大小；只保留当前可见项和最近记录。
                if len(seen) > 200:
                    seen = set(list(seen)[-100:]) | keys
            except Exception as exc:
                self.events.put(("error", str(exc)))

            self.stop_event.wait(1.4)

        self.events.put(("stopped",))

    def process_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "status":
                    self.status.set(event[1])
                elif kind == "scan":
                    _, language, text, count, sidebar_count, rect = event
                    self.last_window_rect = rect
                    self.status.set(
                        "状态：已连接微信"
                        f"｜OCR {language}"
                        f"｜聊天触发 {count} 条"
                        f"｜左栏触发 {sidebar_count} 条"
                    )
                    self.set_preview(text)
                elif kind == "log":
                    self.log(event[1])
                elif kind == "error":
                    self.status.set("状态：检测出错")
                    self.log(f"错误：{event[1]}")
                elif kind == "trigger":
                    _, detected_text, hwnd, rect, forced_reply = event
                    self.log(f"检测到新事件：「{detected_text}」")
                    self.handle_trigger(hwnd, rect, forced_reply)
                elif kind == "stopped":
                    self.start_button.configure(text="开始监控")
                    self.log("监控已停止。")
        except queue.Empty:
            pass
        self.root.after(100, self.process_events)

    def handle_trigger(self, hwnd, rect, forced_reply=None):
        action_name = "随机短句"
        if isinstance(forced_reply, dict) and forced_reply.get("mode") == "action":
            reply, action_name = self.choose_random_action(
                forced_reply.get("row_id", "unknown")
            )
        else:
            replies = self.get_replies()
            reply = forced_reply or (
                random.choice(replies) if replies else "You tickled me."
            )
        reply = reply[:12]
        self.log(f"随机行为：{action_name}｜内容：「{reply}」")
        if not self.auto_send.get():
            self.log(f"观察模式：本来会发送「{reply}」")
            return

        if not self.confirmed_once and forced_reply is None:
            confirmed = messagebox.askyesno(
                "首次发送确认",
                "程序将点击当前微信输入框并发送：\n\n"
                f"{reply}\n\n"
                "请确认当前聊天对象正确。继续吗？",
            )
            if not confirmed:
                self.auto_send.set(False)
                self.log("已取消发送并切回观察模式。")
                return
            self.confirmed_once = True

        try:
            self.send_to_wechat(hwnd, rect, reply)
            self.log(f"已发送：「{reply}」")
        except Exception as exc:
            self.auto_send.set(False)
            self.log(f"发送失败并已关闭自动发送：{exc}")

    def choose_random_action(self, row_id):
        now = time.time()
        counts = self.tickle_state["counts"]
        streaks = self.tickle_state["streaks"]
        last_seen = self.tickle_state["last_seen"]

        count = int(counts.get(row_id, 0)) + 1
        previous = float(last_seen.get(row_id, 0.0))
        streak = int(streaks.get(row_id, 0)) + 1 if now - previous <= 20 else 1
        counts[row_id] = count
        streaks[row_id] = streak
        last_seen[row_id] = now
        save_tickle_state(self.tickle_state)

        roll = random.random()
        if roll < 0.55:
            replies = self.get_replies()
            return (
                random.choice(replies) if replies else "你把我拍醒了",
                "抽象短句",
            )
        if roll < 0.72:
            return f"这是第{count}次拍我", "计数器"
        if roll < 0.85:
            if streak >= 2:
                return f"{streak}连拍，暴击！", "连击系统"
            return "连击蓄力中", "连击系统"
        if roll < 0.95:
            return random.choice(SYSTEM_REPLIES), "假装系统消息"
        return random.choice(RED_PACKET_REPLIES), "红包彩蛋"

    def open_sidebar_conversation(self, hwnd, rect, layout, row_center):
        left, top, _, _ = rect
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
            time.sleep(0.3)
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 0x0002, 0)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.25)

        x = int(left + (layout["sidebar_left"] + layout["divider"]) / 2)
        y = int(top + layout["sidebar_top"] + row_center)
        user32.SetCursorPos(x, y)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.8)

    def send_to_wechat(self, hwnd, rect, reply):
        left, top, right, bottom = rect
        width = right - left
        height = bottom - top
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
            time.sleep(0.3)
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 0x0002, 0)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.25)

        # 点击当前聊天底部输入框的空白区域。
        x = int(left + width * 0.70)
        y = int(top + height * 0.88)
        user32.SetCursorPos(x, y)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.15)

        user32.keybd_event(0x11, 0, 0, 0)
        user32.keybd_event(0x41, 0, 0, 0)
        user32.keybd_event(0x41, 0, 0x0002, 0)
        user32.keybd_event(0x11, 0, 0x0002, 0)
        self.root.clipboard_clear()
        self.root.clipboard_append(reply)
        self.root.update()

        user32.keybd_event(0x11, 0, 0, 0)  # Ctrl down
        user32.keybd_event(0x56, 0, 0, 0)  # V down
        user32.keybd_event(0x56, 0, 0x0002, 0)
        user32.keybd_event(0x11, 0, 0x0002, 0)
        time.sleep(0.20)

        # 点击 Send，比依赖用户的 Enter/Ctrl+Enter 发送设置更稳定。
        send_x = int(right - 37)
        send_y = int(bottom - 38)
        user32.SetCursorPos(send_x, send_y)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)

    def test_reply(self):
        replies = self.get_replies()
        self.log(f"随机结果：「{random.choice(replies) if replies else 'You tickled me.'}」")

    def close(self):
        self.stop_event.set()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        App().run()
    except Exception as exc:
        try:
            messagebox.showerror("启动失败", str(exc))
        except Exception:
            pass
        raise
