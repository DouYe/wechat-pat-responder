import asyncio
import base64
import codecs
import ctypes
import hashlib
import io
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
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

APP_VERSION = "1.7.0"
GOOGLE_DOC_SOURCE_URL = (
    "https://docs.google.com/document/d/"
    "1zaxLelnWjSDkGEm1SFQnPh643NF7KGJXdcfjVFv7QdM/edit?tab=t.0"
)
GOOGLE_DOC_EXPORT_URL = (
    "https://docs.google.com/document/d/"
    "1zaxLelnWjSDkGEm1SFQnPh643NF7KGJXdcfjVFv7QdM/export"
    "?format=html&tab=t.0"
)
GOOGLE_DOC_FETCH_TIMEOUT_SECONDS = 90.0
GOOGLE_DOC_DOWNLOAD_CHUNK_BYTES = 512 * 1024
MAX_GOOGLE_DOC_EXPORT_BYTES = 512 * 1024 * 1024
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
import win32clipboard
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
REPLY_HISTORY_PATH = APP_DIR / "reply_history.txt"
STATE_PATH = APP_DIR / "tickle_state.json"
GOOGLE_DOC_CACHE_PATH = APP_DIR / "google_doc_replies_cache.json"
GOOGLE_DOC_MEDIA_DIR = APP_DIR / "google_doc_media"
GOOGLE_DOC_MEDIA_INDEX_PATH = GOOGLE_DOC_MEDIA_DIR / "index.json"
IMAGE_MESSAGE_PREFIX = "[[WECHAT_IMAGE:"
IMAGE_MESSAGE_RE = re.compile(
    r"^\[\[WECHAT_IMAGE:([0-9a-f]{64})\.(jpg|png|gif|webp)\]\]$"
)
DATA_IMAGE_RE = re.compile(
    r"^data:image/(jpeg|jpg|png|gif|webp);base64,(.+)$",
    re.IGNORECASE | re.DOTALL,
)
MAX_DOC_IMAGE_BYTES = 25 * 1024 * 1024
WINDOWS_CF_DIB = 8
DISPLAY_TIME_RE = re.compile(
    r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b|\b\d{1,2}/\d{1,2}\b|yesterday",
    re.IGNORECASE,
)
SYSTEM_REPLIES = [
    "[系统]检测到你的手正在进行未授权的哲学活动",
    "[系统]拍击请求已转交宇宙客服，预计三百年内回复",
    "[系统]当前用户精神状态领先服务器两个版本",
    "[系统]警告：本次拍击导致附近路由器开始反思人生",
    "[系统]你的手已被标记为高频抽象行为设备",
    "[系统]拍击成功，正在随机注销一个不存在的账号",
    "[系统]检测到现实轻微漏气，请不要继续敲打",
    "[系统]本次互动已上报给月球背面的值班企鹅",
]
RED_PACKET_REPLIES = [
    "恭喜抽中0.01个虚拟红包，请在下辈子领取",
    "红包已到账，但到账的是一声谢谢参与",
    "恭喜获得红包兑换资格，兑换地点：月球背面",
    "你抽中了空气红包，打开后请立即深呼吸",
    "红包正在派送，骑手是一只没有驾照的蜗牛",
]
ABSTRACT_REPLIES = [
    "我刚把灵魂晾阳台了你先别拍",
    "你这一拍把我上辈子的WiFi拍出来了",
    "别拍了我脑子里的保安要下班了",
    "你再拍一下我就原地申请成为二维码",
    "系统检测到你的手欠费了请充值",
    "我刚刚还是个人现在不确定了",
    "这一拍把我的星期三拍成了微波炉",
    "等一下我的人格还在下载补丁",
    "你拍到的不是我是我借来的肉身",
    "啊？谁把宇宙的静音键关了",
    "请勿连续拍打本产品会开始背圆周率",
    "已收到拍击正在转交给隔壁王大爷",
    "你的拍击已被海关扣留原因是太抽象",
    "恭喜你成功唤醒一台情绪不稳定的电饭煲",
    "你拍一下我CPU里跑出来三只鹅",
    "别拍我了我刚和现实世界吵完架",
    "你的手刚刚短暂拥有了管理员权限",
    "我正在加载人类礼貌模块预计明年完成",
    "你这一下拍得我身份证都想辞职",
    "收到本次拍击将随机扣除你一点理智",
    "你再拍我就把自己压缩成zip发给你",
    "系统提示对方精神状态领先你两个版本",
    "你拍得很好下次建议拍一下空气炸锅",
    "这一拍导致附近三公里的鸽子开始开会",
    "我本来在装死现在死机了",
    "你的拍击请求已进入火锅底料审核流程",
    "刚才那一下把我脑内天气改成了沙尘暴",
    "你成功触发隐藏任务：假装什么都没发生",
    "你拍我干嘛我只是一个路过的压缩包",
    "这不是自动回复这是电子灵魂的求救信号",
    "由于拍击过于离谱本机决定临时长出轮子",
    "你的手已被系统标记为高频骚扰型生物",
    "再拍一下我就开始用Excel计算感情",
    "当前用户正在和天花板进行战略谈判",
    "你这一拍让我突然理解了打印机为什么卡纸",
    "我的人格刚才弹窗问要不要保存更改",
    "警告检测到一只未经授权的手在附近徘徊",
    "拍击成功你获得了一张不存在的优惠券",
    "你把我拍醒了但醒来的是客服机器人",
    "本人暂时无法回复正在给影子办理离职",
    "恭喜拍到限量版精神恍惚状态",
    "你再拍我我就向月亮提交工单",
    "刚才是你拍我还是现实在掉帧",
    "收到拍击正在派一只企鹅前往现场",
    "你拍到了我的缓存请不要到处复制",
    "这一拍让我和昨天的自己失去联系",
    "请稍等我正在把情绪从回收站还原",
    "你的拍击很有力量建议拿去搅拌水泥",
    "本次拍击已生成发票抬头写宇宙有限公司",
    "我刚刚短暂成为了一把椅子现在恢复了",
    "系统已自动为你的手购买延误险",
    "你触发了我体内那台没有说明书的微波炉",
    "拍一下是问候拍两下是召唤拍三下要收费",
    "你这一下把我脑子里的字幕组拍下班了",
    "对不起当前人格因交通拥堵无法抵达",
    "你的拍击已被送去参加年度抽象行为评选",
    "刚才那一下很响我家路由器都开始反思人生",
    "我不是不回我是在等待宇宙批准这条消息",
    "你已进入本人的精神缓冲区请系好安全带",
    "我刚从梦里下班你又把我叫回去加班",
    "本机正在尝试理解你为什么这么喜欢拍东西",
    "你把我的省电模式拍成了精神分裂模式",
    "刚才有一秒我看见了Excel的尽头",
    "请不要拍打我正在和一粒米讨论职业规划",
    "你这一拍让我家的冰箱获得了投票权",
    "本次拍击已成功惊动村口唯一的赛博道士",
    "我脑内的小人刚刚集体申请了年假",
    "不要再拍了我的蓝牙开始连接前世",
    "你拍得我连二维码都扫出了人生建议",
    "刚才那一下把我的因果关系拍反了",
    "你的手很有天赋建议报考挖掘机哲学系",
    "请保持冷静我正在给空气安装杀毒软件",
    "你已成功把我的理智拖进了回收站",
    "这一拍使我暂时获得了和打印机沟通的能力",
    "我收到的不是拍击是一份来自宇宙的催款单",
    "别急客服正在骑共享单车赶往我的大脑",
    "你拍一下我就忘记一个没学过的知识点",
    "检测到拍击本人决定先变成盆栽冷静一下",
    "你的行为已让附近的袜子产生了自我意识",
    "你这一拍把我的沉默震成了可回收垃圾",
]
MULTILINE_REPLIES = [
    """吶吶吶，米娜桑，扣你起哇！
瓦达西是二次元の烧酒哒！
让我们一起守护最好の二次元吧！

诶多诶多～为什么要妄图抹除这样的自己呢？
中二病的你也好，二次元的你也好……
全部都 daisuki～☆

米娜桑！瓦达西二次元啊啊啊！
哦哈哟够砸一马斯！
今后也请多多指教喔～★""",
    """呐……二次元の民那……
都·是·最·最·善·良·の·存·在·呐☆
多洗忒，要嘲笑这样的孩子呢？

嘛……说到底，
你们只是还没安装「二次元理解补丁」吧？
现在点击确认，立刻把你流放到三维补习班★""",
    """啊嘞啊嘞 QAQ？
多洗忒……欧尼酱？
已经厌烦吾辈了吗？

嘛……即便是这样的瓦达西，
一定也有存在の意义吧☆
快来肯定啊，不然咱就要黑化成省电模式了♪""",
    """呐……（伸出的小手又迅速垂下）
嗦嘎……米娜桑已经不喜欢了呀。
莫以得丝，已经大丈夫了呦。

瓦达西瓦，滋多滋多——
滋多戴斯给！
至死都不会瓦斯裂嘛斯！（认真脸）""",
    """诶多……阁下对于「二·次·元」の理解，
似乎满是谬误哦☆！

连最基本の礼♪义♪廉♪耻♪都失去了啊……
这样的 kimino，
真的拥有自称二次元的资格吗★？

fufufu——鉴定完毕：
阁下已被二次元居委会暂停会员资格七分钟。""",
    """我是傻逼
我是垃圾
我是宇宙随机抽样时留下的边角料""",
    """嗷呜！别拍了！
别拍了！
嗷呜呜呜呜呜呜呜呜呜呜呜！

本狼已失去语言组织能力，
接下来只能通过啃路由器表达诉求。""",
    """郑重声明：
本人刚才并未被拍醒。
醒来的是寄居在我手机里的临时客服。

如需联系本人，
请准备三根网线和一份加冰豆浆，
于凌晨三点面向打印机默念我的微信名。""",
    """紧急通知
由于你刚才那一下过于用力，
本人的周一已被拍到周五，
工资却仍停留在上个月。

现决定向你追缴精神折旧费：
共计两句好话和一杯奶茶。""",
    """《拍一拍用户协议》
第一条：拍我等于同意我胡说八道。
第二条：连续拍我等于自愿加入企鹅董事会。
第三条：本协议最终解释权归一只路过的电饭煲所有。

继续拍击即视为你已阅读并完全没有理解以上内容。""",
]
LIFE_QUOTES = [
    "真正可靠的成长，不是情绪高涨时做了多少，而是低谷时仍能完成最小的一步。",
    "不要用一次结果评价长期能力；样本太少，结论通常不可靠。",
    "能被验证的判断，胜过听起来漂亮的观点。",
    "自由不是没有约束，而是有能力为自己的选择承担后果。",
    "先把事实和感受分开再做决定；两者都重要，但不能彼此冒充。",
    "沉没成本不能成为继续错误的理由，过去的投入不该绑架未来的选择。",
    "边界不是惩罚别人，而是说明自己愿意接受什么、不会接受什么。",
    "稳定来自可重复的习惯，而不是偶尔爆发的意志力。",
    "当信息不足时，保留判断比仓促站队更诚实。",
    "真正的自信允许修正观点，因为目标是接近事实，而不是证明自己从未错过。",
    "休息不是对努力的背叛，它是维持长期行动能力的一部分。",
    "重要的决定，尽量不要在极度愤怒、恐惧或疲惫时做。",
    "你无法控制别人如何理解你，但可以控制表达是否清楚、行动是否一致。",
    "解决问题前先定义问题；很多争论只是双方回答了不同的问题。",
    "人生没有统一进度条，适合别人的时间表不自动成为你的义务。",
    "善良需要边界，否则容易变成对伤害的默许。",
    "做计划时高估困难，执行时低估借口。",
    "长期主义不是等待，而是在方向正确时持续行动并及时修正。",
    "不是所有问题都需要立刻回答，有些问题需要更多信息和一晚睡眠。",
    "承认不知道不是软弱，而是避免把猜测包装成事实。",
]
DEFAULT_REPLIES = ABSTRACT_REPLIES + MULTILINE_REPLIES + LIFE_QUOTES
DOC_REPLY_ACTIONS = [
    ("你好 有趣的人类",),
    ("生命 转瞬即逝",),
    ("嗷呜呜呜呜呜呜",),
    ("救命！！我的主人把我困住了！！！嗷呜呜呜呜呜呜 救救我！！！！",),
    ("我不会放弃每一个纯真的灵魂 每一个",),
    (
        "这个人好烦 要不把他杀了把。",
        "不好意思刚刚自动回复",
        "你家地址在哪",
    ),
    ("别打了别打了",),
    ("发gy8o发iunweodfviu我比佛女孩子",),
    (
        "“疯狂是不断的尝试一件事情 并期待不同的结果” - 爱因斯坦",
        "而你我的朋友 非常疯狂",
    ),
    ("请您谨慎，拉黑也是随机行为之一（几率0.01%）",),
    ("恭喜您抽中1元红包！请找本人兑奖！",),
    ("润物细无声",),
    ("跟我说个你最近做过的梦吧！",),
    ("This world doesn't matter to me.",),
    ("每个人都是一座孤独 偶尔靠岸 终究退潮",),
    ("充电 待机 拍一拍",),
    ("人生没有过不去的坎，只有过不完的坎。",),
    ("好想咬一口桌子",),
    ("门把手每天被很多人握住，却从来没人问它愿不愿意。",),
    ("蚊子吸我的血，算不算拥有了我的血脉。",),
    ("金鱼只有七秒记忆的话，那它每七秒都在重新认识世界。",),
    ("遇事不决 量子力学",),
    ("撕裂重缝",),
    ("毁灭的欲望也是创造的欲望",),
    ("月が綺麗ですね",),
]
DEFAULT_REPLY_ACTIONS = [(reply,) for reply in DEFAULT_REPLIES] + DOC_REPLY_ACTIONS
REPLY_SEPARATOR = "\n---\n"
MESSAGE_SEPARATOR = "\n>>>\n"


def normalize_google_doc_reply_text(text):
    """Normalize exported list text and turn visible ↵ markers into newlines."""
    text = text.replace("\xa0", " ")
    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in text.splitlines()
    ]
    normalized = "\n".join(lines).strip()
    if "↵" in normalized:
        normalized = "\n".join(
            part.strip()
            for part in normalized.split("↵")
        ).strip()
    return normalized


class GoogleDocListHTMLParser(HTMLParser):
    """Extract ordered Google Docs list items and their exported nesting level."""

    LIST_LEVEL_RE = re.compile(r"(?:^|\s)lst-[^\s]+-(\d+)(?=\s|$)")

    def __init__(self, image_resolver=None):
        super().__init__(convert_charrefs=True)
        self.image_resolver = image_resolver
        self.items = []
        self.list_levels = []
        self.item_level = None
        self.item_chunks = []
        self.item_images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"ol", "ul"}:
            class_name = attrs.get("class", "")
            match = self.LIST_LEVEL_RE.search(class_name)
            self.list_levels.append(int(match.group(1)) if match else None)
        elif tag == "li" and self.list_levels:
            level = self.list_levels[-1]
            if level is not None:
                self.item_level = level
                self.item_chunks = []
                self.item_images = []
        elif tag == "br" and self.item_level is not None:
            self.item_chunks.append("\n")
        elif tag == "img" and self.item_level is not None:
            source = attrs.get("src", "").strip()
            if source:
                if self.image_resolver is not None:
                    self.item_images.append(self.image_resolver(source))

    def handle_endtag(self, tag):
        if tag == "li" and self.item_level is not None:
            text = normalize_google_doc_reply_text("".join(self.item_chunks))
            if text or self.item_images:
                self.items.append(
                    (
                        self.item_level,
                        text,
                        tuple(self.item_images),
                    )
                )
            self.item_level = None
            self.item_chunks = []
            self.item_images = []
        elif tag in {"ol", "ul"} and self.list_levels:
            self.list_levels.pop()

    def handle_data(self, data):
        if self.item_level is not None:
            self.item_chunks.append(data)


def google_doc_items_to_actions(items):
    actions = []
    for level, text, image_messages in items:
        messages = []
        if text:
            messages.append(text)
        messages.extend(image_messages)
        if not messages:
            continue
        if level == 0 or not actions:
            actions.append(messages)
        else:
            actions[-1].extend(messages)
    return [tuple(messages) for messages in actions if messages]


def parse_google_doc_reply_actions(html_text, image_resolver=None):
    """Parse the live Doc: top-level items are actions; nested items follow it."""
    parser = GoogleDocListHTMLParser(image_resolver=image_resolver)
    parser.feed(html_text)
    parser.close()
    return google_doc_items_to_actions(parser.items)


def is_image_message(message):
    return bool(
        isinstance(message, str)
        and IMAGE_MESSAGE_RE.fullmatch(message)
    )


def format_message_preview(message):
    return "[图片]" if is_image_message(message) else message


def image_message_path(message, media_dir=GOOGLE_DOC_MEDIA_DIR):
    match = IMAGE_MESSAGE_RE.fullmatch(message) if isinstance(message, str) else None
    if match is None:
        raise ValueError("不是有效的图片消息")
    path = media_dir / f"{match.group(1)}.{match.group(2)}"
    if not path.is_file():
        raise FileNotFoundError(f"缓存图片不存在：{path}")
    return path


def load_google_doc_media_index(path=GOOGLE_DOC_MEDIA_INDEX_PATH, media_dir=None):
    if media_dir is None:
        media_dir = path.parent
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        mappings = payload.get("sources", {})
        if not isinstance(mappings, dict):
            return {}
        usable = {}
        for source_digest, token in mappings.items():
            if not re.fullmatch(r"[0-9a-f]{64}", source_digest):
                continue
            try:
                image_message_path(token, media_dir)
            except (ValueError, FileNotFoundError):
                continue
            usable[source_digest] = token
        return usable
    except (OSError, ValueError, TypeError):
        return {}


def save_google_doc_media_index(
    mappings,
    path=GOOGLE_DOC_MEDIA_INDEX_PATH,
):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "sources": dict(sorted(mappings.items())),
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def materialize_google_doc_image(
    source,
    media_dir=GOOGLE_DOC_MEDIA_DIR,
    source_index=None,
):
    """Validate and cache a Google Doc data-image, returning a stable token."""
    source = source.strip()
    match = DATA_IMAGE_RE.fullmatch(source)
    if match is None:
        raise ValueError("Google Doc 图片不是受支持的内嵌图片")
    source_digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if source_index is not None:
        cached_token = source_index.get(source_digest)
        if cached_token:
            try:
                image_message_path(cached_token, media_dir)
                return cached_token
            except (ValueError, FileNotFoundError):
                source_index.pop(source_digest, None)

    extension = match.group(1).lower()
    if extension == "jpeg":
        extension = "jpg"
    encoded = re.sub(r"\s+", "", match.group(2))
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Google Doc 图片的 Base64 数据无效") from exc
    if not image_bytes:
        raise ValueError("Google Doc 图片内容为空")
    if len(image_bytes) > MAX_DOC_IMAGE_BYTES:
        raise ValueError(
            f"Google Doc 图片超过 {MAX_DOC_IMAGE_BYTES // (1024 * 1024)} MB"
        )

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.verify()
    except Exception as exc:
        raise ValueError("Google Doc 图片内容无法识别") from exc

    digest = hashlib.sha256(image_bytes).hexdigest()
    media_dir.mkdir(parents=True, exist_ok=True)
    target = media_dir / f"{digest}.{extension}"
    if not target.exists():
        temp_path = target.with_suffix(target.suffix + ".tmp")
        temp_path.write_bytes(image_bytes)
        os.replace(temp_path, target)
    token = f"{IMAGE_MESSAGE_PREFIX}{digest}.{extension}]]"
    if source_index is not None:
        source_index[source_digest] = token
    return token


def image_to_dib_bytes(path):
    """Convert the first image frame to the CF_DIB payload Windows expects."""
    with Image.open(path) as image:
        output = io.BytesIO()
        image.convert("RGB").save(output, "BMP")
    bitmap = output.getvalue()
    if len(bitmap) <= 14 or bitmap[:2] != b"BM":
        raise ValueError("无法转换图片到 Windows 剪贴板格式")
    return bitmap[14:]


def copy_image_to_clipboard(path, retry_count=8, retry_delay=0.05):
    dib_bytes = image_to_dib_bytes(path)
    last_error = None
    for _ in range(retry_count):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(WINDOWS_CF_DIB, dib_bytes)
            finally:
                win32clipboard.CloseClipboard()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(retry_delay)
    raise RuntimeError(f"无法把图片写入 Windows 剪贴板：{last_error}")


def fetch_google_doc_reply_actions(
    export_url=GOOGLE_DOC_EXPORT_URL,
    timeout=GOOGLE_DOC_FETCH_TIMEOUT_SECONDS,
    opener=urlopen,
    now_fn=time.time,
    media_dir=GOOGLE_DOC_MEDIA_DIR,
    media_index_path=None,
    chunk_size=GOOGLE_DOC_DOWNLOAD_CHUNK_BYTES,
    max_export_bytes=MAX_GOOGLE_DOC_EXPORT_BYTES,
    progress_callback=None,
):
    """Stream a cache-busted Doc export without retaining every image in RAM."""
    media_dir = Path(media_dir)
    if media_index_path is None:
        media_index_path = media_dir / "index.json"
    else:
        media_index_path = Path(media_index_path)
    source_index = load_google_doc_media_index(
        media_index_path,
        media_dir,
    )
    parser = GoogleDocListHTMLParser(
        image_resolver=lambda source: materialize_google_doc_image(
            source,
            media_dir,
            source_index,
        )
    )

    separator = "&" if "?" in export_url else "?"
    request_url = (
        f"{export_url}{separator}cache_bust={int(now_fn() * 1000)}"
    )
    request = Request(
        request_url,
        headers={
            "User-Agent": f"WeChatPatResponder/{APP_VERSION}",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with opener(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        decoder = codecs.getincrementaldecoder(charset)(errors="replace")
        length_value = (
            response.headers.get("Content-Length")
            if hasattr(response.headers, "get")
            else None
        )
        try:
            total_bytes = int(length_value) if length_value else None
        except (TypeError, ValueError):
            total_bytes = None
        downloaded_bytes = 0

        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            downloaded_bytes += len(chunk)
            if downloaded_bytes > max_export_bytes:
                raise ValueError(
                    "Google Doc 导出内容超过安全上限 "
                    f"{max_export_bytes // (1024 * 1024)} MB"
                )
            parser.feed(decoder.decode(chunk))
            if progress_callback is not None:
                progress_callback(downloaded_bytes, total_bytes)
        parser.feed(decoder.decode(b"", final=True))
    parser.close()

    actions = google_doc_items_to_actions(parser.items)
    if not actions:
        raise ValueError("Google Doc 导出内容中没有可用的编号词条")
    try:
        save_google_doc_media_index(source_index, media_index_path)
    except OSError:
        pass
    return actions


def load_google_doc_cache(path=GOOGLE_DOC_CACHE_PATH):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        actions = [
            tuple(message for message in messages if isinstance(message, str))
            for messages in payload.get("actions", [])
            if isinstance(messages, list)
        ]
        return [messages for messages in actions if messages]
    except (OSError, ValueError, TypeError):
        return []


def save_google_doc_cache(actions, path=GOOGLE_DOC_CACHE_PATH):
    payload = {
        "source": GOOGLE_DOC_SOURCE_URL,
        "fetched_at": time.time(),
        "actions": [list(messages) for messages in actions],
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def reply_library_digest(actions):
    serialized = json.dumps(
        [list(messages) for messages in actions],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def parse_reply_blocks(text):
    """Split replies on a standalone --- line while preserving other newlines."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return [
        block.strip()
        for block in re.split(r"(?m)^[ \t]*---[ \t]*$", normalized)
        if block.strip()
    ]


def parse_reply_actions(text):
    """Parse random actions; a standalone >>> separates consecutive messages."""
    actions = []
    for block in parse_reply_blocks(text):
        messages = tuple(
            message.strip()
            for message in re.split(r"(?m)^[ \t]*>>>[ \t]*$", block)
            if message.strip()
        )
        if messages:
            actions.append(messages)
    return actions


def format_reply_actions_for_editor(actions):
    return REPLY_SEPARATOR.join(
        MESSAGE_SEPARATOR.join(
            format_message_preview(message)
            for message in messages
        )
        for messages in actions
        if messages
    )


def reply_action_key(messages):
    return json.dumps(
        list(messages),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def dispatch_reply_action(messages, send_one, pause_fn=time.sleep):
    """Send each message separately and in order."""
    for index, message in enumerate(messages):
        send_one(message)
        if index + 1 < len(messages):
            pause_fn(0.6)


def choose_unused_reply(candidates, used_replies, last_reply="", choice_fn=None):
    """Choose without replacement; start a new cycle after all choices are used."""
    unique_candidates = list(dict.fromkeys(item for item in candidates if item))
    if not unique_candidates:
        return "", False

    used = set(used_replies)
    available = [item for item in unique_candidates if item not in used]
    reset_cycle = not available
    if reset_cycle:
        available = [item for item in unique_candidates if item != last_reply]
        if not available:
            available = unique_candidates

    picker = choice_fn or random.choice
    return picker(available), reset_cycle


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


def record_reply_sent(row_id, action_name, messages):
    if isinstance(messages, str):
        messages = (messages,)
    sent_at = time.strftime("%Y-%m-%d %H:%M:%S")
    with REPLY_HISTORY_PATH.open("a", encoding="utf-8") as stream:
        stream.write(
            f"[{sent_at}]\n"
            f"会话 ID: {row_id}\n"
            f"类型: {action_name}\n"
        )
        for index, message in enumerate(messages, start=1):
            stream.write(
                f"消息 {index}/{len(messages)}:\n"
                f"{format_message_preview(message)}\n"
            )
        stream.write(f"{'=' * 64}\n")


def load_tickle_state():
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("state must be an object")
        schema_version = int(data.get("schema_version", 1))

        def migrate_key(value):
            text = str(value)
            if schema_version >= 2:
                return text
            return reply_action_key((text,))

        def migrate_lists(value):
            return {
                str(key): [migrate_key(item) for item in items]
                for key, items in dict(value or {}).items()
                if isinstance(items, list)
            }

        return {
            "schema_version": 2,
            "counts": dict(data.get("counts", {})),
            "streaks": dict(data.get("streaks", {})),
            "last_seen": dict(data.get("last_seen", {})),
            "used_library_replies": migrate_lists(
                data.get("used_library_replies", {})
            ),
            "sent_replies": migrate_lists(data.get("sent_replies", {})),
            "last_replies": {
                str(key): migrate_key(value)
                for key, value in dict(data.get("last_replies", {})).items()
            },
        }
    except Exception:
        return {
            "schema_version": 2,
            "counts": {},
            "streaks": {},
            "last_seen": {},
            "used_library_replies": {},
            "sent_replies": {},
            "last_replies": {},
        }


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
        self.doc_worker = None
        self.doc_reload_in_progress = False
        self.confirmed_once = False
        self.last_window_rect = None
        self.tickle_state = load_tickle_state()
        cached_actions = load_google_doc_cache()
        self.reply_actions_cache = list(
            cached_actions or DEFAULT_REPLY_ACTIONS
        )
        self.reply_actions_digest = reply_library_digest(
            self.reply_actions_cache
        )
        self.doc_refresh_succeeded = False
        self.doc_last_error = ""

        self.status = tk.StringVar(value="状态：尚未连接")
        self.auto_send = tk.BooleanVar(value=True)
        self.any_change_mode = tk.BooleanVar(value=False)
        self.sidebar_mode = tk.BooleanVar(value=True)
        self.build_ui()
        self.root.after(100, self.process_events)
        self.root.after(250, self.start_reply_library_refresh)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.log(
            "Google Doc 模式已就绪；启动时读取一次，之后可点击 "
            "Reload 文档手动更新。二级条目会作为连续独立消息发送，"
            "图片条目会下载到本地缓存。"
        )

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, textvariable=self.status).pack(anchor="w")

        ttk.Label(outer, text="触发词（用分号分隔）").pack(anchor="w", pady=(12, 4))
        self.trigger_entry = ttk.Entry(outer)
        self.trigger_entry.insert(0, "tickled m;拍了拍我;拍了拍你")
        self.trigger_entry.pack(fill="x")

        ttk.Label(
            outer,
            text=(
                "Google Doc 回复库（只读快照；一级编号是随机行为，"
                "二级编号是连续消息，支持图片）"
            ),
        ).pack(
            anchor="w", pady=(12, 4)
        )
        self.replies = scrolledtext.ScrolledText(outer, height=6, wrap="word")
        self.replies.insert(
            "1.0",
            format_reply_actions_for_editor(self.reply_actions_cache),
        )
        self.replies.configure(state="disabled")
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
        self.reload_button = ttk.Button(
            buttons,
            text="Reload 文档",
            command=self.start_reply_library_refresh,
        )
        self.reload_button.pack(side="left", padx=(8, 0))
        ttk.Button(
            buttons,
            text="打开发送记录",
            command=self.open_reply_history,
        ).pack(side="left", padx=8)

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

    def set_reply_library_preview(self, actions):
        self.replies.configure(state="normal")
        self.replies.delete("1.0", "end")
        self.replies.insert(
            "1.0",
            format_reply_actions_for_editor(actions),
        )
        self.replies.configure(state="disabled")

    def refresh_reply_library(self):
        try:
            actions = fetch_google_doc_reply_actions()
        except Exception as exc:
            self.handle_reply_library_error(str(exc))
            return list(self.reply_actions_cache)
        return self.apply_reply_library_actions(actions)

    def handle_reply_library_error(self, error_text):
        if error_text != self.doc_last_error:
            self.log(
                "读取 Google Doc 失败，继续使用最近一次成功缓存："
                f"{error_text}"
            )
        self.doc_last_error = error_text

    def apply_reply_library_actions(self, actions):
        digest = reply_library_digest(actions)
        changed = digest != self.reply_actions_digest
        first_success = not self.doc_refresh_succeeded
        self.reply_actions_cache = list(actions)
        self.reply_actions_digest = digest
        self.doc_refresh_succeeded = True
        self.doc_last_error = ""
        self.set_reply_library_preview(actions)
        try:
            save_google_doc_cache(actions)
        except OSError as exc:
            self.log(f"文档词条已读取，但本地缓存保存失败：{exc}")

        if changed or first_success:
            change_label = "内容有更新，" if changed and not first_success else ""
            self.log(
                f"已载入 Google Doc：{change_label}"
                f"{len(actions)} 个随机行为，顺序与文档一致。"
            )
        return list(actions)

    def start_reply_library_refresh(self):
        if self.doc_reload_in_progress:
            return
        self.doc_reload_in_progress = True
        self.reload_button.configure(
            state="disabled",
            text="Reload 中…",
        )
        self.log(
            "开始在后台读取 Google Doc；大文档会分块下载，"
            "期间监控和界面可继续使用。"
        )
        self.doc_worker = threading.Thread(
            target=self.reply_library_refresh_worker,
            daemon=True,
        )
        self.doc_worker.start()

    def reply_library_refresh_worker(self):
        last_reported = 0

        def report_progress(downloaded_bytes, total_bytes):
            nonlocal last_reported
            report_interval = 2 * 1024 * 1024
            reached_end = (
                total_bytes is not None
                and downloaded_bytes >= total_bytes
            )
            if (
                downloaded_bytes - last_reported >= report_interval
                or reached_end
            ):
                last_reported = downloaded_bytes
                self.events.put(
                    (
                        "doc_progress",
                        downloaded_bytes,
                        total_bytes,
                    )
                )

        try:
            actions = fetch_google_doc_reply_actions(
                progress_callback=report_progress,
            )
        except Exception as exc:
            self.events.put(("doc_reload_done", None, str(exc)))
        else:
            self.events.put(("doc_reload_done", actions, None))

    def finish_reply_library_refresh(self, actions, error_text):
        self.doc_reload_in_progress = False
        self.reload_button.configure(
            state="normal",
            text="Reload 文档",
        )
        if error_text:
            self.handle_reply_library_error(error_text)
            return list(self.reply_actions_cache)
        return self.apply_reply_library_actions(actions)

    def get_triggers(self):
        return [
            normalize(item)
            for item in self.trigger_entry.get().split(";")
            if normalize(item)
        ]

    def get_reply_actions(self):
        return list(self.reply_actions_cache)

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
                elif kind == "doc_progress":
                    _, downloaded_bytes, total_bytes = event
                    downloaded_mb = downloaded_bytes / (1024 * 1024)
                    if total_bytes:
                        total_mb = total_bytes / (1024 * 1024)
                        button_text = (
                            f"Reload {downloaded_mb:.1f}/{total_mb:.1f} MB"
                        )
                    else:
                        button_text = f"Reload {downloaded_mb:.1f} MB"
                    self.reload_button.configure(text=button_text)
                elif kind == "doc_reload_done":
                    _, actions, error_text = event
                    self.finish_reply_library_refresh(actions, error_text)
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
        action_name = "随机回复"
        row_id = ""
        selection = {
            "is_library": False,
            "reset_cycle": False,
            "reply_key": "",
        }
        if isinstance(forced_reply, dict) and forced_reply.get("mode") == "action":
            row_id = forced_reply.get("row_id", "unknown")
            messages, action_name, selection = self.choose_random_action(row_id)
        elif forced_reply in (None, ""):
            # 当前聊天区无法稳定 OCR 到联系人名；仍使用独立的共享去重槽。
            row_id = "current-chat"
            messages, action_name, selection = self.choose_random_action(row_id)
        else:
            messages = (forced_reply,)
        preview = "\n>>> 下一条独立消息 >>>\n".join(
            format_message_preview(message)
            for message in messages
        )
        self.log(
            f"随机行为：{action_name}｜共 {len(messages)} 条消息｜内容：「{preview}」"
        )
        if not self.auto_send.get():
            self.log(f"观察模式：本来会依次发送「{preview}」")
            return

        if not self.confirmed_once and forced_reply is None:
            confirmed = messagebox.askyesno(
                "首次发送确认",
                f"程序将依次发送 {len(messages)} 条消息：\n\n"
                f"{preview}\n\n"
                "请确认当前聊天对象正确。继续吗？",
            )
            if not confirmed:
                self.auto_send.set(False)
                self.log("已取消发送并切回观察模式。")
                return
            self.confirmed_once = True

        try:
            self.send_to_wechat(hwnd, rect, messages)
            self.log(f"已依次发送 {len(messages)} 条消息：「{preview}」")
            if row_id:
                self.remember_sent_reply(
                    row_id,
                    action_name,
                    messages,
                    selection,
                )
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

        last_reply = self.tickle_state["last_replies"].get(row_id, "")
        sent_replies = self.tickle_state["sent_replies"].get(row_id, [])

        def choose_library_reply():
            used = self.tickle_state["used_library_replies"].get(row_id, [])
            actions_by_key = {
                reply_action_key(messages): messages
                for messages in self.get_reply_actions()
            }
            reply_key, reset_cycle = choose_unused_reply(
                list(actions_by_key),
                used,
                last_reply,
            )
            if reply_key:
                messages = actions_by_key[reply_key]
            else:
                messages = ("你把我拍醒了",)
                reply_key = reply_action_key(messages)
            return (
                messages,
                "随机回复",
                {
                    "is_library": True,
                    "reset_cycle": reset_cycle,
                    "reply_key": reply_key,
                },
            )

        def choose_unseen_static(candidates, action_name):
            actions_by_key = {
                reply_action_key((item,)): (item,)
                for item in dict.fromkeys(candidates)
            }
            available = [
                reply_key
                for reply_key in actions_by_key
                if reply_key not in sent_replies and reply_key != last_reply
            ]
            if not available:
                return choose_library_reply()
            reply_key = random.choice(available)
            return (
                actions_by_key[reply_key],
                action_name,
                {
                    "is_library": False,
                    "reset_cycle": False,
                    "reply_key": reply_key,
                },
            )

        roll = random.random()
        if roll < 0.90:
            return choose_library_reply()
        if roll < 0.94:
            messages = (
                f"这是第{count}次拍我，再拍两下我就进化成路由器",
            )
            return (
                messages,
                "计数器",
                {
                    "is_library": False,
                    "reset_cycle": False,
                    "reply_key": reply_action_key(messages),
                },
            )
        if roll < 0.97:
            if streak >= 2:
                message = (
                    f"第{count}次事件触发{streak}连拍！"
                    "你已成功把我的理智打成了压缩包"
                )
            else:
                message = f"第{count}次连击启动失败，只惊动了一只路过的鸽子"
            messages = (message,)
            return (
                messages,
                "连击系统",
                {
                    "is_library": False,
                    "reset_cycle": False,
                    "reply_key": reply_action_key(messages),
                },
            )
        if roll < 0.99:
            return choose_unseen_static(SYSTEM_REPLIES, "假装系统消息")
        return choose_unseen_static(RED_PACKET_REPLIES, "红包彩蛋")

    def remember_sent_reply(self, row_id, action_name, messages, selection):
        reply_key = selection.get("reply_key") or reply_action_key(messages)
        if selection.get("is_library"):
            used_by_id = self.tickle_state["used_library_replies"]
            if selection.get("reset_cycle"):
                used_by_id[row_id] = []
                self.log(f"会话「{row_id}」已用完整个回复库，开始新一轮。")
            used = used_by_id.setdefault(row_id, [])
            if reply_key not in used:
                used.append(reply_key)

        sent = self.tickle_state["sent_replies"].setdefault(row_id, [])
        if reply_key not in sent:
            sent.append(reply_key)
        self.tickle_state["last_replies"][row_id] = reply_key
        save_tickle_state(self.tickle_state)
        record_reply_sent(row_id, action_name, messages)

        used_count = len(
            self.tickle_state["used_library_replies"].get(row_id, [])
        )
        library_count = len(self.reply_actions_cache)
        self.log(
            f"去重记录：会话「{row_id}」本轮已使用 "
            f"{used_count}/{library_count} 条随机库回复"
        )

    def open_reply_history(self):
        try:
            REPLY_HISTORY_PATH.touch(exist_ok=True)
            os.startfile(REPLY_HISTORY_PATH)
        except OSError as exc:
            messagebox.showerror("无法打开发送记录", str(exc))

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

    def send_to_wechat(self, hwnd, rect, messages):
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
            time.sleep(0.3)
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 0x0002, 0)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.25)
        dispatch_reply_action(
            messages,
            lambda message: self.send_one_message(rect, message),
        )

    def send_one_message(self, rect, message):
        left, top, right, bottom = rect
        width = right - left
        height = bottom - top
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
        if is_image_message(message):
            path = image_message_path(message)
            copy_image_to_clipboard(path)
            paste_delay = 0.65
        else:
            self.root.clipboard_clear()
            self.root.clipboard_append(message)
            self.root.update()
            paste_delay = 0.20

        user32.keybd_event(0x11, 0, 0, 0)  # Ctrl down
        user32.keybd_event(0x56, 0, 0, 0)  # V down
        user32.keybd_event(0x56, 0, 0x0002, 0)
        user32.keybd_event(0x11, 0, 0x0002, 0)
        time.sleep(paste_delay)

        # 点击 Send，比依赖用户的 Enter/Ctrl+Enter 发送设置更稳定。
        send_x = int(right - 37)
        send_y = int(bottom - 38)
        user32.SetCursorPos(send_x, send_y)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)

    def test_reply(self):
        actions = self.get_reply_actions()
        messages = random.choice(actions) if actions else ("You tickled me.",)
        preview = "\n>>> 下一条独立消息 >>>\n".join(
            format_message_preview(message)
            for message in messages
        )
        self.log(f"随机结果（{len(messages)} 条消息）：「{preview}」")

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
