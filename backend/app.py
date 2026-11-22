import hashlib
import io
import json
import os
import re
import secrets
import time
import traceback
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import psycopg2
from psycopg2.extras import Json, RealDictCursor

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", BASE_DIR / "uploads"))
ROUTES_PATH = BASE_DIR / "routes.json"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "7001"))
MAX_UPLOAD = 20 * 1024 * 1024

# 账号格式：字母或数字开头，2-32 位字母/数字/下划线/短横线（与登录页校验保持一致）
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,31}$")

ARTICLE_FIELDS = [
    "timestamp", "author", "reviewer", "title", "content_short", "content",
    "forecast", "importance", "type", "status", "display_time", "comment_disabled",
    "pageviews", "image_uri", "platforms", "source_uri", "remark",
]

ACCOUNT_FIELDS = [
    "timestamp", "biz_date", "category", "client", "phone", "wechat", "platform", "items", "unit_price", "quantity",
    "revenue", "cost", "profit", "status", "remark", "creator", "platform_order_no",
    "license_name", "credit_code", "legal_person", "legal_id",
    "id_photos",
]


def normalize_photos(raw):
    """身份证 / 执照照片列表统一成 [{url, name, size}]，最多 20 张，脏数据直接丢。"""
    if not isinstance(raw, list):
        return []
    photos = []
    for item in raw:
        if isinstance(item, str):
            if item.strip():
                photos.append({"url": item.strip(), "name": "", "size": 0})
        elif isinstance(item, dict):
            url = str(item.get("url") or "").strip()
            if url:
                try:
                    size = int(item.get("size") or 0)
                except (TypeError, ValueError):
                    size = 0
                photos.append({
                    "url": url,
                    "name": str(item.get("name") or "")[:120],
                    "size": size,
                })
    return photos[:20]

COST_FIELDS = [
    "timestamp", "biz_date", "category", "payee", "amount", "method", "related_order",
    "remark", "creator",
]

# 订单进度阶段：通用流转 + 工商/税务两类办事节点。
# 工商、税务节点均带「工商 · / 税务 ·」前缀，写进 step 字段后自成口径，
# 时间线一眼能看出这条跟进属于哪条线，也方便按前缀统计。
PROGRESS_COMMON_STEPS = ["已录入", "已联系", "已报价", "已付款", "办理中", "已交付", "已完成"]

# 工商线：资料收集 → 名称核准 → 网上申报 → 材料签署 → 受理审核 →（补正）→ 公示公告 → 领证 → 刻章/银行/社保 → 办结
PROGRESS_BIZ_STEPS = [
    "工商 · 资料收集",
    "工商 · 名称核准",
    "工商 · 网上申报",
    "工商 · 材料签署",
    "工商 · 受理审核",
    "工商 · 补正材料",
    "工商 · 公示公告",
    "工商 · 领取执照",
    "工商 · 刻章/银行",
    "工商 · 办结",
]

# 税务线：资料收集 → 报到 → 票种核定 →（补申报 → 欠税罚款处理 → 解除非正常）→ 清税申报 → 清税证明 → 办结
PROGRESS_TAX_STEPS = [
    "税务 · 资料收集",
    "税务 · 税务报到",
    "税务 · 票种核定",
    "税务 · 补申报",
    "税务 · 欠税罚款处理",
    "税务 · 解除非正常",
    "税务 · 清税申报",
    "税务 · 清税证明",
    "税务 · 办结",
]

PROGRESS_STAGE_GROUPS = [
    {"key": "common", "label": "通用流程", "hint": "从接单到收款", "stages": PROGRESS_COMMON_STEPS},
    {"key": "biz", "label": "工商办理", "hint": "执照 / 年报 / 变更 / 注销", "stages": PROGRESS_BIZ_STEPS},
    {"key": "tax", "label": "税务办理", "hint": "报到 / 补报 / 解非 / 清税", "stages": PROGRESS_TAX_STEPS},
]

# 扁平列表保留给老接口/老前端，顺序为通用 → 工商 → 税务
PROGRESS_STEPS = PROGRESS_COMMON_STEPS + PROGRESS_BIZ_STEPS + PROGRESS_TAX_STEPS


def stage_group_key(step):
    """「工商 · 受理审核」→ biz；老数据（已录入/已联系…）→ common。"""
    head = str(step or "").split("·")[0].strip()
    if head == "工商":
        return "biz"
    if head == "税务":
        return "tax"
    return "common"

# 营业执照状态（工商口径）与税务状态，前端下拉与此保持一致
# 工商状态支持多选，库里用英文逗号拼接，顺序按本数组固定（如「正常,另册管理」）
BIZ_STATUSES = ["正常", "年报异常", "地址异常", "另册管理", "吊销"]
TAX_STATUSES = ["税务正常", "无税务", "税务非正常", "清算"]


def normalize_multi_status(value, allowed):
    """多选状态归一：兼容数组/字符串（中文逗号、顿号、斜杠分隔），按 allowed 顺序去重拼接。"""
    if isinstance(value, (list, tuple, set)):
        raw = [str(item).strip() for item in value]
    else:
        raw = [part.strip() for part in re.split(r"[,，、/|]", str(value or ""))]
    picked = []
    for item in raw:
        if item and item not in picked:
            picked.append(item)
    # 已知取值排前面并保持固定顺序，历史遗留的自定义值原样跟在后面
    ordered = [item for item in allowed if item in picked]
    ordered.extend(item for item in picked if item not in allowed)
    # 工商状态的「正常」与各类异常互斥：同时出现时以异常为准（正常只是默认态）
    if len(ordered) > 1 and "正常" in ordered and allowed is BIZ_STATUSES:
        ordered = [item for item in ordered if item != "正常"]
    return ",".join(ordered)

COST_CATEGORIES = ["采购", "物流", "人工", "房租", "水电", "推广", "差旅", "办公", "其他"]

PROGRESS_STATUS = ("pending", "doing", "done", "blocked")

# 任务（执照明细）状态：在原有 待定/进行中/已完成 之外，增加 取消订单 / 已退款
ITEM_STATUSES = ("pending", "doing", "done", "cancelled", "refunded")
# 关单状态：不再计为进行中，订单级状态回算时按它们判断整单是否已取消/已退款
CLOSED_ITEM_STATUSES = ("done", "cancelled", "refunded")
ITEM_STATUS_LABELS = {
    "pending": "待定",
    "doing": "进行中",
    "done": "已完成",
    "cancelled": "取消订单",
    "refunded": "已退款",
}



def biz_month_key(biz_date, fallback=None):
    """把各种写法的业务日期（2026-10-29 / 10/29 / 2026年10月29日）归一到 YYYY-MM。"""
    text = str(biz_date or "").strip()
    if text:
        head = (
            text.replace("/", "-")
            .replace(".", "-")
            .replace("年", "-")
            .replace("月", "-")
            .replace("日", "")
        )
        parts = [part for part in head.split("-") if part.strip().isdigit()]
        if len(parts) >= 3 and len(parts[0]) == 4:
            return "%04d-%02d" % (int(parts[0]), int(parts[1]))
        if len(parts) == 2:
            month = int(parts[0])
            now = datetime.now()
            year = now.year - 1 if month > now.month + 6 else now.year
            return "%04d-%02d" % (year, month)
    if fallback is not None:
        return fallback.strftime("%Y-%m")
    return ""


def shift_month(base, offset):
    year = base.year + (base.month - 1 + offset) // 12
    month = (base.month - 1 + offset) % 12 + 1
    return datetime(year, month, 1)


def ms_month_key(stamp):
    """毫秒时间戳归到 YYYY-MM：订单哪个月办结，收入就算哪个月。"""
    try:
        value = float(stamp or 0)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    if value > 1e11:
        value = value / 1000.0
    return datetime.fromtimestamp(value).strftime("%Y-%m")


def account_month_ids(cur, month_key):
    """订单列表/汇总的月份口径：
    - 已办结（含取消/退款）：按完成月，与首页卡片、收入归集一致；
    - 未办结（进行中/待定）：没有完成月，按下单月份 biz_date（MM/DD，年份取创建时间）筛选，
      否则按完成月筛会把本月进行中的订单全部漏掉。
    """
    cur.execute(
        "SELECT id, completed_at, biz_date, created_at FROM account_records WHERE is_delete = 0"
    )
    ids = []
    for row in cur.fetchall():
        if row["completed_at"]:
            matched = ms_month_key(row["completed_at"]) == month_key
        else:
            bits = str(row["biz_date"] or "").strip().replace("-", "/").split("/")
            month = bits[0].zfill(2) if bits and bits[0].isdigit() else ""
            if not month:
                month = row["created_at"].strftime("%m") if row["created_at"] else ""
            year = ""
            if len(bits) >= 3 and len(bits[2]) == 4 and bits[2].isdigit():
                year = bits[2]
            elif row["created_at"]:
                year = row["created_at"].strftime("%Y")
            matched = bool(month) and ("%s-%s" % (year, month) == month_key)
        if matched:
            ids.append(int(row["id"]))
    return ids


class UploadedFile:
    def __init__(self, filename, data):
        self.filename = filename
        self.file = io.BytesIO(data)


def parse_multipart_file(raw, content_type):
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("boundary="):
            boundary = part[len("boundary="):].strip().strip('"')
    if not boundary:
        return None
    marker = ("--" + boundary).encode("utf-8")
    for chunk in raw.split(marker):
        chunk = chunk.strip(b"\r\n")
        if not chunk or chunk == b"--":
            continue
        head, sep, data = chunk.partition(b"\r\n\r\n")
        if not sep:
            continue
        headers = {}
        for line in head.decode("utf-8", "replace").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        disposition = headers.get("content-disposition", "")
        if "filename" not in disposition:
            continue
        filename = disposition.split("filename=", 1)[1].strip().strip('"')
        return UploadedFile(filename, data.rstrip(b"\r\n"))
    return None


def connect():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "127.0.0.1"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
    )


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return "pbkdf2$%s$%s" % (salt, digest.hex())


def verify_password(password, stored):
    try:
        scheme, salt, digest = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "pbkdf2":
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()
    return secrets.compare_digest(check, digest)


def now_ms():
    return int(time.time() * 1000)


def normalize_phone(value):
    """手机号只留数字：粘贴「+86 138 0013 8000」这种整串也能一步收拾干净。"""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) > 11 and digits.startswith("86"):
        digits = digits[2:]
    return digits[:11]


def generate_order_no(stamp_ms, record_id):
    """订单编号：DD + 录入日期（北京时间）+ 4 位订单 id，如 DD20261105-0001。
    序号取自订单 id（全表自增），天然不重复；日期取业务录入时间，和列表里看到的日期一致。"""
    moment = datetime.fromtimestamp(int(stamp_ms or now_ms()) / 1000, tz=timezone.utc) + timedelta(hours=8)
    return "DD%s-%s" % (moment.strftime("%Y%m%d"), str(int(record_id)).zfill(4))


def format_completed(stamp):
    """毫秒时间戳 → 「YYYY-MM-DD HH:MM」（按北京时间 UTC+8，服务器本身跑在 UTC）。"""
    if not stamp:
        return ""
    moment = datetime.fromtimestamp(int(stamp) / 1000, tz=timezone.utc) + timedelta(hours=8)
    return moment.strftime("%Y-%m-%d %H:%M")


def parse_ms(value):
    if value is None or value == "":
        return now_ms()
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    text = text.replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except ValueError:
        return now_ms()


def parse_display(value, fallback_ms):
    if value is None or value == "":
        return datetime.fromtimestamp(fallback_ms / 1000, timezone.utc)
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        return datetime.fromtimestamp(int(float(value)) / 1000, timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.fromtimestamp(fallback_ms / 1000, timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def as_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in ("1", "true", "yes", "on")


def article_out(row):
    platforms = row["platforms"] if row["platforms"] is not None else []
    display = row["display_time"]
    display_text = display.strftime("%Y-%m-%d %H:%M:%S") if display else None
    return {
        "id": row["id"],
        "timestamp": int(row["timestamp"] or 0),
        "author": row["author"] or "",
        "reviewer": row["reviewer"] or "",
        "title": row["title"] or "",
        "content_short": row["content_short"] or "",
        "content": row["content"] or "",
        "forecast": float(row["forecast"] or 0),
        "importance": int(row["importance"] or 0),
        "type": row["type"] or "",
        "status": row["status"] or "draft",
        "display_time": display_text,
        "comment_disabled": bool(row["comment_disabled"]),
        "pageviews": int(row["pageviews"] or 0),
        "image_uri": row["image_uri"] or "",
        "platforms": platforms,
        "source_uri": row["source_uri"] or "",
        "remark": row["remark"] or "",
    }


def to_number(value, default=None):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_amount(value):
    if value is None:
        return "待定"
    number = float(value)
    if number == int(number):
        return str(int(number))
    return ("%.2f" % number).rstrip("0").rstrip(".")


# ---------- 财务报表 ----------

MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")


def normalize_month(text):
    """把 2026-10 / 2026/10 / 10 等写法归一到 YYYY-MM，默认当月。"""
    raw = str(text or "").strip()
    if raw:
        head = raw.replace("/", "-").replace(".", "-").replace("年", "-").replace("月", "")
        parts = [part for part in head.split("-") if part.strip().isdigit()]
        if len(parts) >= 2 and len(parts[0]) == 4:
            candidate = "%s-%02d" % (parts[0], int(parts[1]))
        elif len(parts) == 1 and len(parts[0]) == 4:
            candidate = parts[0] + "-01"
        elif len(parts) == 1 and 1 <= int(parts[0]) <= 12:
            now = datetime.now()
            candidate = "%04d-%02d" % (now.year, int(parts[0]))
        else:
            candidate = ""
        match = MONTH_RE.match(candidate)
        if match and 1 <= int(match.group(2)) <= 12:
            return "%04d-%02d" % (int(match.group(1)), int(match.group(2)))
    now = datetime.now()
    return "%04d-%02d" % (now.year, now.month)


def month_bounds(month):
    """YYYY-MM → 本地时区的 (首日 0 点, 次月 1 日 0 点)。"""
    year, mon = int(month[:4]), int(month[5:7])
    begin = datetime(year, mon, 1)
    end = datetime(year + 1, 1, 1) if mon == 12 else datetime(year, mon + 1, 1)
    return begin, end


def prev_month(month):
    year, mon = int(month[:4]), int(month[5:7])
    if mon == 1:
        return "%04d-12" % (year - 1)
    return "%04d-%02d" % (year, mon - 1)


def finance_month_of(biz_date, ts_ms):
    """一条记录归属的财务月份：业务日期能解析出年份就用它；
    只有「10/30」这类月日写法时，年份按录入时间补全。"""
    key = biz_month_key(biz_date)
    if key:
        return key
    stamp = float(ts_ms or 0)
    if not stamp:
        return None
    record_time = datetime.fromtimestamp(stamp / 1000)
    text = str(biz_date or "").strip()
    parts = [part for part in re.split(r"[-/.年月日 ]+", text) if part.strip().isdigit()]
    month_num = 0
    for part in parts:
        value = int(part)
        if 1 <= value <= 12:
            month_num = value
            break
    if month_num:
        return "%04d-%02d" % (record_time.year, month_num)
    return "%04d-%02d" % (record_time.year, record_time.month)


def finance_day_of(biz_date, ts_ms):
    """记录落在自然月的哪一天：优先业务日期（2026-10-30 / 10/30），其次录入时间。"""
    text = str(biz_date or "").strip()
    head = (
        text.replace("/", "-").replace(".", "-")
        .replace("年", "-").replace("月", "-").replace("日", "")
    )
    parts = [part for part in head.split("-") if part.strip().isdigit()]
    if len(parts) >= 3 and len(parts[0]) == 4:
        return "%02d-%02d" % (int(parts[1]), int(parts[2]))
    if len(parts) == 2 and int(parts[0]) <= 12:
        return "%02d-%02d" % (int(parts[0]), int(parts[1]))
    stamp = float(ts_ms or 0)
    if stamp:
        return datetime.fromtimestamp(stamp / 1000).strftime("%m-%d")
    return None


def finance_group_rows(rows, key_getter, amount_getter):
    """按 key 聚合金额，返回 [{name, amount, count}]，按金额降序。"""
    grouped = {}
    for row in rows:
        name = (key_getter(row) or "").strip() or "未分类"
        bucket = grouped.setdefault(name, {"name": name, "amount": 0.0, "count": 0})
        bucket["amount"] += float(amount_getter(row) or 0)
        bucket["count"] += 1
    result = list(grouped.values())
    result.sort(key=lambda item: item["amount"], reverse=True)
    return result


def account_message(record):
    """订单消息文案：一单可挂多个执照，每个执照一行。"""
    details = record.get("details") or []
    lines = ["【订单】"]
    if record.get("order_no"):
        lines.append("编号：" + record["order_no"])
    head = " ".join(part for part in [record.get("biz_date"), record.get("category")] if part)
    if head:
        lines.append(head)
    details_count = len(details)
    subject = record.get("client") or ""
    if details_count <= 1 and record.get("items"):
        subject += record["items"]
    if subject:
        lines.append(subject)
    if details_count > 1:
        lines.append("共 %d 个执照任务" % details_count)
    if record.get("phone"):
        lines.append("手机：" + record["phone"])
    for index, detail in enumerate(details, 1):
        name = detail.get("license_name") or ""
        extras = []
        if detail.get("biz_status"):
            extras.append("工商：" + normalize_multi_status(detail["biz_status"], BIZ_STATUSES).replace(",", "、"))
        if detail.get("tax_status"):
            extras.append("税务：" + detail["tax_status"])
        if detail.get("items"):
            extras.append("业务：" + detail["items"])
        if not name and not extras:
            continue
        prefix = ("执照%d：" % index) if len(details) > 1 else "执照："
        line = prefix + (name or "未填名称")
        if extras:
            line += "（" + " / ".join(extras) + "）"
        lines.append(line)
    if len(details) == 1:
        single = details[0]
        lines.append("单价：" + format_amount(single.get("unit_price")))
        quantity = single.get("quantity")
        if quantity is not None and float(quantity) != 1:
            lines.append("数量：" + format_amount(quantity))
            lines.append("金额：" + format_amount(single.get("revenue")))
    lines.append("收入：" + format_amount(record.get("revenue")))
    lines.append("成本：" + format_amount(record.get("cost")))
    lines.append("利润：" + format_amount(record.get("profit")))
    if record.get("remark"):
        lines.append("备注：" + record["remark"])
    return "\n".join(lines)


def menu_out(row):
    """菜单行 → 前端侧边栏配置。登录接口与 /menu/list 共用同一份结构。"""
    return {
        "id": row["id"],
        "path": row["path"],
        "title": row["title"],
        "icon": row["icon"] or "",
        "parent": row["parent"] or "",
        "sort": int(row["sort"] or 0),
        "visible": bool(row["visible"]),
    }


def item_out(row):
    created = row.get("created_at")
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "license_name": row.get("license_name") or "",
        "credit_code": row.get("credit_code") or "",
        "legal_person": row.get("legal_person") or "",
        "legal_id": row.get("legal_id") or "",
        "legal_phone": row.get("legal_phone") or "",
        "biz_status": row.get("biz_status") or "",
        "tax_status": row.get("tax_status") or "",
        "items": row.get("items") or "",
        "unit_price": None if row.get("unit_price") is None else float(row["unit_price"]),
        "quantity": None if row.get("quantity") is None else float(row["quantity"]),
        "revenue": None if row.get("revenue") is None else float(row["revenue"]),
        "cost": None if row.get("cost") is None else float(row["cost"]),
        "profit": None if row.get("profit") is None else float(row["profit"]),
        "status": row.get("status") or "pending",
        "completed_at": int(row["completed_at"]) if row.get("completed_at") else None,
        "created_at": int(created.timestamp() * 1000) if created else None,
        "remark": row.get("remark") or "",
        "sort": int(row.get("sort") or 0),
        # 执照照片（随执照明细存，编辑订单时可补传）
        "license_photos": normalize_photos(row.get("license_photos")),
        # 主跟进人（username）；为空表示还没指定，展示时按跟进记录推断
        "owner": row.get("owner") or "",
        "owner_updated_at": int(row["owner_updated_at"]) if row.get("owner_updated_at") else None,
        # 退款：累计退款金额 + 最近一次退款时间，前端用来展示「已退款 / 部分退款」
        "refund_amount": float(row.get("refund_amount") or 0),
        "refund_at": int(row["refund_at"]) if row.get("refund_at") else None,
        # 取消订单：原因 / 备注 / 取消时间
        "cancel_reason": row.get("cancel_reason") or "",
        "cancel_note": row.get("cancel_note") or "",
        "cancelled_at": int(row["cancelled_at"]) if row.get("cancelled_at") else None,
    }


def progress_snapshot(cur, item_ids):
    """每条明细的三条办理线进度（已完成数 / 总数 / 当前未完成节点），供订单详情直接展示。"""
    ids = [int(i) for i in item_ids if i]
    if not ids:
        return {}
    cur.execute(
        "SELECT item_id, step, status, timestamp FROM order_progress"
        " WHERE item_id = ANY(%s) AND is_delete = 0 ORDER BY timestamp DESC, id DESC",
        (ids,),
    )
    raw = {}
    for row in cur.fetchall():
        raw.setdefault(row["item_id"], []).append(row)

    snapshot = {}
    # 建单时系统自动写的「已录入」不算真实进度，各线取最近记录时要跳过
    AUTO_STEPS = {"已录入"}
    for item_id in ids:
        records = raw.get(item_id, [])
        done = {r["step"] for r in records if (r["status"] or "") == "done"}
        open_map = {}
        last_map = {}
        for record in records:
            key = stage_group_key(record["step"])
            if (record["status"] or "") != "done":
                open_map.setdefault(key, record)
            if record["step"] not in AUTO_STEPS:
                last_map.setdefault(key, record)
        lines = []
        for key in ("biz", "tax", "common"):
            group = next((g for g in PROGRESS_STAGE_GROUPS if g["key"] == key), None)
            if group is None:
                continue
            stages = group["stages"]
            hit = open_map.get(key)
            recent = last_map.get(key)
            lines.append({
                "group": key,
                "label": group["label"].replace("办理", "").replace("流程", ""),
                "done": sum(1 for stage in stages if stage in done),
                "total": len(stages),
                "open_step": (hit["step"] or "") if hit else "",
                "open_status": (hit["status"] or "doing") if hit else "",
                "open_timestamp": int(hit["timestamp"] or 0) if hit else 0,
                "last_step": (recent["step"] or "") if recent else "",
                "last_status": (recent["status"] or "") if recent else "",
            })
        last = records[0] if records else None
        snapshot[item_id] = {
            "lines": lines,
            "last_step": (last["step"] or "") if last else "",
            "last_status": (last["status"] or "") if last else "",
            "last_timestamp": int(last["timestamp"] or 0) if last else 0,
            "count": len(records),
        }
    return snapshot


def fetch_details(cur, account_ids):
    """批量取订单明细，避免列表 N+1 查询。"""
    ids = [int(i) for i in account_ids if i]
    if not ids:
        return {}
    cur.execute(
        "SELECT * FROM account_items WHERE account_id = ANY(%s) AND is_delete = 0 ORDER BY account_id, sort, id",
        (ids,),
    )
    grouped = {}
    for row in cur.fetchall():
        grouped.setdefault(row["account_id"], []).append(item_out(row))
    snapshot = progress_snapshot(cur, [item["id"] for items in grouped.values() for item in items])
    # 主跟进人补上显示名/头像，详情页不用再查一次用户表
    owner_usernames = sorted({
        item["owner"] for items in grouped.values() for item in items if item.get("owner")
    })
    owners = {}
    if owner_usernames:
        cur.execute("SELECT username, name, avatar FROM users WHERE username = ANY(%s)", (owner_usernames,))
        owners = {row["username"]: row for row in cur.fetchall()}
    for items in grouped.values():
        for item in items:
            item["progress"] = snapshot.get(item["id"], None)
            owner = owners.get(item.get("owner"))
            if owner:
                item["owner_name"] = owner["name"] or owner["username"]
                item["owner_avatar"] = owner["avatar"] or ""
    return grouped


def account_out(row, details=None):
    details = details or []
    record = {
        "id": row["id"],
        "order_no": row.get("order_no") or "",
        "platform_order_no": row.get("platform_order_no") or "",
        "timestamp": int(row["timestamp"] or 0),
        "biz_date": row["biz_date"] or "",
        "category": row["category"] or "",
        "client": row["client"] or "",
        "phone": row.get("phone") or "",
        "wechat": row.get("wechat") or "",
        "items": row["items"] or "",
        "unit_price": None if row["unit_price"] is None else float(row["unit_price"]),
        "quantity": None if row["quantity"] is None else float(row["quantity"]),
        "revenue": None if row["revenue"] is None else float(row["revenue"]),
        "cost": None if row["cost"] is None else float(row["cost"]),
        "profit": None if row["profit"] is None else float(row["profit"]),
        "status": row["status"] or "pending",
        "platform": row["platform"] or "",
        "completed_at": int(row["completed_at"]) if row.get("completed_at") else None,
        "remark": row["remark"] or "",
        "creator": row["creator"] or "",
        # 客户身份证照片（订单层面）
        "id_photos": normalize_photos(row.get("id_photos")),
        "details": details,
        "license_count": len(details),
        "done_count": len([item for item in details if item["status"] == "done"]),
    }
    # 兼容旧的单执照字段：取第一个明细，老页面/旧脚本仍能读到
    first = details[0] if details else {}
    record["license_name"] = first.get("license_name") or row.get("license_name") or ""
    record["credit_code"] = first.get("credit_code") or row.get("credit_code") or ""
    record["legal_person"] = first.get("legal_person") or row.get("legal_person") or ""
    record["legal_id"] = first.get("legal_id") or row.get("legal_id") or ""
    record["legal_phone"] = first.get("legal_phone") or ""
    record["message"] = account_message(record)
    return record


def user_out(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "name": row["name"] or row["username"],
        "avatar": row["avatar"] or "",
        "introduction": row["introduction"] or "",
        "roles": list(row["roles"] or []),
        "created": row["created_at"].strftime("%Y-%m-%d %H:%M:%S") if row.get("created_at") else "",
    }


def progress_out(row):
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "item_id": row.get("item_id"),
        "task_id": row.get("task_id"),
        "step": row["step"] or "",
        "status": row["status"] or "doing",
        "note": row["note"] or "",
        "operator": row["operator"] or "",
        # 跟进人显示名 / 头像（users 表里的 name、avatar，查不到就退回 username）
        "operator_name": row.get("operator_name") or row["operator"] or "",
        "operator_avatar": row.get("operator_avatar") or "",
        "timestamp": int(row["timestamp"] or 0),
    }


def progress_file_out(row):
    """办理线附件（工商 / 税务线上的图片、单据）。"""
    return {
        "id": row["id"],
        "item_id": row["item_id"],
        "account_id": row["account_id"],
        "line": row["line"] or "",
        "url": row["url"] or "",
        "name": row["name"] or "",
        "size": int(row["size"] or 0),
        "uploader": row["uploader"] or "",
        "timestamp": int(row["timestamp"] or 0),
    }


def cost_out(row):
    return {
        "id": row["id"],
        "timestamp": int(row["timestamp"] or 0),
        "biz_date": row["biz_date"] or "",
        "category": row["category"] or "",
        "payee": row["payee"] or "",
        "amount": None if row["amount"] is None else float(row["amount"]),
        "method": row["method"] or "",
        "related_order": row["related_order"],
        "remark": row["remark"] or "",
        "creator": row["creator"] or "",
        # refund = 订单退款自动写入的那条记录（金额已在订单收入里冲减）
        "kind": row.get("kind") or "",
        # 软删除：is_delete=1 表示「已删除」，数据仍在库里，可恢复
        "is_delete": int(row.get("is_delete") or 0),
        "record_status": "deleted" if row.get("is_delete") else "active",
    }


def insert_progress(cur, account_id, step, status, note, operator, stamp=None, item_id=None, task_id=None):
    """写入一条进度记录。

    item_id 指向执照明细（主任务），task_id 指向细分任务；
    细分任务的时间线只认 task_id，主任务级系统记录（已录入/状态变更等）不带 task_id。
    """
    if status not in PROGRESS_STATUS:
        status = "doing"
    cur.execute(
        """
        INSERT INTO order_progress (account_id, item_id, task_id, step, status, note, operator, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (account_id, item_id, task_id, step, status, note or "", operator or "", stamp or now_ms()),
    )


def auto_progress(cur, record, operator, item_id=None, detail=None):
    """订单/任务录入时生成一条「已录入」初始进度。"""
    subject = "".join(part for part in [record.get("client"), record.get("items")] if part)
    amount = format_amount(record.get("revenue"))
    note = "订单已录入：" + (subject or "未命名订单") + "，金额 " + amount
    if detail:
        license_name = detail.get("license_name") or "未填名称"
        detail_items = detail.get("items") or ""
        note = "任务已录入：%s%s" % (
            license_name,
            (" · " + detail_items) if detail_items else "",
        )
    insert_progress(cur, record["id"], "已录入", "done", note, operator, record.get("timestamp"), item_id)


def recalc_order(cur, account_id):
    """按执照明细回算订单级金额与状态。

    订单是否完成只取决于「还需要办的执照」：已取消的执照不要求办结，
    其余执照全部办结，整单就算完成——只有这种情况收入才计入总收入。
    全部取消=取消订单，全部退款=已退款，有推进=进行中。"""
    # 先锁住订单行再聚合：前端一次提交多条进度线时是并发请求，两个事务各算一遍，
    # 后算的那个如果读到的是旧明细状态，会把订单状态写回旧值（丢更新）。
    # 锁住订单行后，后到的事务会等前一个提交完再读，聚合结果一定是最新的。
    cur.execute("SELECT id FROM account_records WHERE id = %s FOR UPDATE", (account_id,))
    cur.execute(
        """
        SELECT COUNT(*) AS cnt,
               SUM(revenue) AS revenue,
               SUM(cost) AS cost,
               SUM(profit) AS profit,
               COUNT(*) FILTER (WHERE status = 'done') AS done,
               COUNT(*) FILTER (WHERE status = 'refunded') AS refunded,
               COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled,
               COUNT(*) FILTER (WHERE status IN ('doing', 'done')) AS active,
               MAX(completed_at) FILTER (WHERE status IN ('done', 'cancelled', 'refunded')) AS completed_at,
               string_agg(DISTINCT NULLIF(items, ''), '、') AS items
          FROM account_items
         WHERE account_id = %s AND is_delete = 0
        """,
        (account_id,),
    )
    row = cur.fetchone()
    count = int(row["cnt"] or 0)
    done = int(row["done"] or 0)
    refunded = int(row["refunded"] or 0)
    cancelled = int(row["cancelled"] or 0)
    active = int(row["active"] or 0)
    # 还要办结的执照数：取消掉的执照不用做，不阻塞整单完成
    waiting = count - cancelled
    if count and waiting == 0:
        # 执照全被取消了：整单跟着取消，有退款就按已退款记
        status = "refunded" if refunded else "cancelled"
        completed_at = row["completed_at"]
    elif count and done == waiting:
        # 需要办的执照全部办结 → 订单完成，收入才计入总收入
        status = "done"
        completed_at = row["completed_at"]
    elif count and refunded and (done + refunded) == waiting:
        # 剩下的都退款关单了：整单按「已退款」记，方便按状态筛出退款单
        status = "refunded"
        completed_at = row["completed_at"]
    elif active:
        status = "doing"
        completed_at = None
    else:
        status = "pending"
        completed_at = None
    cur.execute(
        """
        UPDATE account_records
           SET revenue = %s, cost = %s, profit = %s, quantity = %s,
               items = COALESCE(%s, items), status = %s, completed_at = %s
         WHERE id = %s
        """,
        (row["revenue"], row["cost"], row["profit"], count or None, row["items"], status, completed_at, account_id),
    )


def repair_order_statuses(conn):
    """兜底修复：订单状态以明细为准。

    历史上并发写进度时出现过「明细已经全部完成、订单还挂在进行中」的丢更新，
    启动时把这类对不上的订单重算一遍；只处理不一致的，正常订单不写库。
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 细分任务全被取消、执照还挂在待办状态：随单取消，免得整单被堵在「进行中」
        cur.execute(
            """
            UPDATE account_items i
               SET status = 'cancelled',
                   completed_at = NULL,
                   cancelled_at = COALESCE(i.cancelled_at, (extract(epoch from now()) * 1000)::bigint)
             WHERE i.status IN ('pending', 'doing', 'done') AND i.is_delete = 0
               AND EXISTS (SELECT 1 FROM account_item_tasks t WHERE t.item_id = i.id AND t.is_delete = 0)
               AND NOT EXISTS (
                   SELECT 1 FROM account_item_tasks t
                    WHERE t.item_id = i.id AND t.status <> 'cancelled' AND t.is_delete = 0
               )
            RETURNING i.id
            """
        )
        items_fixed = [row["id"] for row in cur.fetchall()]
        cur.execute(
            """
            SELECT a.id
              FROM account_records a
              JOIN account_items i ON i.account_id = a.id
             WHERE a.is_delete = 0 AND i.is_delete = 0
             GROUP BY a.id, a.status
            HAVING a.status <> CASE
                     WHEN COUNT(*) FILTER (WHERE i.status <> 'cancelled') = 0
                          THEN CASE WHEN COUNT(*) FILTER (WHERE i.status = 'refunded') > 0
                                    THEN 'refunded' ELSE 'cancelled' END
                     WHEN COUNT(*) FILTER (WHERE i.status = 'done')
                          = COUNT(*) FILTER (WHERE i.status <> 'cancelled') THEN 'done'
                     WHEN COUNT(*) FILTER (WHERE i.status IN ('done', 'refunded'))
                          = COUNT(*) FILTER (WHERE i.status <> 'cancelled')
                          AND COUNT(*) FILTER (WHERE i.status = 'refunded') > 0 THEN 'refunded'
                     WHEN COUNT(*) FILTER (WHERE i.status IN ('doing', 'done')) > 0 THEN 'doing'
                     ELSE 'pending'
                   END
            """
        )
        fixed = [row["id"] for row in cur.fetchall()]
        for account_id in fixed:
            recalc_order(cur, account_id)
    if items_fixed:
        print("[startup] 细分任务全取消、执照随单取消：%s" % ", ".join(str(item) for item in items_fixed), flush=True)
    if fixed:
        print("[startup] 修正订单状态不一致：%s" % ", ".join(str(item) for item in fixed), flush=True)


def refund_item_line(cur, item, amount, stamp):
    """把一条任务的收入冲减 amount（退款），返回 (退款后金额, 退款后状态)。"""
    revenue = float(item.get("revenue") or 0)
    cost = float(item.get("cost") or 0)
    new_revenue = round(max(0.0, revenue - amount), 2)
    full = new_revenue <= 0.004
    status = item.get("status") or "pending"
    new_status = "refunded" if full else (status if status in ("doing", "done") else "doing")
    completed_at = stamp if full else item.get("completed_at")
    cur.execute(
        """
        UPDATE account_items
           SET revenue = %s, profit = %s, status = %s, completed_at = %s,
               refund_amount = COALESCE(refund_amount, 0) + %s, refund_at = %s
         WHERE id = %s
        """,
        (new_revenue, round(new_revenue - cost, 2), new_status, completed_at, amount, stamp, item["id"]),
    )
    # 全额退款等同于这条任务办不下去了，细分任务一起标记取消（已办结的保留）
    if full:
        cur.execute(
            "UPDATE account_item_tasks SET status = 'cancelled', updated_at = %s"
            " WHERE item_id = %s AND status <> 'done'",
            (stamp, item["id"]),
        )
    return new_revenue, new_status


def cancel_item_line(cur, item, stamp, reason, remark, clear_amount):
    """把一条任务标成「取消订单」，返回 (取消前金额, 取消后金额)。"""
    revenue = float(item.get("revenue") or 0)
    cost = float(item.get("cost") or 0)
    new_revenue = 0.0 if clear_amount else revenue
    cur.execute(
        """
        UPDATE account_items
           SET status = 'cancelled', completed_at = %s, cancelled_at = %s,
               cancel_reason = %s, cancel_note = %s, revenue = %s, profit = %s
         WHERE id = %s
        """,
        (stamp, stamp, reason, remark, new_revenue, round(new_revenue - cost, 2), item["id"]),
    )
    # 取消订单：没办结的细分任务一起取消，展开后不会还挂着「未开始」
    cur.execute(
        "UPDATE account_item_tasks SET status = 'cancelled', updated_at = %s"
        " WHERE item_id = %s AND status <> 'done'",
        (stamp, item["id"]),
    )
    return revenue, new_revenue


def split_refund_amount(items, amount):
    """把一笔退款金额按顺序分摊到若干任务上，返回 [(任务, 分摊金额)]。

    先可着前面的任务退，退不完再退下一条；分到最后差几分钱时补到已分摊的那几笔上，
    保证「分摊总额 == 本次退款金额」，不会在成本账上留下几分钱的对不上。
    """
    shares = []
    left = round(float(amount), 2)
    for item in items:
        if left <= 0.004:
            break
        revenue = round(float(item.get("revenue") or 0), 2)
        if revenue <= 0.004:
            continue
        take = round(min(revenue, left), 2)
        shares.append([item, take])
        left = round(left - take, 2)
    if shares and left > 0.004:
        # 兜底：残差补到还没退满的那一条上，仍然不能超过该任务当前金额
        for pair in reversed(shares):
            revenue = round(float(pair[0].get("revenue") or 0), 2)
            room = round(revenue - pair[1], 2)
            if room <= 0.004:
                continue
            extra = min(room, left)
            pair[1] = round(pair[1] + extra, 2)
            left = round(left - extra, 2)
            if left <= 0.004:
                break
    return [(item, take) for item, take in shares]


def migrate_account_items(cur):
    """把历史「一单一执照」的数据迁移成明细：每个老订单补一条明细，进度挂到该明细上。"""
    cur.execute(
        """
        INSERT INTO account_items (
            account_id, license_name, credit_code, legal_person, legal_id, items,
            unit_price, quantity, revenue, cost, profit, status, completed_at, remark, sort, created_at
        )
        SELECT a.id, a.license_name, a.credit_code, a.legal_person, a.legal_id, a.items,
               a.unit_price, a.quantity, a.revenue, a.cost, a.profit,
               COALESCE(a.status, 'pending'), a.completed_at, a.remark, 0, a.created_at
          FROM account_records a
         WHERE a.is_delete = 0
           AND NOT EXISTS (SELECT 1 FROM account_items i WHERE i.account_id = a.id AND i.is_delete = 0)
           AND (COALESCE(a.client, '') <> '' OR COALESCE(a.items, '') <> ''
                OR COALESCE(a.license_name, '') <> '' OR a.revenue IS NOT NULL)
        """
    )
    # 历史备注里常写着手机号，手机号为空时顺手补上，省得每条订单都手工回填
    cur.execute(
        """
        UPDATE account_records
           SET phone = substring(remark from '(1[3-9][0-9]{9})')
         WHERE COALESCE(phone, '') = ''
           AND remark ~ '1[3-9][0-9]{9}'
        """
    )
    # 老进度没有明细归属，挂到该订单的第一条明细上，进度页才不会出现「孤儿任务」
    cur.execute(
        """
        UPDATE order_progress p
           SET item_id = sub.id
          FROM (SELECT account_id, MIN(id) AS id FROM account_items
                 WHERE is_delete = 0 GROUP BY account_id) sub
         WHERE p.account_id = sub.account_id AND p.item_id IS NULL
        """
    )


def init_db():

    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id serial PRIMARY KEY,
            username text UNIQUE NOT NULL,
            password_hash text NOT NULL,
            name text NOT NULL,
            avatar text,
            introduction text,
            roles text[] NOT NULL
        )
        """,
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now()
        """,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token text PRIMARY KEY,
            user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS articles (
            id serial PRIMARY KEY,
            timestamp bigint,
            author text,
            reviewer text,
            title text,
            content_short text,
            content text,
            forecast numeric,
            importance integer,
            type text,
            status text,
            display_time timestamptz,
            comment_disabled boolean DEFAULT false,
            pageviews integer DEFAULT 0,
            image_uri text,
            platforms jsonb,
            source_uri text,
            remark text
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS roles (
            id serial PRIMARY KEY,
            key text UNIQUE NOT NULL,
            name text NOT NULL,
            description text,
            routes jsonb NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id serial PRIMARY KEY,
            order_no text NOT NULL,
            timestamp bigint NOT NULL,
            username text NOT NULL,
            price numeric NOT NULL,
            status text NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id serial PRIMARY KEY,
            name text NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS account_records (
            id serial PRIMARY KEY,
            timestamp bigint NOT NULL,
            biz_date text,
            category text,
            client text,
            platform text,
            items text,
            unit_price numeric,
            quantity numeric DEFAULT 1,
            revenue numeric,
            cost numeric,
            profit numeric,
            status text DEFAULT 'pending',
            remark text,
            creator text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        ALTER TABLE account_records ADD COLUMN IF NOT EXISTS completed_at bigint
        """,
        """
        ALTER TABLE account_records ADD COLUMN IF NOT EXISTS platform text
        """,
        """
        ALTER TABLE account_records ADD COLUMN IF NOT EXISTS license_name text
        """,
        """
        ALTER TABLE account_records ADD COLUMN IF NOT EXISTS credit_code text
        """,
        """
        ALTER TABLE account_records ADD COLUMN IF NOT EXISTS legal_person text
        """,
        """
        ALTER TABLE account_records ADD COLUMN IF NOT EXISTS legal_id text
        """,
        """
        ALTER TABLE account_records ADD COLUMN IF NOT EXISTS phone text
        """,
        """
        CREATE TABLE IF NOT EXISTS account_items (
            id serial PRIMARY KEY,
            account_id integer NOT NULL REFERENCES account_records(id) ON DELETE CASCADE,
            license_name text,
            credit_code text,
            legal_person text,
            legal_id text,
            legal_phone text,
            biz_status text,
            tax_status text,
            items text,
            unit_price numeric,
            quantity numeric DEFAULT 1,
            revenue numeric,
            cost numeric,
            profit numeric,
            status text DEFAULT 'pending',
            completed_at bigint,
            remark text,
            sort integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS account_items_account_idx
        ON account_items (account_id, sort, id)
        """,
        """
        CREATE TABLE IF NOT EXISTS order_progress (
            id serial PRIMARY KEY,
            account_id integer NOT NULL REFERENCES account_records(id) ON DELETE CASCADE,
            step text NOT NULL,
            status text NOT NULL DEFAULT 'doing',
            note text,
            operator text,
            timestamp bigint NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        ALTER TABLE order_progress ADD COLUMN IF NOT EXISTS item_id integer
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_progress_item_fk') THEN
                ALTER TABLE order_progress
                ADD CONSTRAINT order_progress_item_fk
                FOREIGN KEY (item_id) REFERENCES account_items(id) ON DELETE CASCADE;
            END IF;
        END $$
        """,
        """
        CREATE INDEX IF NOT EXISTS order_progress_account_idx
        ON order_progress (account_id, timestamp DESC)
        """,
        # 跟进记录挂到具体细分任务上：主任务不再有独立时间线，每条记录跟着子任务走
        """
        ALTER TABLE order_progress ADD COLUMN IF NOT EXISTS task_id integer
        """,
        """
        CREATE TABLE IF NOT EXISTS cost_records (
            id serial PRIMARY KEY,
            timestamp bigint NOT NULL,
            biz_date text,
            category text,
            payee text,
            amount numeric NOT NULL DEFAULT 0,
            method text,
            related_order integer REFERENCES account_records(id) ON DELETE SET NULL,
            remark text,
            creator text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS cost_records_date_idx
        ON cost_records (timestamp DESC)
        """,
        """
        CREATE TABLE IF NOT EXISTS menus (
            id serial PRIMARY KEY,
            path text UNIQUE NOT NULL,
            title text NOT NULL,
            icon text DEFAULT '',
            parent text DEFAULT '',
            sort integer NOT NULL DEFAULT 0,
            visible boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS platforms (
            id serial PRIMARY KEY,
            name text UNIQUE NOT NULL,
            sort integer NOT NULL DEFAULT 0,
            remark text DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        # 业务项字典：订单里的业务项从这里多选组合，单价随配置带出
        """
        CREATE TABLE IF NOT EXISTS biz_items (
            id serial PRIMARY KEY,
            name text UNIQUE NOT NULL,
            unit_price numeric DEFAULT 0,
            remark text DEFAULT '',
            sort integer NOT NULL DEFAULT 0,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        # 价格配置：代办服务价目表，一行 = 一个服务项目（类别 + 适用条件 + 标准价 + 同行参考价）
        """
        CREATE TABLE IF NOT EXISTS price_items (
            id serial PRIMARY KEY,
            category text NOT NULL DEFAULT '',
            name text NOT NULL,
            condition text DEFAULT '',
            price numeric NOT NULL DEFAULT 0,
            peer_price numeric NOT NULL DEFAULT 0,
            remark text DEFAULT '',
            sort integer NOT NULL DEFAULT 0,
            active boolean NOT NULL DEFAULT true,
            updated_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS price_items_name_uidx ON price_items (name)
        """,
        # 价目表的说明文案（免责声明、特别提醒），跟具体项目分开存，可随时改
        """
        CREATE TABLE IF NOT EXISTS price_settings (
            key text PRIMARY KEY,
            value text DEFAULT '',
            updated_at timestamptz
        )
        """,
        # 税务状态文案调整：有税务 → 税务正常，历史数据一并归一
        """
        UPDATE account_items SET tax_status = '税务正常' WHERE tax_status = '有税务'
        """,
        # 工商状态改为多选：历史数据里的中文逗号/顿号/空格统一成英文逗号分隔
        # 空格按分隔符处理（状态名本身不含空格），空片段丢弃，重复执行无副作用
        """
        UPDATE account_items
           SET biz_status = array_to_string(
                   array_remove(
                       string_to_array(
                           regexp_replace(biz_status,
                                          '[[:space:]]*[,，、/|][[:space:]]*|[[:space:]]+',
                                          ',', 'g'),
                           ','
                       ), ''
                   ), ',')
         WHERE biz_status ~ '[，、/| ]'
        """,
        # 订单编号：DD + 录入日期（北京时间）+ 4 位订单 id，历史数据按录入时间回填
        """
        ALTER TABLE account_records ADD COLUMN IF NOT EXISTS order_no text
        """,
        """
        UPDATE account_records
           SET order_no = 'DD' || to_char(
                   to_timestamp(timestamp / 1000.0) AT TIME ZONE 'Asia/Shanghai',
                   'YYYYMMDD') || '-' || lpad(id::text, 4, '0')
         WHERE order_no IS NULL
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS account_records_order_no_uidx
        ON account_records (order_no)
        """,
        # 平台订单编号：人工填写的第三方渠道单号，可空
        """
        ALTER TABLE account_records ADD COLUMN IF NOT EXISTS platform_order_no text DEFAULT ''
        """,
        # 法人手机号：挂在每条执照上，不同执照法人可能不同
        """
        ALTER TABLE account_items ADD COLUMN IF NOT EXISTS legal_phone text
        """,
        # 主跟进人：任务（执照明细）的第一责任人，留空时按跟进记录自动推断
        """
        ALTER TABLE account_items ADD COLUMN IF NOT EXISTS owner text
        """,
        """
        ALTER TABLE account_items ADD COLUMN IF NOT EXISTS owner_updated_at bigint
        """,
        # 取消订单：记下取消原因、补充备注与取消时间，方便复盘和区分责任
        """
        ALTER TABLE account_items ADD COLUMN IF NOT EXISTS cancel_reason text DEFAULT ''
        """,
        """
        ALTER TABLE account_items ADD COLUMN IF NOT EXISTS cancel_note text DEFAULT ''
        """,
        """
        ALTER TABLE account_items ADD COLUMN IF NOT EXISTS cancelled_at bigint
        """,
        # 退款：累计退款金额与最近退款时间，收入在明细 revenue 上直接冲减
        """
        ALTER TABLE account_items ADD COLUMN IF NOT EXISTS refund_amount numeric DEFAULT 0
        """,
        """
        ALTER TABLE account_items ADD COLUMN IF NOT EXISTS refund_at bigint
        """,
        # 成本记录来源：kind='refund' 是订单退款自动生成的那条，
        # 它的金额已经在收入里冲减过，财务报表统计利润时不再重复计入支出
        """
        ALTER TABLE cost_records ADD COLUMN IF NOT EXISTS kind text DEFAULT ''
        """,
        # 订单的身份证照片 / 执照的执照照片：随订单一起存，录入和编辑时都能传
        """
        ALTER TABLE account_records ADD COLUMN IF NOT EXISTS id_photos jsonb DEFAULT '[]'::jsonb
        """,
        """
        ALTER TABLE account_items ADD COLUMN IF NOT EXISTS license_photos jsonb DEFAULT '[]'::jsonb
        """,
        # 客户微信：订单层面的联系方式，录入/编辑/详情都能看到，也支持按微信号搜索
        """
        ALTER TABLE account_records ADD COLUMN IF NOT EXISTS wechat text DEFAULT ''
        """,
        # 行业叫法统一：「同行业」→「同行」，老订单一起改名，报表按行业分组才不会裂成两类
        """
        UPDATE account_records SET category = '同行' WHERE category = '同行业'
        """,
        # 办理线附件：工商 / 税务每条线可上传图片（受理单、执照照片、办结截图等）
        """
        CREATE TABLE IF NOT EXISTS progress_files (
            id serial PRIMARY KEY,
            item_id integer NOT NULL,
            account_id integer NOT NULL,
            line text NOT NULL DEFAULT '',
            url text NOT NULL,
            name text DEFAULT '',
            size bigint DEFAULT 0,
            uploader text DEFAULT '',
            timestamp bigint
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS progress_files_item_idx ON progress_files (item_id, line)
        """,
        # 细分任务：一个执照（主任务）按业务项再拆一层，「工商注销」「税务非正常解除」各自独立办结；
        # 主任务行只看整单状态，展开后才看这些细分任务，互不干扰
        """
        CREATE TABLE IF NOT EXISTS account_item_tasks (
            id serial PRIMARY KEY,
            item_id integer NOT NULL REFERENCES account_items(id) ON DELETE CASCADE,
            account_id integer NOT NULL REFERENCES account_records(id) ON DELETE CASCADE,
            name text NOT NULL,
            line text NOT NULL DEFAULT 'other',
            status text NOT NULL DEFAULT 'pending',
            owner text DEFAULT '',
            note text DEFAULT '',
            done_at bigint,
            updated_at bigint,
            sort integer NOT NULL DEFAULT 0,
            -- 来源：item = 由业务项自动拆出来的（业务项改了会跟着同步），manual = 手工补的事项
            source text NOT NULL DEFAULT 'item',
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        ALTER TABLE account_item_tasks ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'item'
        """,
        """
        CREATE INDEX IF NOT EXISTS account_item_tasks_item_idx
        ON account_item_tasks (item_id, sort, id)
        """,
        """
        CREATE INDEX IF NOT EXISTS account_item_tasks_account_idx
        ON account_item_tasks (account_id)
        """,
        # 跟进记录 → 细分任务的外键（account_item_tasks 建好之后才能加）
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_progress_task_fk') THEN
                ALTER TABLE order_progress
                ADD CONSTRAINT order_progress_task_fk
                FOREIGN KEY (task_id) REFERENCES account_item_tasks(id) ON DELETE SET NULL;
            END IF;
        END $$
        """,
        """
        CREATE INDEX IF NOT EXISTS order_progress_task_idx
        ON order_progress (task_id, timestamp DESC)
        """,
        # 软删除：is_delete=0 正常 / 1 已删除，业务数据只标记不物理删除，误删可恢复
        """
        ALTER TABLE account_records ADD COLUMN IF NOT EXISTS is_delete smallint NOT NULL DEFAULT 0
        """,
        """
        ALTER TABLE account_items ADD COLUMN IF NOT EXISTS is_delete smallint NOT NULL DEFAULT 0
        """,
        """
        ALTER TABLE order_progress ADD COLUMN IF NOT EXISTS is_delete smallint NOT NULL DEFAULT 0
        """,
        """
        ALTER TABLE cost_records ADD COLUMN IF NOT EXISTS is_delete smallint NOT NULL DEFAULT 0
        """,
        """
        ALTER TABLE account_item_tasks ADD COLUMN IF NOT EXISTS is_delete smallint NOT NULL DEFAULT 0
        """,
        """
        COMMENT ON COLUMN account_records.is_delete IS '软删除标记：0=正常，1=已删除'
        """,
        """
        COMMENT ON COLUMN account_items.is_delete IS '软删除标记：0=正常，1=已删除'
        """,
        """
        COMMENT ON COLUMN order_progress.is_delete IS '软删除标记：0=正常，1=已删除'
        """,
        """
        COMMENT ON COLUMN cost_records.is_delete IS '软删除标记：0=正常，1=已删除'
        """,
        """
        COMMENT ON COLUMN account_item_tasks.is_delete IS '软删除标记：0=正常，1=已删除'
        """,
    ]
    with connect() as conn:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
            cur.execute("SELECT COUNT(*) FROM users")
            if cur.fetchone()[0] == 0:
                seed(cur)
            migrate_account_items(cur)
            # 子任务单价是后加的：只在第一次加列时按业务项价格回填一次，
            # 之后用户手工把某项改成 0 不会被启动流程再冲掉
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'account_item_tasks' AND column_name = 'amount'"
            )
            if cur.fetchone() is None:
                cur.execute(
                    "ALTER TABLE account_item_tasks ADD COLUMN amount numeric(12,2) NOT NULL DEFAULT 0"
                )
                cur.execute(
                    """
                    UPDATE account_item_tasks t
                       SET amount = b.unit_price
                      FROM biz_items b
                     WHERE t.name = b.name AND b.unit_price > 0
                    """
                )
            backfill_item_tasks(cur)
            linked = backfill_progress_task_links(cur)
            if linked:
                print("[startup] 跟进记录挂到细分任务：%d 条" % linked, flush=True)
            sync_account_route(cur)
            ensure_finance_route(cur)
            seed_menus(cur)
            seed_platforms(cur)
            seed_biz_items(cur)
            seed_prices(cur)
        # 订单状态以明细为准，顺手把历史上对不上的订单修正掉
        repair_order_statuses(conn)
        conn.commit()


# 系统内置页面 → 默认菜单项。菜单可在「菜单管理」里改名/改图标/排序/隐藏/删除，
# 但页面本体由前端路由提供，菜单只是这些页面的入口配置。
MENU_SEED = [
    ("/account/index", "订单管理", "money", "", 10),
    ("/account/query", "订单查询", "table", "", 20),
    ("/progress/index", "订单进度", "tree", "", 30),
    ("/price/index", "价格配置", "money", "", 35),
    ("/cost/index", "支出管理", "money", "", 40),
    ("/cost/query", "成本查询", "table", "", 50),
    ("/finance/report", "财务报表", "chart", "", 60),
    ("/system/user", "用户管理", "user", "/system", 110),
    ("/system/role", "角色管理", "lock", "/system", 120),
    ("/system/menu", "菜单管理", "list", "/system", 130),
    ("/system/platform", "平台管理", "shopping", "/system", 140),
    ("/system/bizitem", "业务项配置", "star", "/system", 150),
]

# 旧菜单路径 → 新菜单路径（升级时把存量行改名，避免 ON CONFLICT 撞旧路径）
MENU_RENAME = {
    "/platform/index": ("/system/platform", "平台管理", "shopping", "/system", 40),
    "/account/index": ("/account/index", "订单管理", "money", "", 10),
    "/cost/index": ("/cost/index", "支出管理", "money", "", 40),
}


# 平台字典的预置项（属于基础配置，不是业务数据，可在「平台管理」里增删改）
PLATFORM_SEED = ["微信", "抖音", "小红书", "淘宝", "拼多多", "京东", "线下"]


def seed_platforms(cur):
    for index, name in enumerate(PLATFORM_SEED):
        cur.execute(
            """
            INSERT INTO platforms (name, sort, remark)
            VALUES (%s, %s, %s)
            ON CONFLICT (name) DO NOTHING
            """,
            (name, (index + 1) * 10, "预置"),
        )


# 业务项字典的预置项。业务项是「原子项」，订单里多选后按 A+B 拼接，
# 所以这里只放单项，不放「解非+注销」这类组合。
BIZ_ITEM_SEED = [
    "工商注销",
    "税务注销",
    "解非",
    "税务非正常解除",
    "另册管理",
    "虚假地址",
    "挂靠地址明年注销",
    "年报补报",
    "年报异常解除",
    "地址异常解除",
    "有税",
    "无税",
    "变更登记",
]

ITEM_SPLIT_RE = re.compile(r"[+＋、,，/／|]+")


def split_biz_items(text):
    """把「解非+工商注销」拆成原子业务项，供下拉选择与使用次数统计共用。"""
    parts = []
    for piece in ITEM_SPLIT_RE.split(text or ""):
        name = piece.strip()
        if name and name not in parts:
            parts.append(name)
    return parts


def seed_biz_items(cur):
    # 预置项 + 历史订单里已经用过的业务项，一起导入字典，升级后立刻可复用
    names = list(BIZ_ITEM_SEED)
    cur.execute(
        "SELECT DISTINCT items FROM account_items"
        " WHERE COALESCE(items, '') <> '' AND is_delete = 0"
    )
    for row in cur.fetchall():
        for name in split_biz_items(row["items"] if isinstance(row, dict) else row[0]):
            if name not in names:
                names.append(name)
    for index, name in enumerate(names):
        cur.execute(
            """
            INSERT INTO biz_items (name, unit_price, remark, sort)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (name) DO NOTHING
            """,
            (name, 0, "预置", (index + 1) * 10),
        )


# 细分任务：执照（主任务）下按业务项拆出来的小任务，各自独立办结
TASK_STATUS_LABELS = {"pending": "未开始", "doing": "办理中", "done": "已办结", "cancelled": "已取消"}

# 细分任务归属哪条办理线：先判税务再判工商，「税务注销」不能被「注销」抢成工商线
TASK_LINE_RULES = [
    ("tax", ("税务", "解非", "非正常", "清税", "记账", "报税", "申报", "发票", "票种",
             "汇算", "欠税", "有税", "无税", "个税", "社保")),
    ("biz", ("工商", "执照", "注销", "注册", "变更", "地址", "年报", "刻章", "银行",
             "股权", "增资", "减资", "经营范围", "另册", "吊销", "挂靠", "虚假")),
]


def task_line_of(name):
    """业务项 → 办理线（biz / tax / other），只用于列表上打个小标签。"""
    text = str(name or "")
    for key, words in TASK_LINE_RULES:
        if any(word in text for word in words):
            return key
    return "other"


def task_out(row):
    return {
        "id": row["id"],
        "item_id": row["item_id"],
        "account_id": row["account_id"],
        "name": row["name"] or "",
        "line": row["line"] or "other",
        "status": row["status"] or "pending",
        "owner": row["owner"] or "",
        "note": row["note"] or "",
        "done_at": int(row["done_at"] or 0),
        "updated_at": int(row["updated_at"] or 0),
        "sort": int(row["sort"] or 0),
        "source": row.get("source") or "item",
        "amount": float(row.get("amount") or 0),
        "is_delete": int(row.get("is_delete") or 0),
    }


def fetch_item_tasks(cur, item_ids):
    """批量取细分任务，按 item_id 分组，列表页一次查完不做 N+1。"""
    ids = [int(i) for i in item_ids if i]
    if not ids:
        return {}
    cur.execute(
        "SELECT * FROM account_item_tasks WHERE item_id = ANY(%s) AND is_delete = 0 ORDER BY sort, id",
        (ids,),
    )
    grouped = {}
    for row in cur.fetchall():
        grouped.setdefault(row["item_id"], []).append(task_out(row))
    return grouped


def sync_item_tasks(cur, item_id, account_id, items_text, status="pending", owner=""):
    """按业务项同步细分任务：补新增的、删掉业务项已去掉的，已有的保留自己的办理状态。

    主任务标「已完成」时，细分任务一起置为已办结；主任务取消时细分任务跟着取消，
    改回正常状态时把取消的细分任务恢复成未开始。人工改过的细分任务状态不会被覆盖。
    """
    names = split_biz_items(items_text)
    # 这个方法两种游标下都会跑（启动迁移用普通游标，接口里用 RealDictCursor），
    # 先统一成元组，后面按位置取值就行
    cur.execute(
        "SELECT id, name, sort, source FROM account_item_tasks WHERE item_id = %s AND is_delete = 0 ORDER BY sort, id",
        (item_id,),
    )
    existing = {}
    for row in cur.fetchall():
        if isinstance(row, dict):
            row = (row["id"], row["name"], row["sort"], row.get("source"))
        existing.setdefault(row[1], []).append(row)
    stamp = now_ms()
    status = status or "pending"
    # 业务项自带单价：新建子任务时带过来做默认值，之后可在订单里单独改
    cur.execute("SELECT name, unit_price FROM biz_items")
    price_map = {}
    for row in cur.fetchall():
        if isinstance(row, dict):
            price_map[row["name"]] = float(row["unit_price"] or 0)
        else:
            price_map[row[0]] = float(row[1] or 0)
    for index, name in enumerate(names):
        rows = existing.get(name) or []
        if rows:
            row = rows.pop(0)
            if int(row[2] or 0) != index:
                cur.execute("UPDATE account_item_tasks SET sort = %s WHERE id = %s", (index, row[0]))
            continue
        done = status == "done"
        cur.execute(
            """
            INSERT INTO account_item_tasks
                   (item_id, account_id, name, line, status, owner, amount, done_at, updated_at, sort)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (item_id, account_id, name, task_line_of(name), "done" if done else "pending",
             owner or "", price_map.get(name, 0), stamp if done else None, stamp, index),
        )
    # 业务项被去掉的细分任务删掉；同名重复的历史行也一起清掉。手工补的事项不受业务项影响
    removed = [
        row[0] for rows in existing.values() for row in rows
        if (row[3] or "item") != "manual"
    ]
    if removed:
        cur.execute(
            "UPDATE account_item_tasks SET is_delete = 1 WHERE id = ANY(%s) AND is_delete = 0",
            (removed,),
        )
    # 主任务状态带着细分任务走：完成 → 全办结；取消 → 全取消；恢复 → 取消的回到未开始
    if status == "done":
        cur.execute(
            "UPDATE account_item_tasks SET status = 'done', done_at = COALESCE(done_at, %s), updated_at = %s"
            " WHERE item_id = %s AND status <> 'done'",
            (stamp, stamp, item_id),
        )
    elif status == "cancelled":
        cur.execute(
            "UPDATE account_item_tasks SET status = 'cancelled', updated_at = %s"
            " WHERE item_id = %s AND status <> 'done'",
            (stamp, item_id),
        )
    else:
        cur.execute(
            "UPDATE account_item_tasks SET status = 'pending', updated_at = %s"
            " WHERE item_id = %s AND status = 'cancelled'",
            (stamp, item_id),
        )


def apply_task_overrides(cur, item_id, tasks, operator=""):
    """把订单表单里逐条改过的子任务状态 / 单价写回去（新建和编辑都走这里）。

    tasks: [{"id": 可选, "name": "工商注销", "status": "done", "amount": 300, "owner": "张三"}]
    只处理能对上的名字，业务项里没有的名字忽略（手工补的另走接口）。
    带 owner 键时按表单里的选择覆盖（空串表示清空、改回跟随主任务）。
    """
    if not isinstance(tasks, list) or not tasks:
        return
    stamp = now_ms()
    cur.execute(
        "SELECT id, name, status, amount FROM account_item_tasks WHERE item_id = %s AND is_delete = 0 ORDER BY id",
        (item_id,),
    )
    rows = {}
    for row in cur.fetchall():
        if isinstance(row, dict):
            rows.setdefault(row["name"], []).append(row)
        else:
            rows.setdefault(row[1], []).append(
                {"id": row[0], "name": row[1], "status": row[2], "amount": row[3]}
            )
    for entry in tasks:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()[:60]
        if not name or name not in rows:
            continue
        row = rows[name].pop(0)
        status = entry.get("status")
        if status not in TASK_STATUS_LABELS:
            status = None
        amount = to_number(entry.get("amount"), None) if "amount" in entry else None
        if amount is not None and amount < 0:
            amount = 0
        # 表单里显式带了跟进人：按选择覆盖；没带就保持原样（不拿录单人顶替）
        owner_set = "owner" in entry
        owner = str(entry.get("owner") or "").strip()[:60]
        if status is None and amount is None and not owner_set:
            continue
        new_status = status or row["status"]
        new_amount = float(row["amount"] or 0) if amount is None else float(amount)
        cur.execute(
            """
            UPDATE account_item_tasks
               SET status = %s,
                   amount = %s,
                   done_at = CASE WHEN %s = 'done' THEN COALESCE(done_at, %s) ELSE NULL END,
                   owner = CASE WHEN %s THEN %s ELSE owner END,
                   updated_at = %s
             WHERE id = %s
            """,
            (new_status, round(new_amount, 2), new_status, stamp,
             owner_set, owner, stamp, row["id"]),
        )


def backfill_progress_task_links(cur):
    """老跟进记录没有 task_id：按办理线挂到该执照下第一条同线子任务。

    「已录入 / 状态变更 / 已完成」这类系统记录保持为空（新界面不再展示主任务级时间线）。
    按条判断，重复执行无副作用。
    """
    cur.execute(
        """
        UPDATE order_progress p
           SET task_id = (
               SELECT t.id FROM account_item_tasks t
                WHERE t.item_id = p.item_id AND t.is_delete = 0
                  AND t.line = CASE WHEN p.step LIKE '工商 · %' THEN 'biz' ELSE 'tax' END
                ORDER BY t.sort, t.id
                LIMIT 1
           )
         WHERE p.task_id IS NULL
           AND (p.step LIKE '工商 · %' OR p.step LIKE '税务 · %')
        """
    )
    return cur.rowcount


def backfill_item_tasks(cur):
    """老订单补细分任务：还没有细分任务的执照，按业务项拆一遍。"""
    cur.execute(
        """
        SELECT i.id, i.account_id, i.items, i.status, i.owner
          FROM account_items i
         WHERE COALESCE(i.items, '') <> '' AND i.is_delete = 0
           AND NOT EXISTS (SELECT 1 FROM account_item_tasks t WHERE t.item_id = i.id AND t.is_delete = 0)
        """
    )
    rows = cur.fetchall()
    for row in rows:
        # 普通游标，按位置取值
        sync_item_tasks(cur, row[0], row[1], row[2], row[3], row[4] or "")
    if rows:
        print("[startup] 补建细分任务：%d 条执照任务" % len(rows), flush=True)


# 价格配置的预置价目：来源是线下的《工商税务代办价格表》，
# 首次启动导入一次，之后完全由「价格设置」维护（改价、增删项目）。
PRICE_SEED = [
    ("税务注销", "税务注销（账务清晰、无欠税无异常）", "已按时申报、账册齐全、无未结事项", 150),
    ("税务注销", "税务注销（账务不规范 / 有漏申报）", "有漏报、错报、账册不全需补整", 300),
    ("税务注销", "税务注销（有欠税 / 滞纳金）", "存在欠缴税款、滞纳金、罚款", 400),
    ("解除非正常", "解除税务非正常户（仅补申报）", "被列为非正常户，仅需补逾期申报", 100),
    ("解除非正常", "解除非正常户（补申报 + 罚款）", "需补申报且缴罚款、滞纳金", 150),
    ("解除非正常", "解除非正常户（有欠税需清缴）", "欠税、罚款一并处理", 200),
    ("工商注销", "个体户简易注销（税务已清/无税务）", "无税务异常、无债权债务纠纷", 100),
    ("工商注销", "个体户一般注销", "需清算公示等一般流程", 300),
    ("工商注销", "有限公司简易注销（税务已清）", "未开业或无债权债务，公示20日", 500),
    ("工商注销", "有限公司一般注销", "需清算组备案、债权人公告45日", 800),
    ("工商注销", "吊销执照后注销", "执照已被吊销，需先处理处罚", 500),
    ("综合套餐", "个体户全包注销（税务+工商）", "正常状态、账务简单", 200),
    ("综合套餐", "有限公司全包注销（税务+工商+社保）", "账务清晰、无重大异常", 1000),
    ("综合套餐", "吊销企业全包注销", "已被吊销，需解除非正常+注销", 800),
    ("综合套餐", "解除非正常 + 注销一站式", "税务非正常户需先恢复再注销", 500),
    ("附加服务", "公章 / 其他资质注销", "公章、许可资质一并注销", 200),
]

# 类别顺序：价目表按这个顺序分组展示，新类别排在最后
PRICE_CATEGORY_ORDER = ["税务注销", "解除非正常", "工商注销", "综合套餐", "附加服务"]

PRICE_NOTICE = (
    "以下价格为参考价，仅作预算参考，非固定报价；不含政府部门规费、罚款、补缴税款等实报实销项目；"
    "个体户与有限公司、税务状态（正常/非正常）、营业收入不同，价格差异较大，以最终报价为准。"
)

PRICE_TIPS = "\n".join([
    "税务非正常户必须先补申报、缴清税款罚款解除异常后才能注销；",
    "吊销≠注销，执照被吊销仍须主动办理注销，否则法人/股东持续受限；",
    "财务负责人/法人实名备案，委托代办后责任仍在你本人，务必选择正规机构并签书面委托合同；",
    "所有实报实销费用（罚款、补税、规费、登报等）要求机构提前书面列明。",
])


def seed_prices(cur):
    """首次启动导入预置价目；已有数据时不动，避免把用户改过的价格覆盖回去。"""
    cur.execute("SELECT COUNT(*) FROM price_items")
    if cur.fetchone()[0] == 0:
        category_index = {name: index for index, name in enumerate(PRICE_CATEGORY_ORDER)}
        counters = {}
        for category, name, condition, price in PRICE_SEED:
            counters[category] = counters.get(category, 0) + 10
            cur.execute(
                """
                INSERT INTO price_items
                       (category, name, condition, price, peer_price, remark, sort, active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (name) DO NOTHING
                """,
                (
                    category, name, condition, price, price, "",
                    (category_index.get(category, 99) + 1) * 1000 + counters[category],
                ),
            )
    for key, value in (("notice", PRICE_NOTICE), ("tips", PRICE_TIPS)):
        cur.execute(
            """
            INSERT INTO price_settings (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO NOTHING
            """,
            (key, value),
        )


def seed_menus(cur):
    for old_path, (path, title, icon, parent, sort) in MENU_RENAME.items():
        cur.execute(
            """
            UPDATE menus
               SET path = %s, title = %s, icon = %s, parent = %s, sort = %s
             WHERE path = %s
            """,
            (path, title, icon, parent, sort, old_path),
        )
    for path, title, icon, parent, sort in MENU_SEED:
        # 归位分组与排序（不覆盖用户可能改过的标题/图标/显示开关）
        cur.execute(
            "UPDATE menus SET parent = %s, sort = %s WHERE path = %s",
            (parent, sort, path),
        )
        cur.execute(
            """
            INSERT INTO menus (path, title, icon, parent, sort, visible)
            VALUES (%s, %s, %s, %s, %s, TRUE)
            ON CONFLICT (path) DO NOTHING
            """,
            (path, title, icon, parent, sort),
        )


def sync_account_route(cur):
    try:
        routes = json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    entry = next((item for item in routes if item.get("path") == "/account"), None)
    if entry is None:
        return
    cur.execute("SELECT key, routes FROM roles WHERE key IN ('admin', 'editor')")
    for key, role_routes in cur.fetchall():
        items = role_routes if isinstance(role_routes, list) else []
        if any(item.get("path") == "/account" for item in items):
            continue
        cur.execute("UPDATE roles SET routes = %s WHERE key = %s", (Json(items + [entry]), key))


def ensure_finance_route(cur):
    """升级迁移：财务报表上线后，把 /finance 条目补进 admin/editor 的角色路由（visitor 不给）。"""
    try:
        routes = json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    entry = next((item for item in routes if item.get("path") == "/finance"), None)
    if entry is None:
        return
    cur.execute("SELECT key, routes FROM roles WHERE key IN ('admin', 'editor')")
    for key, role_routes in cur.fetchall():
        items = role_routes if isinstance(role_routes, list) else []
        if any(item.get("path") == "/finance" for item in items):
            continue
        cur.execute("UPDATE roles SET routes = %s WHERE key = %s", (Json(items + [entry]), key))


def seed(cur):
    avatar = "https://wpimg.wallstcn.com/f778738c-e4f8-4870-b634-56703b4acafe.gif"
    users = [
        ("admin", "admin123", "Super Admin", avatar, "I am a super administrator", ["admin"]),
        ("editor", "editor123", "Normal Editor", avatar, "I am an editor", ["editor"]),
    ]
    for username, password, name, avatar, introduction, roles in users:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, name, avatar, introduction, roles)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (username, hash_password(password), name, avatar, introduction, roles),
        )

    routes = json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
    editor_routes = [item for item in routes if item.get("path") != "/permission"]
    visitor_routes = [{
        "path": "",
        "redirect": "dashboard",
        "children": [{
            "path": "dashboard",
            "name": "Dashboard",
            "meta": {"title": "dashboard", "icon": "dashboard"},
        }],
    }]
    roles = [
        ("admin", "admin", "Super Administrator. Have access to view all pages.", routes),
        ("editor", "editor", "Normal Editor. Can see all pages except permission page", editor_routes),
        ("visitor", "visitor", "Just a visitor. Can only see the home page and the document page", visitor_routes),
    ]
    for key, name, description, role_routes in roles:
        cur.execute(
            "INSERT INTO roles (key, name, description, routes) VALUES (%s, %s, %s, %s)",
            (key, name, description, Json(role_routes)),
        )

    articles = [
        ("Quarterly revenue review", "CN", "published", 3, 1860),
        ("Mobile checkout experiment", "US", "published", 2, 980),
        ("Spring campaign brief", "JP", "draft", 1, 240),
        ("EU warehouse capacity", "EU", "published", 2, 1320),
        ("Editor handbook update", "CN", "draft", 1, 86),
        ("Membership renewal report", "US", "published", 3, 2540),
        ("Support ticket summary", "JP", "published", 1, 640),
        ("Pricing page revision", "EU", "draft", 2, 150),
    ]
    base = now_ms() - 10 * 24 * 3600 * 1000
    for index, (title, region, status, importance, pageviews) in enumerate(articles):
        stamp = base + index * 3600 * 1000 * 8
        cur.execute(
            """
            INSERT INTO articles (
                timestamp, author, reviewer, title, content_short, content, forecast,
                importance, type, status, display_time, comment_disabled, pageviews,
                image_uri, platforms, source_uri, remark
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                stamp,
                "admin" if index % 2 == 0 else "editor",
                "reviewer",
                title,
                title,
                "<p>%s</p>" % title,
                round(10 + index * 3.5, 2),
                importance,
                region,
                status,
                datetime.fromtimestamp(stamp / 1000, timezone.utc),
                False,
                pageviews,
                "",
                Json(["a-platform"]),
                "",
                "",
            ),
        )

    orders = [
        ("Alicia Chen", 1280, "success"),
        ("Noah Patel", 860.5, "pending"),
        ("Mia Rossi", 2460, "success"),
        ("Ethan Brooks", 320, "pending"),
        ("Sofia Kim", 1999, "success"),
        ("Liam Garcia", 540.25, "success"),
        ("Emma Novak", 4300, "pending"),
        ("Oliver Sato", 760, "success"),
    ]
    for index, (username, price, status) in enumerate(orders):
        cur.execute(
            "INSERT INTO transactions (order_no, timestamp, username, price, status) VALUES (%s,%s,%s,%s,%s)",
            (secrets.token_hex(16), now_ms() - index * 7200 * 1000, username, price, status),
        )

    for name in ["admin", "editor", "Alicia Chen", "Noah Patel", "Mia Rossi", "Ethan Brooks", "Sofia Kim", "Liam Garcia"]:
        cur.execute("INSERT INTO contacts (name) VALUES (%s)", (name,))


class App(BaseHTTPRequestHandler):
    server_version = "vue-admin-api/1.0"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PUT(self):
        self.route("PUT")

    def do_DELETE(self):
        self.route("DELETE")

    def route(self, method):
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            if path.startswith("/uploads/") and method == "GET":
                self.serve_upload(path)
                return
            if path == "/health" and method == "GET":
                self.send_json({"code": 20000, "data": "ok"})
                return
            body = self.read_body() if method in ("POST", "PUT") else {}
            if path != "/vue-element-admin/user/login":
                user = self.current_user(query)
                if user is None and path != "/health":
                    # 带了 token 却查不到 = 被同一账号在别处登录顶下线
                    has_token = bool(self.headers.get("X-Token") or query.get("token"))
                    message = (
                        "该账号已在其他设备登录，当前会话已下线，请重新登录"
                        if has_token else "登录已失效，请重新登录"
                    )
                    self.send_json({"code": 50008, "message": message})
                    return
            else:
                user = None
            self.dispatch(method, path, query, body, user)
        except Exception as exc:
            print("ERROR", exc, flush=True)
            traceback.print_exc()
            self.send_json({"code": 50000, "message": "Server error"})

    def dispatch(self, method, path, query, body, user):
        if path == "/vue-element-admin/user/login" and method == "POST":
            self.login(body)
        elif path == "/vue-element-admin/user/ping" and method == "GET":
            # 会话心跳专用：只校验 token 是否还有效，不查库、不带业务数据
            self.send_json({"code": 20000, "data": "ok"})
        elif path == "/vue-element-admin/user/info" and method == "GET":
            self.user_info(user)
        elif path == "/vue-element-admin/user/logout" and method == "POST":
            self.logout()
        elif path == "/vue-element-admin/user/list" and method == "GET":
            self.user_list(query, user)
        elif path == "/vue-element-admin/user/create" and method == "POST":
            self.user_create(body, user)
        elif path == "/vue-element-admin/user/update" and method == "POST":
            self.user_update(body, user)
        elif path == "/vue-element-admin/user/delete" and method == "POST":
            self.user_delete(body, user)
        elif path == "/vue-element-admin/article/list" and method == "GET":
            self.article_list(query)
        elif path == "/vue-element-admin/article/detail" and method == "GET":
            self.article_detail(query)
        elif path == "/vue-element-admin/article/pv" and method == "GET":
            self.article_pv()
        elif path == "/vue-element-admin/article/create" and method == "POST":
            self.article_create(body, user)
        elif path == "/vue-element-admin/article/update" and method == "POST":
            self.article_update(body)
        elif path == "/vue-element-admin/article/delete" and method == "POST":
            self.article_delete(body)
        elif path == "/vue-element-admin/routes" and method == "GET":
            self.routes()
        elif path == "/vue-element-admin/roles" and method == "GET":
            self.roles()
        elif path == "/vue-element-admin/role" and method == "POST":
            self.role_create(body, user)
        elif path.startswith("/vue-element-admin/role/") and method == "PUT":
            self.role_update(path.rsplit("/", 1)[-1], body, user)
        elif path.startswith("/vue-element-admin/role/") and method == "DELETE":
            self.role_delete(path.rsplit("/", 1)[-1], user)
        elif path == "/vue-element-admin/menu/list" and method == "GET":
            self.menu_list()
        elif path == "/vue-element-admin/menu/create" and method == "POST":
            self.menu_create(body, user)
        elif path == "/vue-element-admin/menu/update" and method == "POST":
            self.menu_update(body, user)
        elif path == "/vue-element-admin/menu/delete" and method == "POST":
            self.menu_delete(body, user)
        elif path == "/vue-element-admin/platform/list" and method == "GET":
            self.platform_list(query)
        elif path == "/vue-element-admin/platform/create" and method == "POST":
            self.platform_create(body, user)
        elif path == "/vue-element-admin/platform/update" and method == "POST":
            self.platform_update(body, user)
        elif path == "/vue-element-admin/platform/delete" and method == "POST":
            self.platform_delete(body, user)
        elif path == "/vue-element-admin/bizitem/list" and method == "GET":
            self.bizitem_list(query)
        elif path == "/vue-element-admin/bizitem/create" and method == "POST":
            self.bizitem_create(body, user)
        elif path == "/vue-element-admin/bizitem/update" and method == "POST":
            self.bizitem_update(body, user)
        elif path == "/vue-element-admin/bizitem/delete" and method == "POST":
            self.bizitem_delete(body, user)
        elif path == "/vue-element-admin/price/list" and method == "GET":
            self.price_list(query)
        elif path == "/vue-element-admin/price/create" and method == "POST":
            self.price_create(body, user)
        elif path == "/vue-element-admin/price/update" and method == "POST":
            self.price_update(body, user)
        elif path == "/vue-element-admin/price/delete" and method == "POST":
            self.price_delete(body, user)
        elif path == "/vue-element-admin/price/settings" and method == "POST":
            self.price_save_settings(body, user)
        elif path == "/vue-element-admin/search/user" and method == "GET":
            self.search_user(query)
        elif path == "/vue-element-admin/transaction/list" and method == "GET":
            self.transactions()
        elif path == "/vue-element-admin/account/list" and method == "GET":
            self.account_list(query)
        elif path == "/vue-element-admin/account/detail" and method == "GET":
            self.account_detail(query)
        elif path == "/vue-element-admin/account/summary" and method == "GET":
            self.account_summary(query)
        elif path == "/vue-element-admin/dashboard/overview" and method == "GET":
            self.dashboard_overview()
        elif path == "/vue-element-admin/account/create" and method == "POST":
            self.account_create(body, user)
        elif path == "/vue-element-admin/account/update" and method == "POST":
            self.account_update(body, user)
        elif path == "/vue-element-admin/account/delete" and method == "POST":
            self.account_delete(body)
        elif path == "/vue-element-admin/account/refund" and method == "POST":
            self.account_refund(body, user)
        elif path == "/vue-element-admin/account/cancel" and method == "POST":
            self.account_cancel(body, user)
        elif path == "/vue-element-admin/account/progress/list" and method == "GET":
            self.progress_list(query)
        elif path == "/vue-element-admin/account/progress/overview" and method == "GET":
            self.progress_overview(query)
        elif path == "/vue-element-admin/account/progress/summary" and method == "GET":
            self.progress_summary()
        elif path == "/vue-element-admin/account/progress/owners" and method == "GET":
            self.progress_owners()
        elif path == "/vue-element-admin/account/progress/files" and method == "GET":
            self.progress_files_list(query)
        elif path == "/vue-element-admin/account/progress/files/add" and method == "POST":
            self.progress_file_add(body, user)
        elif path == "/vue-element-admin/account/progress/files/delete" and method == "POST":
            self.progress_file_delete(body)
        elif path == "/vue-element-admin/finance/report" and method == "GET":
            self.finance_report(query)
        elif path == "/vue-element-admin/account/progress/create" and method == "POST":
            self.progress_create(body, user)
        elif path == "/vue-element-admin/account/progress/owner" and method == "POST":
            self.progress_owner_set(body, user)
        elif path == "/vue-element-admin/account/progress/tasks" and method == "GET":
            self.progress_tasks_list(query)
        elif path == "/vue-element-admin/account/progress/tasks/status" and method == "POST":
            self.progress_task_status(body, user)
        elif path == "/vue-element-admin/account/progress/tasks/add" and method == "POST":
            self.progress_task_add(body, user)
        elif path == "/vue-element-admin/account/progress/tasks/delete" and method == "POST":
            self.progress_task_delete(body, user)
        elif path == "/vue-element-admin/account/progress/tasks/owner" and method == "POST":
            self.progress_task_owner(body, user)
        elif path == "/vue-element-admin/account/progress/delete" and method == "POST":
            self.progress_delete(body, user)
        elif path == "/vue-element-admin/account/progress/refund" and method == "POST":
            self.progress_refund(body, user)
        elif path == "/vue-element-admin/account/progress/cancel" and method == "POST":
            self.progress_cancel(body, user)
        elif path == "/vue-element-admin/cost/list" and method == "GET":
            self.cost_list(query)
        elif path == "/vue-element-admin/cost/summary" and method == "GET":
            self.cost_summary(query)
        elif path == "/vue-element-admin/cost/create" and method == "POST":
            self.cost_create(body, user)
        elif path == "/vue-element-admin/cost/update" and method == "POST":
            self.cost_update(body)
        elif path == "/vue-element-admin/cost/delete" and method == "POST":
            self.cost_delete(body)
        elif path == "/vue-element-admin/cost/restore" and method == "POST":
            self.cost_restore(body)
        elif path == "/upload" and method == "POST":
            self.upload(body)
        elif path == "/qiniu/upload/token" and method == "GET":
            name = secrets.token_hex(8)
            self.send_json({"code": 20000, "data": {"qiniu_key": name, "qiniu_token": "local", "qiniu_url": "/uploads/" + name}})
        else:
            self.send_json({"code": 50000, "message": "Not found"})

    def login(self, body):
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE username = %s", (username,))
                row = cur.fetchone()
                if row is None or not verify_password(password, row["password_hash"]):
                    self.send_json({"code": 60204, "message": "Account and password are incorrect."})
                    return
                token = secrets.token_urlsafe(32)
                # 单点登录：同一账号只保留最新一次登录的会话，旧设备的 token 立即作废
                cur.execute("DELETE FROM sessions WHERE user_id = %s", (row["id"],))
                cur.execute("INSERT INTO sessions (token, user_id) VALUES (%s, %s)", (token, row["id"]))
            conn.commit()
            # 登录成功直接带回用户信息与菜单，前端不必再串行请求 user/info、menu/list，
            # 每次往返约一个网络 RTT，省掉这两次能明显缩短登录等待
            menus = []
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM menus ORDER BY parent ASC, sort ASC, id ASC")
                    menus = [menu_out(item) for item in cur.fetchall()]
            except Exception:
                menus = []
        self.send_json({
            "code": 20000,
            "data": {
                "token": token,
                "user": {
                    "id": row["id"],
                    "username": row["username"],
                    "roles": list(row["roles"] or []),
                    "name": row["name"] or "",
                    "avatar": row["avatar"] or "",
                    "introduction": row["introduction"] or "",
                },
                "menus": menus,
            },
        })

    def user_info(self, user):
        # 顺带把菜单带回去：刷新页面时前端就不用再单独请求 /menu/list，少一次跨网络往返
        menus = []
        try:
            with connect() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM menus ORDER BY parent ASC, sort ASC, id ASC")
                    menus = [menu_out(item) for item in cur.fetchall()]
        except Exception:
            menus = []
        self.send_json({
            "code": 20000,
            "data": {
                "id": user["id"],
                "username": user["username"],
                "roles": list(user["roles"]),
                "introduction": user["introduction"] or "",
                "avatar": user["avatar"] or "",
                "name": user["name"],
                "menus": menus,
            },
        })

    def logout(self):
        token = self.headers.get("X-Token")
        if token:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM sessions WHERE token = %s", (token,))
                conn.commit()
        self.send_json({"code": 20000, "data": "success"})

    def current_user(self, query):
        token = self.headers.get("X-Token") or query.get("token")
        if not token:
            return None
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT users.* FROM sessions
                    JOIN users ON users.id = sessions.user_id
                    WHERE sessions.token = %s
                    """,
                    (token,),
                )
                return cur.fetchone()

    @staticmethod
    def is_admin(user):
        return bool(user) and "admin" in list(user["roles"] or [])

    def deny(self, message="没有权限执行该操作"):
        self.send_json({"code": 50000, "message": message})

    def user_list(self, query, user):
        if not self.is_admin(user):
            self.deny("仅管理员可查看用户列表")
            return
        where = []
        params = []
        keyword = (query.get("keyword") or "").strip()
        if keyword:
            where.append("(username ILIKE %s OR name ILIKE %s)")
            params.extend(["%" + keyword + "%", "%" + keyword + "%"])
        role = (query.get("role") or "").strip()
        if role:
            where.append("%s = ANY(roles)")
            params.append(role)
        condition = (" WHERE " + " AND ".join(where)) if where else ""
        page = max(int(query.get("page") or 1), 1)
        limit = min(max(int(query.get("limit") or 20), 1), 200)
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) AS total FROM users" + condition, params)
                total = cur.fetchone()["total"]
                cur.execute(
                    "SELECT * FROM users" + condition + " ORDER BY id ASC LIMIT %s OFFSET %s",
                    params + [limit, (page - 1) * limit],
                )
                items = [user_out(row) for row in cur.fetchall()]

                cur.execute("SELECT DISTINCT unnest(roles) AS role FROM users ORDER BY role")
                role_options = [row["role"] for row in cur.fetchall()]
                cur.execute("SELECT key, name FROM roles ORDER BY id")
                role_meta = [{"key": row["key"], "name": row["name"]} for row in cur.fetchall()]
        self.send_json({
            "code": 20000,
            "data": {"total": total, "items": items, "roles": role_meta or role_options},
        })

    def user_create(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可新增用户")
            return
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        if not username or len(password) < 6:
            self.send_json({"code": 60204, "message": "账号不能为空，密码至少 6 位"})
            return
        # 与登录页一致的账号格式：字母或数字开头，2-32 位字母/数字/下划线/短横线
        if not USERNAME_PATTERN.match(username):
            self.send_json({
                "code": 60204,
                "message": "账号格式不正确：2-32 位字母、数字、下划线，且不能以符号开头",
            })
            return
        roles = body.get("roles") or []
        if isinstance(roles, str):
            roles = [roles]
        roles = [str(item) for item in roles if str(item).strip()]
        if not roles:
            self.send_json({"code": 60204, "message": "请至少选择一个角色"})
            return
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
                if cur.fetchone():
                    self.send_json({"code": 60204, "message": "该账号已存在"})
                    return
                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, name, avatar, introduction, roles)
                    VALUES (%s, %s, %s, %s, %s, %s) RETURNING *
                    """,
                    (
                        username,
                        hash_password(password),
                        (body.get("name") or username).strip(),
                        body.get("avatar") or "",
                        body.get("introduction") or "",
                        roles,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        self.send_json({"code": 20000, "data": user_out(row)})

    def user_update(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可修改用户")
            return
        user_id = int(body.get("id") or 0)
        roles = body.get("roles")
        if roles is not None:
            if isinstance(roles, str):
                roles = [roles]
            roles = [str(item) for item in roles if str(item).strip()]
            if not roles:
                self.send_json({"code": 60204, "message": "请至少选择一个角色"})
                return
            if user_id == user["id"] and "admin" not in roles:
                self.send_json({"code": 60204, "message": "不能取消自己的管理员角色"})
                return
        password = body.get("password") or ""
        if password and len(password) < 6:
            self.send_json({"code": 60204, "message": "密码至少 6 位"})
            return
        assignments = []
        params = []
        for column in ("name", "avatar", "introduction"):
            if column in body:
                assignments.append(column + " = %s")
                params.append(body.get(column) or "")
        if roles is not None:
            assignments.append("roles = %s")
            params.append(roles)
        if password:
            assignments.append("password_hash = %s")
            params.append(hash_password(password))
        if not assignments:
            self.send_json({"code": 50000, "message": "没有需要修改的内容"})
            return
        params.append(user_id)
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "UPDATE users SET " + ", ".join(assignments) + " WHERE id = %s RETURNING *",
                    params,
                )
                row = cur.fetchone()
                if row is None:
                    self.send_json({"code": 50000, "message": "用户不存在"})
                    return
                if password:
                    # 改密后让该用户已有登录态失效
                    cur.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
            conn.commit()
        self.send_json({"code": 20000, "data": user_out(row)})

    def user_delete(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可删除用户")
            return
        user_id = int(body.get("id") or 0)
        if user_id == user["id"]:
            self.send_json({"code": 60204, "message": "不能删除当前登录账号"})
            return
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                target = cur.fetchone()
                if target is None:
                    self.send_json({"code": 50000, "message": "用户不存在"})
                    return
                if "admin" in list(target["roles"] or []):
                    cur.execute("SELECT COUNT(*) AS cnt FROM users WHERE 'admin' = ANY(roles)")
                    if cur.fetchone()["cnt"] <= 1:
                        self.send_json({"code": 60204, "message": "至少保留一个管理员账号"})
                        return
                cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
        self.send_json({"code": 20000, "data": "success"})

    def article_list(self, query):
        where = []
        params = []
        importance = query.get("importance")
        if importance not in (None, "", "0"):
            where.append("importance = %s")
            params.append(int(importance))
        if query.get("type"):
            where.append("type = %s")
            params.append(query["type"])
        if query.get("title"):
            where.append("title ILIKE %s")
            params.append("%" + query["title"] + "%")
        sql = "SELECT * FROM articles"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC" if query.get("sort") == "-id" else " ORDER BY id ASC"
        page = max(int(query.get("page") or 1), 1)
        limit = min(max(int(query.get("limit") or 20), 1), 200)
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) AS total FROM articles" + (" WHERE " + " AND ".join(where) if where else ""), params)
                total = cur.fetchone()["total"]
                cur.execute(sql + " LIMIT %s OFFSET %s", params + [limit, (page - 1) * limit])
                items = [article_out(row) for row in cur.fetchall()]
        self.send_json({"code": 20000, "data": {"total": total, "items": items}})

    def article_detail(self, query):
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM articles WHERE id = %s", (int(query.get("id") or 0),))
                row = cur.fetchone()
        if row is None:
            self.send_json({"code": 50000, "message": "Article not found"})
            return
        self.send_json({"code": 20000, "data": article_out(row)})

    def article_pv(self):
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COALESCE(type, 'unknown') AS key, COALESCE(SUM(pageviews), 0) AS pv FROM articles GROUP BY type ORDER BY type")
                rows = [{"key": row["key"], "pv": int(row["pv"])} for row in cur.fetchall()]
        self.send_json({"code": 20000, "data": {"pvData": rows}})

    def article_values(self, body, user, existing=None):
        stamp = parse_ms(body.get("timestamp", existing["timestamp"] if existing else None))
        values = {
            "timestamp": stamp,
            "author": body.get("author", existing["author"] if existing else (user["username"] if user else "")),
            "reviewer": body.get("reviewer", existing["reviewer"] if existing else ""),
            "title": body.get("title", existing["title"] if existing else ""),
            "content_short": body.get("content_short", existing["content_short"] if existing else ""),
            "content": body.get("content", existing["content"] if existing else ""),
            "forecast": body.get("forecast", existing["forecast"] if existing else 0) or 0,
            "importance": int(body.get("importance", existing["importance"] if existing else 1) or 0),
            "type": body.get("type", existing["type"] if existing else ""),
            "status": body.get("status", existing["status"] if existing else "draft"),
            "display_time": parse_display(body.get("display_time"), stamp) if "display_time" in body or existing is None else existing["display_time"],
            "comment_disabled": as_bool(body.get("comment_disabled", existing["comment_disabled"] if existing else False)),
            "pageviews": int(body.get("pageviews", existing["pageviews"] if existing else 0) or 0),
            "image_uri": body.get("image_uri", existing["image_uri"] if existing else "") or "",
            "platforms": body.get("platforms", existing["platforms"] if existing else ["a-platform"]) or [],
            "source_uri": body.get("source_uri", existing["source_uri"] if existing else "") or "",
            "remark": body.get("remark", existing["remark"] if existing else "") or "",
        }
        return values

    def article_create(self, body, user):
        values = self.article_values(body, user)
        columns = ARTICLE_FIELDS
        params = []
        for column in columns:
            value = values[column]
            if column == "platforms":
                value = Json(value)
            params.append(value)
        sql = "INSERT INTO articles (" + ", ".join(columns) + ") VALUES (" + ", ".join(["%s"] * len(columns)) + ") RETURNING *"
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
            conn.commit()
        self.send_json({"code": 20000, "data": article_out(row)})

    def article_update(self, body):
        article_id = int(body.get("id") or 0)
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM articles WHERE id = %s", (article_id,))
                existing = cur.fetchone()
                if existing is None:
                    self.send_json({"code": 50000, "message": "Article not found"})
                    return
                values = self.article_values(body, None, existing)
                assignments = []
                params = []
                for column in ARTICLE_FIELDS:
                    if column not in body and column != "timestamp":
                        continue
                    value = values[column]
                    if column == "platforms":
                        value = Json(value)
                    assignments.append(column + " = %s")
                    params.append(value)
                if not assignments:
                    self.send_json({"code": 20000, "data": article_out(existing)})
                    return
                params.append(article_id)
                sql = "UPDATE articles SET " + ", ".join(assignments) + " WHERE id = %s RETURNING *"
                cur.execute(sql, params)
                row = cur.fetchone()
            conn.commit()
        self.send_json({"code": 20000, "data": article_out(row)})

    def article_delete(self, body):
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM articles WHERE id = %s", (int(body.get("id") or 0),))
            conn.commit()
        self.send_json({"code": 20000, "data": "success"})

    def account_list(self, query):
        # 已删除的订单不出现在列表与总数里
        where = ["a.is_delete = 0"]
        params = []
        if query.get("keyword"):
            keyword = "%" + query["keyword"] + "%"
            where.append(
                "(a.client ILIKE %s OR a.items ILIKE %s OR a.category ILIKE %s OR a.remark ILIKE %s"
                " OR a.phone ILIKE %s OR a.wechat ILIKE %s OR a.order_no ILIKE %s OR a.platform_order_no ILIKE %s"
                " OR EXISTS (SELECT 1 FROM account_items i WHERE i.account_id = a.id"
                " AND i.is_delete = 0 AND ("
                " i.license_name ILIKE %s OR i.credit_code ILIKE %s OR i.legal_person ILIKE %s"
                " OR i.legal_phone ILIKE %s OR i.items ILIKE %s)))"
            )
            params.extend([keyword] * 13)
        if query.get("status"):
            where.append("a.status = %s")
            params.append(query["status"])
        if query.get("category"):
            # 首页「收入构成」里未填行业的归为「未分类」，用 __empty__ 表示空值
            if query["category"] == "__empty__":
                where.append("COALESCE(TRIM(a.category), '') = ''")
            else:
                where.append("a.category = %s")
                params.append(query["category"])
        if query.get("platform"):
            where.append("a.platform = %s")
            params.append(query["platform"])
        if query.get("biz_status"):
            # 工商状态可多选，库里是「正常,另册管理」这类逗号串，按元素命中
            where.append(
                "EXISTS (SELECT 1 FROM account_items i WHERE i.account_id = a.id"
                " AND i.is_delete = 0"
                " AND %s = ANY(string_to_array(COALESCE(i.biz_status, ''), ',')))"
            )
            params.append(query["biz_status"])
        if query.get("tax_status"):
            where.append(
                "EXISTS (SELECT 1 FROM account_items i WHERE i.account_id = a.id"
                " AND i.is_delete = 0 AND i.tax_status = %s)"
            )
            params.append(query["tax_status"])
        page = max(int(query.get("page") or 1), 1)
        limit = min(max(int(query.get("limit") or 20), 1), 200)
        month_key = str(query.get("month") or "").strip()
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if month_key:
                    # 已办结订单按完成月（与首页卡片一致），未办结订单按下单月，
                    # 否则选了本月 + 进行中时，进行中的订单因为没有完成月会被全部筛掉
                    match_ids = account_month_ids(cur, month_key)
                    where.append("a.id = ANY(%s)")
                    params.append(match_ids)
                condition = " WHERE " + " AND ".join(where) if where else ""
                cur.execute("SELECT COUNT(*) AS total FROM account_records a" + condition, params)
                total = cur.fetchone()["total"]
                cur.execute(
                    "SELECT * FROM account_records a" + condition + " ORDER BY a.id DESC LIMIT %s OFFSET %s",
                    params + [limit, (page - 1) * limit],
                )
                rows = cur.fetchall()
                grouped = fetch_details(cur, [row["id"] for row in rows])
                items = [account_out(row, grouped.get(row["id"], [])) for row in rows]
        self.send_json({"code": 20000, "data": {"total": total, "items": items}})

    def account_detail(self, query):
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM account_records WHERE id = %s AND is_delete = 0",
                    (int(query.get("id") or 0),),
                )
                row = cur.fetchone()
                if row is None:
                    self.send_json({"code": 50000, "message": "Record not found"})
                    return
                grouped = fetch_details(cur, [row["id"]])
        self.send_json({"code": 20000, "data": account_out(row, grouped.get(row["id"], []))})

    def account_summary(self, query=None):
        where = ["is_delete = 0"]
        params = []
        # 顶部汇总卡的月份筛选与列表、首页卡片统一按「完成月」（ms_month_key）归集
        month_key = str((query or {}).get("month") or "").strip()
        match_ids = None
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if month_key:
                    # 与列表完全一致：已办结按完成月，未办结按下单月
                    match_ids = account_month_ids(cur, month_key)
                    if match_ids:
                        where.append("id = ANY(%s)")
                        params.append(match_ids)
                    else:
                        where.append("1 = 0")
                where_sql = " WHERE " + " AND ".join(where)
                cur.execute(
                    """
                    SELECT COUNT(*) AS count,
                           COALESCE(SUM(revenue), 0) AS revenue,
                           COALESCE(SUM(cost), 0) AS cost,
                           COALESCE(SUM(COALESCE(profit, 0)), 0) AS profit,
                           COUNT(*) FILTER (WHERE profit IS NULL) AS pending,
                           -- 已完成订单口径：执照主任务全部办结的订单才计入总收入
                           COUNT(*) FILTER (WHERE status = 'done') AS done_count,
                           COALESCE(SUM(revenue) FILTER (WHERE status = 'done'), 0) AS done_revenue,
                           COALESCE(SUM(cost) FILTER (WHERE status = 'done'), 0) AS done_cost,
                           COALESCE(SUM(COALESCE(profit, 0)) FILTER (WHERE status = 'done'), 0) AS done_profit
                    FROM account_records
                    """ + where_sql,
                    params,
                )
                row = cur.fetchone()
        self.send_json({
            "code": 20000,
            "data": {
                "count": int(row["count"] or 0),
                "revenue": float(row["revenue"] or 0),
                "cost": float(row["cost"] or 0),
                "profit": float(row["profit"] or 0),
                "pending": int(row["pending"] or 0),
                "done_count": int(row["done_count"] or 0),
                "done_revenue": float(row["done_revenue"] or 0),
                "done_cost": float(row["done_cost"] or 0),
                "done_profit": float(row["done_profit"] or 0),
            },
        })

    def account_values(self, body, user, existing=None):
        """订单级字段。金额、状态、业务项由执照明细回算，这里只处理客户与基础信息。"""

        def pick(key, default=""):
            if key in body:
                return body.get(key)
            if existing is not None:
                return existing.get(key)
            return default

        stamp = parse_ms(body.get("timestamp") if "timestamp" in body else (existing["timestamp"] if existing else None))
        biz_date = pick("biz_date")
        if not biz_date:
            # 服务器在 UTC，业务日期按北京时间算，避免凌晨录入落到前一天/前一月
            moment = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc) + timedelta(hours=8)
            biz_date = moment.strftime("%m/%d")
        details = body.get("details") if isinstance(body.get("details"), list) else []
        first = details[0] if details else {}
        return {
            "timestamp": stamp,
            "biz_date": biz_date,
            "category": pick("category"),
            "client": pick("client"),
            "phone": (pick("phone") or "").strip(),
            "wechat": (pick("wechat") or "").strip(),
            "platform": pick("platform"),
            "items": (first.get("items") or "").strip() or pick("items", ""),
            "unit_price": None,
            "quantity": None,
            "revenue": None,
            "cost": None,
            "profit": None,
            "status": pick("status", "pending") or "pending",
            "completed_at": None,
            "remark": pick("remark"),
            "platform_order_no": (pick("platform_order_no") or "").strip(),
            "creator": pick("creator") or (user["username"] if user else ""),
            "license_name": (first.get("license_name") or "").strip() or (pick("license_name") or "").strip(),
            "credit_code": ((first.get("credit_code") or "").strip() or (pick("credit_code") or "")).strip().upper(),
            "legal_person": (first.get("legal_person") or "").strip() or (pick("legal_person") or "").strip(),
            "legal_id": ((first.get("legal_id") or "").strip() or (pick("legal_id") or "")).strip().upper(),
            "legal_phone": normalize_phone(first.get("legal_phone") or pick("legal_phone")),
            # 客户身份证照片：列表 [{url, name, size}]，jsonb 落库
            "id_photos": Json(normalize_photos(pick("id_photos", []) or [])),
        }

    def detail_values(self, body, existing=None):
        """一条执照明细（= 一个任务）的字段。"""

        def pick(key, default=""):
            if key in body:
                return body.get(key)
            if existing is not None:
                return existing.get(key)
            return default

        unit_price = to_number(pick("unit_price"), None)
        quantity = to_number(pick("quantity", 1), 1)
        if not quantity or quantity <= 0:
            quantity = 1
        revenue = to_number(pick("revenue"), None)
        if revenue is None and unit_price is not None:
            revenue = unit_price * quantity
        cost = to_number(pick("cost"), None)
        profit = to_number(pick("profit"), None)
        if profit is None and revenue is not None and cost is not None:
            profit = revenue - cost
        status = pick("status", "pending") or "pending"
        if status not in ITEM_STATUSES:
            status = "pending"
        # 完成/取消/退款都算关单：首次关单取当时时间，之后保持；退回待定/进行中则清空
        if status in CLOSED_ITEM_STATUSES:
            prior = existing.get("completed_at") if existing is not None else None
            completed_at = int(prior) if prior else now_ms()
        else:
            completed_at = None
        biz_status = normalize_multi_status(pick("biz_status"), BIZ_STATUSES)
        tax_status = (pick("tax_status") or "").strip()
        return {
            "license_name": (pick("license_name") or "").strip(),
            "credit_code": (pick("credit_code") or "").strip().upper(),
            "legal_person": (pick("legal_person") or "").strip(),
            "legal_id": (pick("legal_id") or "").strip().upper(),
            # 法人手机号：容忍用户手输的空格/短横线/+86 前缀
            "legal_phone": normalize_phone(pick("legal_phone")),
            "biz_status": biz_status,
            "tax_status": tax_status,
            "items": (pick("items") or "").strip(),
            "unit_price": unit_price,
            "quantity": quantity,
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
            "status": status,
            "completed_at": completed_at,
            "remark": (pick("remark") or "").strip(),
            # 表单里逐条指定的子任务状态 / 单价（业务项自动拆出来的那些）
            "tasks": body.get("tasks") if isinstance(body.get("tasks"), list) else None,
            # 执照照片：列表 [{url, name, size}]，jsonb 落库
            "license_photos": Json(normalize_photos(pick("license_photos", []) or [])),
        }

    def insert_detail(self, cur, account_id, values, position, operator, account_record):
        columns = [
            "account_id", "license_name", "credit_code", "legal_person", "legal_id", "legal_phone",
            "biz_status", "tax_status", "items", "unit_price", "quantity",
            "revenue", "cost", "profit", "status", "completed_at", "remark", "sort", "license_photos",
        ]
        params = [
            account_id, values["license_name"], values["credit_code"], values["legal_person"],
            values["legal_id"], values["legal_phone"],
            values["biz_status"], values["tax_status"], values["items"], values["unit_price"], values["quantity"],
            values["revenue"], values["cost"], values["profit"], values["status"], values["completed_at"],
            values["remark"], position, values["license_photos"],
        ]
        cur.execute(
            "INSERT INTO account_items (" + ", ".join(columns) + ") VALUES ("
            + ", ".join(["%s"] * len(columns)) + ") RETURNING *",
            params,
        )
        row = cur.fetchone()
        # 每个执照就是一条任务，录入即生成「已录入」进度
        auto_progress(cur, account_record, operator, row["id"], values)
        # 业务项（工商注销 / 税务非正常解除…）各生成一条细分任务，后续可单独办结
        sync_item_tasks(cur, row["id"], account_id, values["items"], values["status"])
        # 录单时就能指定每条子任务的状态/单价，不用先存再改
        if values.get("tasks"):
            apply_task_overrides(cur, row["id"], values["tasks"], operator)
        # 录完就有子任务了：主任务状态跟着子任务走（有未办结的就是「进行中」），录单阶段静默对齐
        self.item_task_summary(cur, row["id"], quiet=True)
        return row

    def sync_details(self, cur, account_id, details, operator, account_record):
        """按提交的明细做增删改：保留 id 的更新，无 id 的新建，未提交的删除（进度级联删除）。"""
        cur.execute(
            "SELECT * FROM account_items WHERE account_id = %s AND is_delete = 0 ORDER BY sort, id",
            (account_id,),
        )
        existing = {row["id"]: row for row in cur.fetchall()}
        kept = []
        position = 0
        for raw in details:
            if not isinstance(raw, dict):
                continue
            try:
                item_id = int(raw.get("id") or 0)
            except (TypeError, ValueError):
                item_id = 0
            current = existing.get(item_id)
            values = self.detail_values(raw, current)
            if current is None:
                row = self.insert_detail(cur, account_id, values, position, operator, account_record)
                kept.append(row["id"])
            else:
                # 取消信息：直接在下拉里改成「取消订单」时补个时间；改回其它状态视为恢复，清空原因
                cancel_reason = current.get("cancel_reason") or ""
                cancel_note = current.get("cancel_note") or ""
                cancelled_at = current.get("cancelled_at")
                prior_status = current["status"] or "pending"
                if values["status"] == "cancelled":
                    if prior_status != "cancelled":
                        cancelled_at = cancelled_at or now_ms()
                elif prior_status == "cancelled":
                    cancel_reason, cancel_note, cancelled_at = "", "", None
                cur.execute(
                    """
                    UPDATE account_items
                       SET license_name = %s, credit_code = %s, legal_person = %s, legal_id = %s,
                           legal_phone = %s,
                           biz_status = %s, tax_status = %s, items = %s, unit_price = %s, quantity = %s,
                           revenue = %s, cost = %s, profit = %s, status = %s, completed_at = %s,
                           remark = %s, sort = %s, license_photos = %s,
                           cancel_reason = %s, cancel_note = %s, cancelled_at = %s
                     WHERE id = %s
                    """,
                    (
                        values["license_name"], values["credit_code"], values["legal_person"], values["legal_id"],
                        values["legal_phone"],
                        values["biz_status"], values["tax_status"], values["items"], values["unit_price"],
                        values["quantity"], values["revenue"], values["cost"], values["profit"],
                        values["status"], values["completed_at"], values["remark"], position,
                        values["license_photos"],
                        cancel_reason, cancel_note, cancelled_at, item_id,
                    ),
                )
                kept.append(item_id)
                # 业务项有增删时同步细分任务（已有的保留各自办理状态）
                sync_item_tasks(
                    cur, item_id, account_id, values["items"], values["status"],
                    (current.get("owner") or ""),
                )
                # 表单里逐条改过的子任务状态/单价
                if values.get("tasks"):
                    apply_task_overrides(cur, item_id, values["tasks"], operator)
                    aligned = self.item_task_summary(cur, item_id, quiet=True)
                    # 子任务全办结会带着主任务变「已完成」，跟进记录按对齐后的状态写
                    if aligned.get("status"):
                        values["status"] = aligned["status"]
                if values["status"] != (current["status"] or "pending"):
                    label = ITEM_STATUS_LABELS.get(values["status"], values["status"])
                    note = "任务状态更新为「%s」" % label
                    if values["status"] == "done":
                        note = "任务已完成，完成时间 " + format_completed(values["completed_at"])
                    insert_progress(
                        cur, account_id, "已完成" if values["status"] == "done" else "状态变更",
                        "done" if values["status"] == "done" else "doing",
                        note, operator, None, item_id,
                    )
            position += 1
        removed = [item_id for item_id in existing if item_id not in kept]
        if removed:
            cur.execute(
                "UPDATE account_items SET is_delete = 1 WHERE id = ANY(%s) AND is_delete = 0",
                (removed,),
            )
        recalc_order(cur, account_id)

    def account_create(self, body, user):
        details = body.get("details")
        if not isinstance(details, list) or not [d for d in details if isinstance(d, dict)]:
            self.send_json({"code": 50000, "message": "订单至少需要一个执照明细（每个执照对应一条任务）"})
            return
        values = self.account_values(body, user)
        columns = ACCOUNT_FIELDS + ["completed_at"]
        params = [values[column] for column in columns]
        sql = (
            "INSERT INTO account_records (" + ", ".join(columns) + ") VALUES ("
            + ", ".join(["%s"] * len(columns)) + ") RETURNING *"
        )
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                # 订单编号在拿到 id 后生成：DD + 录入日期 + 4 位 id
                order_no = generate_order_no(values["timestamp"], row["id"])
                cur.execute(
                    "UPDATE account_records SET order_no = %s WHERE id = %s",
                    (order_no, row["id"]),
                )
                row["order_no"] = order_no
                operator = user["username"] if user else ""
                account_record = {
                    "id": row["id"],
                    "client": values["client"],
                    "items": values["items"],
                    "revenue": None,
                    "timestamp": values["timestamp"],
                }
                for position, raw in enumerate(details):
                    dv = self.detail_values(raw)
                    self.insert_detail(cur, row["id"], dv, position, operator, account_record)
                recalc_order(cur, row["id"])
                cur.execute("SELECT * FROM account_records WHERE id = %s", (row["id"],))
                row = cur.fetchone()
                grouped = fetch_details(cur, [row["id"]])
            conn.commit()
        self.send_json({"code": 20000, "data": account_out(row, grouped.get(row["id"], []))})

    def account_update(self, body, user=None):
        record_id = int(body.get("id") or 0)
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM account_records WHERE id = %s", (record_id,))
                existing = cur.fetchone()
                if existing is None:
                    self.send_json({"code": 50000, "message": "Record not found"})
                    return
                values = self.account_values(body, None, existing)
                computed = (
                    "revenue", "cost", "profit", "status", "quantity", "unit_price", "items",
                    "license_name", "credit_code", "legal_person", "legal_id", "completed_at",
                )
                assignments = []
                params = []
                for column in ACCOUNT_FIELDS:
                    if column not in body and column not in ("timestamp",):
                        continue
                    if column in computed:
                        continue
                    assignments.append(column + " = %s")
                    params.append(values[column])
                # 没有明细的纯状态更新（兼容旧调用）才允许直接改订单状态
                if "status" in body and not isinstance(body.get("details"), list):
                    assignments.append("status = %s")
                    params.append(values["status"])
                if assignments:
                    params.append(record_id)
                    cur.execute(
                        "UPDATE account_records SET " + ", ".join(assignments) + " WHERE id = %s",
                        params,
                    )
                if isinstance(body.get("details"), list):
                    operator = user["username"] if user else ""
                    account_record = {
                        "id": record_id,
                        "client": values["client"],
                        "items": values["items"],
                        "revenue": None,
                        "timestamp": values["timestamp"],
                    }
                    self.sync_details(cur, record_id, body["details"], operator, account_record)
                cur.execute("SELECT * FROM account_records WHERE id = %s", (record_id,))
                row = cur.fetchone()
                grouped = fetch_details(cur, [record_id])
            conn.commit()
        self.send_json({"code": 20000, "data": account_out(row, grouped.get(record_id, []))})

    def account_delete(self, body):
        """软删除：只把订单及其明细、进度、细分任务标记为已删除，数据永久留在库里。"""
        record_id = int(body.get("id") or 0)
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE account_records SET is_delete = 1 WHERE id = %s AND is_delete = 0",
                    (record_id,),
                )
                cur.execute(
                    "UPDATE account_items SET is_delete = 1 WHERE account_id = %s AND is_delete = 0",
                    (record_id,),
                )
                cur.execute(
                    "UPDATE order_progress SET is_delete = 1 WHERE account_id = %s AND is_delete = 0",
                    (record_id,),
                )
                cur.execute(
                    "UPDATE account_item_tasks SET is_delete = 1 WHERE account_id = %s AND is_delete = 0",
                    (record_id,),
                )
            conn.commit()
        self.send_json({"code": 20000, "data": "success"})

    # ---------------- 订单级退款 / 取消（订单列表发起） ----------------

    def account_refund(self, body, user):
        """订单退款：从订单列表发起，可整单退，也可只退选中的几个执照任务。

        - 不传 item_ids 就退所有还能退的任务；传了只退选中的那几条。
        - 一笔退款在「成本管理」只记一条退款支出（kind='refund'），财务统计会排除，
          因为退款金额已经在订单收入里扣过一次，不能再当支出扣第二次。
        - 每条被退的任务都会在跟进时间线留一条「退款」记录，订单状态按任务回算。
        """
        account_id = int(body.get("account_id") or 0)
        if not account_id:
            self.send_json({"code": 50000, "message": "缺少订单 id"})
            return
        raw_ids = body.get("item_ids") or []
        if isinstance(raw_ids, str):
            raw_ids = [part for part in raw_ids.split(",") if part.strip()]
        wanted = {int(str(part).strip()) for part in raw_ids if str(part).strip().isdigit()}
        operator = user["username"] if user else ""
        stamp = now_ms()
        biz_date = (datetime.fromtimestamp(stamp / 1000, tz=timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM account_records WHERE id = %s AND is_delete = 0 FOR UPDATE",
                    (account_id,),
                )
                account = cur.fetchone()
                if account is None:
                    self.send_json({"code": 50000, "message": "订单不存在"})
                    return
                cur.execute(
                    "SELECT * FROM account_items WHERE account_id = %s AND is_delete = 0"
                    " ORDER BY sort, id FOR UPDATE",
                    (account_id,),
                )
                items = cur.fetchall()
                pool = [
                    item for item in items
                    if (item.get("status") or "") not in ("cancelled", "refunded")
                    and float(item.get("revenue") or 0) > 0.004
                ]
                if wanted:
                    pool = [item for item in pool if item["id"] in wanted]
                    if not pool:
                        self.send_json({"code": 50000, "message": "选中的任务都已取消/退款，或没有可退金额"})
                        return
                if not pool:
                    self.send_json({"code": 50000, "message": "该订单没有可退金额"})
                    return
                available = round(sum(float(item.get("revenue") or 0) for item in pool), 2)
                raw_amount = body.get("amount")
                if raw_amount in (None, ""):
                    amount = available
                else:
                    amount = round(to_number(raw_amount, 0) or 0, 2)
                if amount <= 0:
                    self.send_json({"code": 50000, "message": "退款金额必须大于 0"})
                    return
                if amount > available + 0.004:
                    self.send_json({
                        "code": 50000,
                        "message": "退款金额不能超过可退金额 ¥" + format_amount(available),
                    })
                    return

                reason = (body.get("reason") or "").strip()[:100]
                method = (body.get("method") or "").strip()
                shares = split_refund_amount(pool, amount)
                refund_total = 0.0
                touched = []
                for item, take in shares:
                    before = float(item.get("revenue") or 0)
                    new_revenue, new_status = refund_item_line(cur, item, take, stamp)
                    refund_total = round(refund_total + take, 2)
                    note = "退款 ¥%s（%s），任务金额 %s → %s" % (
                        format_amount(take),
                        item.get("license_name") or "未填执照",
                        format_amount(before),
                        format_amount(new_revenue),
                    )
                    if reason:
                        note += "；原因：" + reason
                    insert_progress(cur, account_id, "退款", "done", note, operator, stamp, item["id"])
                    touched.append({
                        "item_id": item["id"],
                        "license_name": item.get("license_name") or "",
                        "refund": take,
                        "revenue": new_revenue,
                        "status": new_status,
                    })

                licenses = "、".join(item.get("license_name") for item, _ in shares if item.get("license_name"))
                remark = "订单退款：%s %s；范围：%s" % (
                    account.get("order_no") or ("订单#" + str(account_id)),
                    account.get("client") or "",
                    licenses or "整单",
                )
                if reason:
                    remark += "；原因：" + reason
                cur.execute(
                    """
                    INSERT INTO cost_records
                           (timestamp, biz_date, category, payee, amount, method,
                            related_order, remark, creator, kind)
                    VALUES (%s, %s, '退款', %s, %s, %s, %s, %s, %s, 'refund')
                    RETURNING id
                    """,
                    (
                        stamp, biz_date, account.get("client") or "客户",
                        refund_total, method, account_id, remark, operator,
                    ),
                )
                cost_id = cur.fetchone()["id"]

                recalc_order(cur, account_id)
                cur.execute("SELECT status, revenue, profit FROM account_records WHERE id = %s", (account_id,))
                order = cur.fetchone()
            conn.commit()
        self.send_json({
            "code": 20000,
            "data": {
                "account_id": account_id,
                "cost_id": cost_id,
                "refund": refund_total,
                "available": available,
                "items": touched,
                "account_status": order["status"],
                "order_revenue": float(order["revenue"] or 0),
                "order_profit": float(order["profit"] or 0),
            },
        })

    def account_cancel(self, body, user):
        """取消订单：从订单列表发起，可整单取消，也可只取消选中的几个执照任务。

        和任务级的取消口径一致：默认把金额清零（不做了就不计收入），成本保留；
        clear_amount=false 时只改状态、金额不动（比如退过一部分款的单子）。
        """
        account_id = int(body.get("account_id") or 0)
        if not account_id:
            self.send_json({"code": 50000, "message": "缺少订单 id"})
            return
        raw_ids = body.get("item_ids") or []
        if isinstance(raw_ids, str):
            raw_ids = [part for part in raw_ids.split(",") if part.strip()]
        wanted = {int(str(part).strip()) for part in raw_ids if str(part).strip().isdigit()}
        reason = (body.get("reason") or "").strip()[:100]
        remark = (body.get("note") or "").strip()[:500]
        clear_amount = body.get("clear_amount")
        clear_amount = True if clear_amount is None else bool(clear_amount)
        if not reason:
            self.send_json({"code": 50000, "message": "请填写取消原因"})
            return
        operator = user["username"] if user else ""
        stamp = now_ms()
        biz_date = (datetime.fromtimestamp(stamp / 1000, tz=timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM account_records WHERE id = %s AND is_delete = 0 FOR UPDATE",
                    (account_id,),
                )
                account = cur.fetchone()
                if account is None:
                    self.send_json({"code": 50000, "message": "订单不存在"})
                    return
                cur.execute(
                    "SELECT * FROM account_items WHERE account_id = %s AND is_delete = 0"
                    " ORDER BY sort, id FOR UPDATE",
                    (account_id,),
                )
                items = cur.fetchall()
                targets = [item for item in items if (item.get("status") or "") not in ("cancelled", "refunded")]
                if wanted:
                    targets = [item for item in targets if item["id"] in wanted]
                    if not targets:
                        self.send_json({"code": 50000, "message": "选中的任务都已取消或退款，不能再取消"})
                        return
                if not targets:
                    self.send_json({"code": 50000, "message": "该订单没有可取消的任务"})
                    return

                # 取消时可以把已收的钱一起退给客户：先冲减收入、记一笔退款流水，再取消
                # （顺序不能反：取消会把金额清零，先取消就没金额可退了）
                refund_raw = body.get("refund_amount")
                refund_amount = 0.0 if refund_raw in (None, "") else round(to_number(refund_raw, 0) or 0, 2)
                refund_method = (body.get("refund_method") or "").strip()
                refund_total = 0.0
                refundable = [
                    item for item in targets
                    if (item.get("status") or "") not in ("cancelled", "refunded")
                    and float(item.get("revenue") or 0) > 0.004
                ]
                refundable_total = round(sum(float(item.get("revenue") or 0) for item in refundable), 2)
                if refund_amount > 0.004:
                    if not refundable:
                        self.send_json({"code": 50000, "message": "选中的任务没有可退金额"})
                        return
                    if refund_amount > refundable_total + 0.004:
                        self.send_json({
                            "code": 50000,
                            "message": "退款金额不能超过已收金额 ¥" + format_amount(refundable_total),
                        })
                        return
                    refunded_map = {}
                    shares = split_refund_amount(refundable, refund_amount)
                    for item, take in shares:
                        before_revenue = float(item.get("revenue") or 0)
                        new_revenue, _new_status = refund_item_line(cur, item, take, stamp)
                        refund_total = round(refund_total + take, 2)
                        refunded_map[item["id"]] = new_revenue
                        note = "退款 ¥%s（%s），任务金额 %s → %s" % (
                            format_amount(take),
                            item.get("license_name") or "未填执照",
                            format_amount(before_revenue),
                            format_amount(new_revenue),
                        )
                        if reason:
                            note += "；原因：" + reason
                        insert_progress(cur, account_id, "退款", "done", note, operator, stamp, item["id"])
                    # 后续取消按退款后的金额算，跟进里的「金额 → 0」才对得上
                    targets = [
                        dict(item, revenue=refunded_map.get(item["id"], item.get("revenue")))
                        for item in targets
                    ]
                    refund_licenses = "、".join(
                        item.get("license_name") for item, _ in shares
                        if item.get("license_name")
                    )
                    refund_remark = "取消订单退款：%s %s；范围：%s" % (
                        account.get("order_no") or ("订单#" + str(account_id)),
                        account.get("client") or "",
                        refund_licenses or "整单",
                    )
                    if reason:
                        refund_remark += "；原因：" + reason
                    cur.execute(
                        """
                        INSERT INTO cost_records
                               (timestamp, biz_date, category, payee, amount, method,
                                related_order, remark, creator, kind)
                        VALUES (%s, %s, '退款', %s, %s, %s, %s, %s, %s, 'refund')
                        """,
                        (
                            stamp, biz_date, account.get("client") or "客户",
                            refund_total, refund_method, account_id, refund_remark, operator,
                        ),
                    )

                cleared = 0
                for item in targets:
                    before, after = cancel_item_line(cur, item, stamp, reason, remark, clear_amount)
                    note = "取消订单，原因：" + reason
                    if remark:
                        note += "；备注：" + remark
                    if clear_amount and before > 0.004:
                        note += "；金额 %s → 0（不计收入）" % format_amount(before)
                        cleared += 1
                    insert_progress(cur, account_id, "取消订单", "done", note, operator, stamp, item["id"])

                recalc_order(cur, account_id)
                cur.execute("SELECT status, revenue, profit FROM account_records WHERE id = %s", (account_id,))
                order = cur.fetchone()
            conn.commit()
        self.send_json({
            "code": 20000,
            "data": {
                "account_id": account_id,
                "cancelled_count": len(targets),
                "cleared_count": cleared,
                "refund": refund_total,
                "account_status": order["status"],
                "order_revenue": float(order["revenue"] or 0),
                "order_profit": float(order["profit"] or 0),
            },
        })

    # ---------------- 订单进度 ----------------

    def progress_list(self, query):
        """某个任务（执照明细）的完整跟进记录。"""
        item_id = int(query.get("item_id") or 0)
        account_id = int(query.get("account_id") or 0)
        if not item_id and not account_id:
            self.send_json({"code": 50000, "message": "缺少任务 id"})
            return
        files_by_line = {}
        item_tasks = []
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if item_id:
                    cur.execute(
                        "SELECT p.*, u.name AS operator_name, u.avatar AS operator_avatar"
                        "  FROM order_progress p"
                        "  LEFT JOIN users u ON u.username = p.operator"
                        " WHERE p.item_id = %s AND p.is_delete = 0"
                        " AND NOT EXISTS (SELECT 1 FROM account_item_tasks dt"
                        " WHERE dt.id = p.task_id AND dt.is_delete = 1)"
                        " ORDER BY p.timestamp ASC, p.id ASC",
                        (item_id,),
                    )
                else:
                    cur.execute(
                        "SELECT p.*, u.name AS operator_name, u.avatar AS operator_avatar"
                        "  FROM order_progress p"
                        "  LEFT JOIN users u ON u.username = p.operator"
                        " WHERE p.account_id = %s AND p.is_delete = 0"
                        " AND NOT EXISTS (SELECT 1 FROM account_item_tasks dt"
                        " WHERE dt.id = p.task_id AND dt.is_delete = 1)"
                        " ORDER BY p.timestamp ASC, p.id ASC",
                        (account_id,),
                    )
                items = [progress_out(row) for row in cur.fetchall()]
                item = None
                if item_id:
                    cur.execute(
                        "SELECT * FROM account_items WHERE id = %s AND is_delete = 0",
                        (item_id,),
                    )
                    item_row = cur.fetchone()
                    if item_row is not None:
                        cur.execute(
                            "SELECT * FROM account_records WHERE id = %s AND is_delete = 0",
                            (item_row["account_id"],),
                        )
                        account_row = cur.fetchone()
                        item = item_out(item_row)
                        if account_row is not None:
                            item.update({
                                "client": account_row["client"] or "",
                                "phone": account_row["phone"] or "",
                                "order_no": account_row.get("order_no") or "",
                                "biz_date": account_row["biz_date"] or "",
                                "category": account_row["category"] or "",
                                "account_status": account_row["status"] or "pending",
                            })
                        # 主跟进人显示名：显式指定优先，没指定就按跟进记录推断
                        owner_user = item.get("owner") or ""
                        if not owner_user:
                            for record in reversed(items):
                                if (record.get("step") or "") != "已录入" and record.get("operator"):
                                    owner_user = record["operator"]
                                    break
                            item["owner_auto"] = bool(owner_user)
                        item["owner"] = owner_user
                        item["owner_name"] = owner_user
                        if owner_user:
                            cur.execute("SELECT name, avatar FROM users WHERE username = %s", (owner_user,))
                            user_row = cur.fetchone()
                            if user_row is not None:
                                item["owner_name"] = user_row["name"] or owner_user
                                item["owner_avatar"] = user_row["avatar"] or ""
                    # 办理线附件：工商 / 税务各自上传的图片，随跟进详情一起返回
                    cur.execute(
                        "SELECT * FROM progress_files WHERE item_id = %s ORDER BY timestamp ASC, id ASC",
                        (item_id,),
                    )
                    for row in cur.fetchall():
                        record = progress_file_out(row)
                        files_by_line.setdefault(record["line"], []).append(record)
                    # 细分任务：弹窗里可以直接勾「办结」，不用回列表
                    item_tasks = fetch_item_tasks(cur, [item_id]).get(item_id, [])
        self.send_json({"code": 20000, "data": {
            "items": items,
            "files": files_by_line,
            "tasks": item_tasks,
            "steps": PROGRESS_STEPS,
            "stage_groups": PROGRESS_STAGE_GROUPS,
            "item": item,
        }})

    def progress_files_list(self, query):
        """某条任务下各办理线的附件（工商 / 税务两条线各自一组）。"""
        item_id = int(query.get("item_id") or 0)
        if not item_id:
            self.send_json({"code": 50000, "message": "缺少任务 id"})
            return
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM progress_files WHERE item_id = %s ORDER BY timestamp ASC, id ASC",
                    (item_id,),
                )
                files = [progress_file_out(row) for row in cur.fetchall()]
        by_line = {}
        for record in files:
            by_line.setdefault(record["line"], []).append(record)
        self.send_json({"code": 20000, "data": {"items": files, "by_line": by_line}})

    def progress_file_add(self, body, user):
        """把已上传的图片挂到某条任务的办理线上（文件先走 /upload 拿到 url）。"""
        item_id = int(body.get("item_id") or 0)
        url = str(body.get("url") or "").strip()
        line = str(body.get("line") or "").strip()
        if not item_id or not url:
            self.send_json({"code": 50000, "message": "缺少任务 id 或图片地址"})
            return
        if line not in ("biz", "tax", "common"):
            line = "common"
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, account_id FROM account_items WHERE id = %s AND is_delete = 0", (item_id,))
                item_row = cur.fetchone()
                if item_row is None:
                    self.send_json({"code": 50000, "message": "任务不存在"})
                    return
                cur.execute(
                    "INSERT INTO progress_files (item_id, account_id, line, url, name, size, uploader, timestamp)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                    (
                        item_id,
                        item_row["account_id"],
                        line,
                        url,
                        str(body.get("name") or "")[:200],
                        int(body.get("size") or 0),
                        user["username"] if user else "",
                        now_ms(),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        self.send_json({"code": 20000, "data": progress_file_out(row)})

    def progress_file_delete(self, body):
        """删掉一张附件（同时把 /uploads 下的物理文件清掉，避免堆积）。"""
        file_id = int(body.get("id") or 0)
        if not file_id:
            self.send_json({"code": 50000, "message": "缺少附件 id"})
            return
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT url FROM progress_files WHERE id = %s", (file_id,))
                row = cur.fetchone()
                cur.execute("DELETE FROM progress_files WHERE id = %s", (file_id,))
            conn.commit()
        url = (row or {}).get("url") or ""
        if url.startswith("/uploads/"):
            target = UPLOAD_DIR / os.path.basename(url)
            try:
                if target.is_file():
                    target.unlink()
            except OSError:
                pass
        self.send_json({"code": 20000, "data": "success"})

    def progress_overview(self, query):
        """任务总览：一行 = 一条执照明细，带该任务最新进度与主跟进人。"""
        # 已删除的订单与明细都不出现在任务总览里
        where = ["i.is_delete = 0", "a.is_delete = 0"]
        params = []
        keyword = (query.get("keyword") or "").strip()
        if keyword:
            where.append(
                "(a.client ILIKE %s OR a.phone ILIKE %s OR a.wechat ILIKE %s OR a.order_no ILIKE %s"
                " OR a.platform_order_no ILIKE %s"
                " OR i.items ILIKE %s OR i.license_name ILIKE %s"
                " OR i.credit_code ILIKE %s OR i.legal_person ILIKE %s OR i.legal_phone ILIKE %s)"
            )
            params.extend(["%" + keyword + "%"] * 10)
        if query.get("status"):
            where.append("i.status = %s")
            params.append(query["status"])
        if query.get("biz_status"):
            # 多选状态按逗号拆分后匹配单个取值
            where.append("%s = ANY(string_to_array(COALESCE(i.biz_status, ''), ','))")
            params.append(query["biz_status"])
        if query.get("tax_status"):
            where.append("i.tax_status = %s")
            params.append(query["tax_status"])
        if query.get("owner"):
            # 主跟进人：显式指定的优先，没指定就按「跟进记录最多的人」推断
            where.append(
                "COALESCE(NULLIF(i.owner, ''), (SELECT op.operator FROM order_progress op"
                " WHERE op.item_id = i.id AND op.is_delete = 0"
                " AND COALESCE(op.operator, '') <> '' AND op.step <> '已录入'"
                " GROUP BY op.operator ORDER BY COUNT(*) DESC, MAX(op.timestamp) DESC LIMIT 1), '') = %s"
            )
            params.append(query["owner"])
        if query.get("month"):
            month = str(query["month"]).split("-")[-1].strip()
            where.append("(a.biz_date LIKE %s OR a.biz_date LIKE %s)")
            params.extend([month + "/%", "%-" + month + "-%"])
        condition = (" WHERE " + " AND ".join(where)) if where else ""
        page = max(int(query.get("page") or 1), 1)
        limit = min(max(int(query.get("limit") or 20), 1), 200)
        sql = """
            SELECT i.*, a.client, a.phone, a.wechat, a.biz_date, a.category, a.platform,
                   a.order_no, a.status AS account_status,
                   p.step AS last_step,
                   p.status AS last_status,
                   p.note AS last_note,
                   p.operator AS last_operator,
                   p.timestamp AS last_timestamp,
                   COALESCE(NULLIF(i.owner, ''), ow.username, '') AS owner_user,
                   COALESCE(ow.cnt, 0) AS owner_cnt,
                   uo.name AS owner_name,
                   uo.avatar AS owner_avatar,
                   COALESCE(c.cnt, 0) AS progress_count
              FROM account_items i
              JOIN account_records a ON a.id = i.account_id
              LEFT JOIN LATERAL (
                   SELECT * FROM order_progress
                    WHERE item_id = i.id AND is_delete = 0
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 1
              ) p ON TRUE
              -- 自动推断的主跟进人：跟进条数最多（同条数取最近跟进）的那个人；系统自动写的「已录入」不算，改任务状态也算人跟进
              LEFT JOIN LATERAL (
                   SELECT op.operator AS username, COUNT(*) AS cnt, MAX(op.timestamp) AS ts
                     FROM order_progress op
                    WHERE op.item_id = i.id AND op.is_delete = 0
                      AND COALESCE(op.operator, '') <> '' AND op.step <> '已录入'
                    GROUP BY op.operator
                    ORDER BY COUNT(*) DESC, MAX(op.timestamp) DESC
                    LIMIT 1
              ) ow ON TRUE
              LEFT JOIN users uo ON uo.username = COALESCE(NULLIF(i.owner, ''), ow.username)
              LEFT JOIN (
                   SELECT item_id, COUNT(*) AS cnt FROM order_progress
                    WHERE item_id IS NOT NULL AND is_delete = 0 GROUP BY item_id
              ) c ON c.item_id = i.id
        """
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT COUNT(*) AS total FROM account_items i JOIN account_records a ON a.id = i.account_id" + condition,
                    params,
                )
                total = cur.fetchone()["total"]
                cur.execute(
                    sql + condition + " ORDER BY a.id DESC, i.sort, i.id LIMIT %s OFFSET %s",
                    params + [limit, (page - 1) * limit],
                )
                items = []
                ids = []
                for row in cur.fetchall():
                    record = item_out(row)
                    owner_user = row["owner_user"] or ""
                    record.update({
                        "client": row["client"] or "",
                        "phone": row["phone"] or "",
                        "wechat": row.get("wechat") or "",
                        "order_no": row.get("order_no") or "",
                        "biz_date": row["biz_date"] or "",
                        "category": row["category"] or "",
                        "platform": row["platform"] or "",
                        "account_status": row["account_status"] or "pending",
                        "last_step": row["last_step"] or "",
                        "last_status": row["last_status"] or "",
                        "last_note": row["last_note"] or "",
                        "last_operator": row["last_operator"] or "",
                        "last_timestamp": int(row["last_timestamp"] or 0),
                        "progress_count": int(row["progress_count"] or 0),
                        # 主跟进人：显式指定 or 按跟进记录推断（owner_auto=True 表示是推断出来的）
                        "owner": owner_user,
                        "owner_name": row["owner_name"] or owner_user,
                        "owner_avatar": row["owner_avatar"] or "",
                        "owner_auto": bool(owner_user) and not (row.get("owner") or ""),
                        "owner_count": int(row["owner_cnt"] or 0),
                    })
                    items.append(record)
                    ids.append(record["id"])

                # 三条办理线各自的最新状态：未完成的排前面，已完成的（含系统自动写的「已录入」）不算当前进度
                snapshot = progress_snapshot(cur, ids)
                # 细分任务：主任务行默认折叠，展开才看这些业务项
                tasks_map = fetch_item_tasks(cur, ids)
                for record in items:
                    snap = snapshot.get(record["id"]) or {}
                    lines = snap.get("lines") or []
                    record["progress_lines"] = lines
                    tasks = tasks_map.get(record["id"], [])
                    record["tasks"] = tasks
                    record["task_total"] = len(tasks)
                    record["task_done"] = len([t for t in tasks if t["status"] == "done"])
                    record["task_cancelled"] = len([t for t in tasks if t["status"] == "cancelled"])
                    record["open_steps"] = [
                        {
                            "group": line["group"],
                            "step": line["open_step"],
                            "status": line["open_status"],
                            "timestamp": line["open_timestamp"],
                        }
                        for line in lines if line["open_step"]
                    ]
        self.send_json({"code": 20000, "data": {
            "total": total,
            "items": items,
            "steps": PROGRESS_STEPS,
            "stage_groups": PROGRESS_STAGE_GROUPS,
        }})

    def progress_summary(self):
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT step, COUNT(*) AS cnt FROM (
                        SELECT DISTINCT ON (item_id) item_id, step
                          FROM order_progress
                         WHERE item_id IS NOT NULL AND is_delete = 0
                         ORDER BY item_id, timestamp DESC, id DESC
                    ) latest GROUP BY step ORDER BY cnt DESC, step
                """)
                by_step = [{"step": row["step"], "count": int(row["cnt"])} for row in cur.fetchall()]
                cur.execute(
                    "SELECT COUNT(DISTINCT item_id) AS cnt FROM order_progress"
                    " WHERE item_id IS NOT NULL AND is_delete = 0"
                )
                covered = int(cur.fetchone()["cnt"] or 0)
                cur.execute("SELECT COUNT(*) AS cnt FROM account_items WHERE is_delete = 0")
                tasks = int(cur.fetchone()["cnt"] or 0)
                cur.execute("SELECT COUNT(*) AS cnt FROM account_records WHERE is_delete = 0")
                orders = int(cur.fetchone()["cnt"] or 0)
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM account_items WHERE status = 'done' AND is_delete = 0"
                )
                done = int(cur.fetchone()["cnt"] or 0)
                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM account_items i
                     WHERE i.is_delete = 0
                       AND NOT EXISTS (
                           SELECT 1 FROM order_progress p
                            WHERE p.item_id = i.id AND p.is_delete = 0
                       )
                """)
                missing = int(cur.fetchone()["cnt"] or 0)
                # 按任务状态分档：页面上的「任务总数」是全部任务，列表可能被状态筛选过，
                # 这两个数字要能对得上，所以把各状态条数一并返回
                cur.execute(
                    "SELECT status, COUNT(*) AS cnt FROM account_items"
                    " WHERE is_delete = 0 GROUP BY status"
                )
                by_status = {"pending": 0, "doing": 0, "done": 0, "cancelled": 0, "refunded": 0}
                for row in cur.fetchall():
                    by_status[row["status"] or "pending"] = int(row["cnt"] or 0)
                # 细分任务：执照按业务项拆出来的小任务，卡片上给个总进度
                cur.execute(
                    "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status = 'done') AS done"
                    "  FROM account_item_tasks WHERE is_delete = 0"
                )
                subtask_row = cur.fetchone()
        self.send_json({
            "code": 20000,
            "data": {
                "by_step": by_step, "covered": covered, "tasks": tasks,
                "orders": orders, "done": done, "missing": missing,
                "by_status": by_status,
                "subtasks": {
                    "total": int(subtask_row["total"] or 0),
                    "done": int(subtask_row["done"] or 0),
                },
            },
        })

    def finance_report(self, query):
        """月度财务报表：一个自然月的订单收入、直接成本、支出与利润汇总。
        不传 month 时自动落在最近有数据的月份，避免打开就是空白页。"""
        requested = str(query.get("month") or "").strip()
        month = normalize_month(requested) if requested else None

        def pick_month(rows, target):
            return [row for row in rows if finance_month_of(row.get("biz_date"), row.get("timestamp")) == target]

        def summarize(ord_rows, cost_rows, item_rows):
            revenue = sum(float(row["revenue"] or 0) for row in ord_rows)
            direct_cost = sum(float(row["cost"] or 0) for row in ord_rows)
            # 退款记录（kind='refund'）的金额已经在订单收入里冲减过，支出侧跳过，
            # 否则同一笔退款会把当月利润扣两次
            opex = sum(
                float(row["amount"] or 0) for row in cost_rows
                if (row.get("kind") or "") != "refund"
            )
            done = sum(1 for row in item_rows if (row.get("status") or "") == "done")
            return {
                "orders": len(ord_rows),
                "licenses": len(item_rows),
                "revenue": round(revenue, 2),
                "direct_cost": round(direct_cost, 2),
                "opex": round(opex, 2),
                "total_cost": round(direct_cost + opex, 2),
                "net_profit": round(revenue - direct_cost - opex, 2),
                "done_tasks": done,
            }

        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM account_records WHERE is_delete = 0")
                all_orders = cur.fetchall()
                cur.execute("SELECT * FROM cost_records WHERE is_delete = 0")
                all_costs = cur.fetchall()

            if month is None:
                # 优先落在最近有订单的月份，没有订单才退到有支出的月份
                order_keys = [
                    key for key in (
                        finance_month_of(row.get("biz_date"), row.get("timestamp")) for row in all_orders
                    ) if key
                ]
                cost_keys = [
                    key for key in (
                        finance_month_of(row.get("biz_date"), row.get("timestamp")) for row in all_costs
                    ) if key
                ]
                month = max(order_keys) if order_keys else (max(cost_keys) if cost_keys else normalize_month(""))

            begin, end = month_bounds(month)
            orders = pick_month(all_orders, month)
            # 退款记录不计入报表支出（收入已冲减），只留在「成本管理」里看现金流出
            costs = [
                row for row in pick_month(all_costs, month)
                if (row.get("kind") or "") != "refund"
            ]
            order_ids = [row["id"] for row in orders]
            details = []
            if order_ids:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        "SELECT * FROM account_items WHERE account_id = ANY(%s) AND is_delete = 0 ORDER BY account_id, sort, id",
                        (order_ids,),
                    )
                    details = cur.fetchall()

            prev_key = prev_month(month)
            prev_orders = pick_month(all_orders, prev_key)
            prev_costs = [
                row for row in pick_month(all_costs, prev_key)
                if (row.get("kind") or "") != "refund"
            ]
            prev_ids = [row["id"] for row in prev_orders]
            prev_details = []
            if prev_ids:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM account_items WHERE account_id = ANY(%s) AND is_delete = 0", (prev_ids,))
                    prev_details = cur.fetchall()

        summary = summarize(orders, costs, details)
        prev_summary = summarize(prev_orders, prev_costs, prev_details)

        # 任务平均结案时长（天）：结案时间 - 明细创建时间
        close_days = []
        for row in details:
            if (row.get("status") or "") == "done" and row.get("completed_at") and row.get("created_at"):
                span = (float(row["completed_at"]) - row["created_at"].timestamp() * 1000) / 86400000
                close_days.append(max(0.0, span))
        summary["avg_close_days"] = round(sum(close_days) / len(close_days), 1) if close_days else None

        revenue_by_category = finance_group_rows(orders, lambda r: r.get("category"), lambda r: r["revenue"])
        revenue_by_platform = finance_group_rows(orders, lambda r: r.get("platform"), lambda r: r["revenue"])
        cost_by_category = finance_group_rows(costs, lambda r: r.get("category"), lambda r: r["amount"])

        # 业务项排行：明细按原子项拆分统计（一条明细多个业务项时，收入会计入每一项）
        biz_stats = {}
        for row in details:
            for name in split_biz_items(row.get("items")):
                bucket = biz_stats.setdefault(name, {"name": name, "count": 0, "revenue": 0.0, "cost": 0.0, "profit": 0.0})
                bucket["count"] += 1
                bucket["revenue"] += float(row["revenue"] or 0)
                bucket["cost"] += float(row["cost"] or 0)
                bucket["profit"] += float(row["profit"] or 0)
        biz_item_rank = sorted(biz_stats.values(), key=lambda item: item["revenue"], reverse=True)
        for bucket in biz_item_rank:
            for key in ("revenue", "cost", "profit"):
                bucket[key] = round(bucket[key], 2)

        client_stats = {}
        for row in orders:
            name = (row.get("client") or "").strip() or "未命名客户"
            bucket = client_stats.setdefault(name, {"name": name, "orders": 0, "revenue": 0.0})
            bucket["orders"] += 1
            bucket["revenue"] += float(row["revenue"] or 0)
        client_rank = sorted(client_stats.values(), key=lambda item: item["revenue"], reverse=True)
        for bucket in client_rank:
            bucket["revenue"] = round(bucket["revenue"], 2)

        # 整月逐日收入 / 支出曲线（缺数据的日期补 0）
        revenue_by_day = {}
        opex_by_day = {}
        for row in orders:
            key = finance_day_of(row.get("biz_date"), row.get("timestamp"))
            if key:
                revenue_by_day[key] = revenue_by_day.get(key, 0) + float(row["revenue"] or 0)
        for row in costs:
            key = finance_day_of(row.get("biz_date"), row.get("timestamp"))
            if key:
                opex_by_day[key] = opex_by_day.get(key, 0) + float(row["amount"] or 0)
        daily = []
        cursor_day = begin
        while cursor_day < end:
            key = cursor_day.strftime("%m-%d")
            daily.append({
                "day": key,
                "revenue": round(revenue_by_day.get(key, 0), 2),
                "opex": round(opex_by_day.get(key, 0), 2),
            })
            cursor_day += timedelta(days=1)

        license_count = {}
        for row in details:
            license_count[row["account_id"]] = license_count.get(row["account_id"], 0) + 1
        order_rows = [{
            "id": row["id"],
            "order_no": row.get("order_no") or "",
            "biz_date": row.get("biz_date") or "",
            "client": row.get("client") or "",
            "category": row.get("category") or "",
            "platform": row.get("platform") or "",
            "items": row.get("items") or "",
            "licenses": license_count.get(row["id"], 0),
            "revenue": round(float(row["revenue"] or 0), 2),
            "cost": round(float(row["cost"] or 0), 2),
            "profit": round(float(row["profit"] or 0), 2),
            "status": row.get("status") or "pending",
        } for row in orders]
        order_rows.sort(key=lambda item: item["id"], reverse=True)

        cost_rows = [{
            "id": row["id"],
            "biz_date": row.get("biz_date") or "",
            "category": row.get("category") or "",
            "payee": row.get("payee") or "",
            "amount": round(float(row["amount"] or 0), 2),
            "method": row.get("method") or "",
            "related_order": row.get("related_order"),
            "remark": row.get("remark") or "",
        } for row in costs]
        cost_rows.sort(key=lambda item: item["id"])

        self.send_json({
            "code": 20000,
            "data": {
                "month": month,
                "summary": summary,
                "prev_summary": prev_summary,
                "revenue_by_category": revenue_by_category,
                "revenue_by_platform": revenue_by_platform,
                "cost_by_category": cost_by_category,
                "biz_item_rank": biz_item_rank,
                "client_rank": client_rank,
                "daily": daily,
                "orders": order_rows,
                "costs": cost_rows,
            },
        })

    def progress_create(self, body, user):
        item_id = int(body.get("item_id") or 0)
        account_id = int(body.get("account_id") or 0)
        task_id = int(body.get("task_id") or 0)
        step = (body.get("step") or "").strip()
        if not step or (not item_id and not account_id):
            self.send_json({"code": 50000, "message": "任务与进度阶段不能为空"})
            return
        status = body.get("status") or "doing"
        operator = user["username"] if user else ""
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                item = None
                task = None
                # 挂在子任务上：先校验归属和编辑权限，只有跟进人本人或管理员能补跟进
                if task_id:
                    task = self.load_task(cur, task_id)
                    if task is None:
                        self.send_json({"code": 50000, "message": "细分任务不存在"})
                        return
                    if item_id and task["item_id"] != item_id:
                        self.send_json({"code": 50000, "message": "细分任务不属于这条执照"})
                        return
                    if not self.task_edit_allowed(user, task):
                        self.send_json({
                            "code": 50000,
                            "message": "这条子任务的跟进人是 %s，只有跟进人本人或管理员能补跟进" % (task.get("owner") or "—"),
                        })
                        return
                    self.claim_task(cur, user, task)
                    item_id = task["item_id"]
                    account_id = task["account_id"]
                if item_id:
                    cur.execute(
                        "SELECT * FROM account_items WHERE id = %s AND is_delete = 0",
                        (item_id,),
                    )
                    item = cur.fetchone()
                    if item is None:
                        self.send_json({"code": 50000, "message": "任务不存在"})
                        return
                    account_id = item["account_id"]
                else:
                    cur.execute(
                        "SELECT * FROM account_items WHERE account_id = %s AND is_delete = 0"
                        " ORDER BY sort, id LIMIT 1",
                        (account_id,),
                    )
                    item = cur.fetchone()
                    if item is None:
                        self.send_json({"code": 50000, "message": "该订单还没有执照明细"})
                        return
                    item_id = item["id"]
                insert_progress(cur, account_id, step, status, body.get("note"), operator, None, item_id, task_id or None)
                if task:
                    # 这条子任务跟着推进：选了「办结」（或状态置为已完成）就办结，其它一律进行中；
                    # 已经办结的子任务只是补一条过程记录，不被打回进行中（要重开直接改任务状态）
                    finished = status == "done" or step.endswith("办结")
                    current_status = task.get("status") or "pending"
                    new_task_status = "done" if (finished or current_status == "done") else "doing"
                    stamp = now_ms()
                    cur.execute(
                        """
                        UPDATE account_item_tasks
                           SET status = %s,
                               done_at = CASE WHEN %s = 'done' THEN COALESCE(done_at, %s) ELSE NULL END,
                               updated_at = %s
                         WHERE id = %s
                        """,
                        (new_task_status, new_task_status, stamp, stamp, task_id),
                    )
                    # 子任务变了，主任务状态跟着对齐（全办结 → 主任务完成）
                    self.item_task_summary(cur, item_id)
                # 进度推进到「已完成」时同步任务状态；已退款/已取消的任务不再被改回进行中
                elif step == "已完成" and (item.get("status") or "") not in ("refunded", "cancelled"):
                    cur.execute(
                        "UPDATE account_items SET status = 'done', completed_at = COALESCE(completed_at, %s) WHERE id = %s",
                        (now_ms(), item_id),
                    )
                    # 主任务已完成：细分任务一起办结，展开后不会还挂着「未开始」
                    sync_item_tasks(cur, item_id, account_id, item.get("items") or "", "done",
                                    item.get("owner") or "")
                elif status == "doing":
                    cur.execute(
                        "UPDATE account_items SET status = 'doing'"
                        " WHERE id = %s AND status = 'pending'",
                        (item_id,),
                    )
                if not task:
                    recalc_order(cur, account_id)
                cur.execute(
                    "SELECT * FROM order_progress WHERE item_id = %s AND is_delete = 0"
                    " ORDER BY id DESC LIMIT 1",
                    (item_id,),
                )
                row = cur.fetchone()
            conn.commit()
        self.send_json({"code": 20000, "data": progress_out(row)})

    def progress_delete(self, body, user=None):
        rid = int(body.get("id") or 0)
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM order_progress WHERE id = %s", (rid,))
                row = cur.fetchone()
                if row is not None:
                    if row.get("task_id"):
                        task = self.load_task(cur, row["task_id"])
                        if not self.task_edit_allowed(user, task):
                            self.send_json({
                                "code": 50000,
                                "message": "这条跟进属于子任务，只有跟进人本人或管理员能删",
                            })
                            return
                    elif not self.is_admin(user):
                        self.send_json({"code": 50000, "message": "主任务级的系统记录只有管理员能删"})
                        return
                cur.execute(
                    "UPDATE order_progress SET is_delete = 1 WHERE id = %s AND is_delete = 0",
                    (rid,),
                )
            conn.commit()
        self.send_json({"code": 20000, "data": "success"})

    def progress_cancel(self, body, user):
        """取消订单（任务级）：记下取消原因和备注，可同时把金额清零（不计收入）。

        取消=这单不做了，所以默认把这条任务的收入冲成 0、成本保留（已发生的成本照样算），
        利润如实变负；如果只是标记状态、金额不想动，传 clear_amount=false。
        cancel_all=true 时连带取消同一订单下其它未取消/未退款的任务（整单作废时用）。
        """
        operator = user["username"] if user else ""
        item_id = int(body.get("item_id") or 0)
        reason = (body.get("reason") or "").strip()[:100]
        remark = (body.get("note") or "").strip()[:500]
        clear_amount = body.get("clear_amount")
        clear_amount = True if clear_amount is None else bool(clear_amount)
        cancel_all = bool(body.get("cancel_all"))
        stamp = now_ms()
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT i.*, a.order_no, a.client
                      FROM account_items i
                      JOIN account_records a ON a.id = i.account_id
                     WHERE i.id = %s AND i.is_delete = 0
                     FOR UPDATE
                    """,
                    (item_id,),
                )
                item = cur.fetchone()
                if item is None:
                    self.send_json({"code": 50000, "message": "任务不存在"})
                    return
                status = item.get("status") or "pending"
                if status == "cancelled":
                    self.send_json({"code": 50000, "message": "该任务已经是取消订单状态"})
                    return
                if status == "refunded":
                    self.send_json({"code": 50000, "message": "该任务已全额退款，不能再取消"})
                    return

                account_id = item["account_id"]
                targets = [item]
                if cancel_all:
                    cur.execute(
                        """
                        SELECT * FROM account_items
                         WHERE account_id = %s AND id <> %s AND is_delete = 0
                           AND status NOT IN ('cancelled', 'refunded')
                         ORDER BY sort, id
                         FOR UPDATE
                        """,
                        (account_id, item_id),
                    )
                    targets.extend(cur.fetchall())

                cleared = 0
                for target in targets:
                    revenue = float(target.get("revenue") or 0)
                    cost = float(target.get("cost") or 0)
                    new_revenue = 0.0 if clear_amount else revenue
                    new_profit = round(new_revenue - cost, 2)
                    cur.execute(
                        """
                        UPDATE account_items
                           SET status = 'cancelled', completed_at = %s, cancelled_at = %s,
                               cancel_reason = %s, cancel_note = %s,
                               revenue = %s, profit = %s
                         WHERE id = %s
                        """,
                        (stamp, stamp, reason, remark, new_revenue, new_profit, target["id"]),
                    )
                    note = "取消订单"
                    if reason:
                        note += "，原因：" + reason
                    if remark:
                        note += "；备注：" + remark
                    if clear_amount and revenue > 0.004:
                        note += "；金额 %s → 0（不计收入）" % format_amount(revenue)
                        cleared += 1
                    insert_progress(cur, account_id, "取消订单", "done", note, operator, stamp, target["id"])

                recalc_order(cur, account_id)
                cur.execute(
                    "SELECT status, revenue, profit, cancel_reason, cancelled_at FROM account_items WHERE id = %s",
                    (item_id,),
                )
                updated = cur.fetchone()
                cur.execute(
                    "SELECT status, revenue FROM account_records WHERE id = %s",
                    (account_id,),
                )
                order = cur.fetchone()
            conn.commit()
        self.send_json({
            "code": 20000,
            "data": {
                "item_id": item_id,
                "item_status": updated["status"],
                "revenue": float(updated["revenue"] or 0),
                "profit": float(updated["profit"] or 0),
                "cancel_reason": updated["cancel_reason"] or "",
                "cancelled_at": int(updated["cancelled_at"] or 0),
                "account_status": order["status"],
                "order_revenue": float(order["revenue"] or 0),
                "cancelled_count": len(targets),
                "cleared_count": cleared,
            },
        })

    def progress_refund(self, body, user):
        """订单退款：冲减任务收入 → 成本管理记一条「退款」支出 → 写一条跟进 → 回算订单状态。

        成本那条记录只用于看现金流出（kind='refund'），财务报表算利润时会排除，
        因为退款金额已经在订单收入里扣过一次，不能再当支出扣第二次。
        """
        item_id = int(body.get("item_id") or 0)
        if not item_id:
            self.send_json({"code": 50000, "message": "缺少任务 id"})
            return
        operator = user["username"] if user else ""
        stamp = now_ms()
        biz_date = datetime.fromtimestamp(stamp / 1000).strftime("%Y-%m-%d")
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT i.*, a.order_no, a.client
                      FROM account_items i
                      JOIN account_records a ON a.id = i.account_id
                     WHERE i.id = %s AND i.is_delete = 0
                     FOR UPDATE
                    """,
                    (item_id,),
                )
                item = cur.fetchone()
                if item is None:
                    self.send_json({"code": 50000, "message": "任务不存在"})
                    return
                status = item.get("status") or "pending"
                if status == "cancelled":
                    self.send_json({"code": 50000, "message": "该任务已取消，无需退款"})
                    return
                revenue = float(item.get("revenue") or 0)
                if revenue <= 0.004:
                    self.send_json({"code": 50000, "message": "该任务当前金额为 0，没有可退金额"})
                    return
                raw_amount = body.get("amount")
                amount = revenue if raw_amount in (None, "") else (to_number(raw_amount, 0) or 0)
                amount = round(amount, 2)
                if amount <= 0:
                    self.send_json({"code": 50000, "message": "退款金额必须大于 0"})
                    return
                if amount > revenue + 0.004:
                    self.send_json({
                        "code": 50000,
                        "message": "退款金额不能超过该任务当前金额 ¥" + format_amount(revenue),
                    })
                    return

                new_revenue = round(max(0.0, revenue - amount), 2)
                cost = float(item.get("cost") or 0)
                new_profit = round(new_revenue - cost, 2)
                full_refund = new_revenue <= 0.004
                new_status = "refunded" if full_refund else (
                    status if status in ("doing", "done") else "doing"
                )
                completed_at = stamp if full_refund else item.get("completed_at")
                cur.execute(
                    """
                    UPDATE account_items
                       SET revenue = %s, profit = %s, status = %s, completed_at = %s,
                           refund_amount = COALESCE(refund_amount, 0) + %s, refund_at = %s
                     WHERE id = %s
                    """,
                    (new_revenue, new_profit, new_status, completed_at, amount, stamp, item_id),
                )

                reason = (body.get("reason") or "").strip()
                method = (body.get("method") or "").strip()
                label = "、".join(
                    part for part in (item.get("order_no"), item.get("client"), item.get("license_name")) if part
                )
                remark = "订单退款：" + (label or ("任务#" + str(item_id)))
                if reason:
                    remark += "；原因：" + reason
                cur.execute(
                    """
                    INSERT INTO cost_records
                           (timestamp, biz_date, category, payee, amount, method,
                            related_order, remark, creator, kind)
                    VALUES (%s, %s, '退款', %s, %s, %s, %s, %s, %s, 'refund')
                    RETURNING id
                    """,
                    (
                        stamp, biz_date, item.get("client") or item.get("license_name") or "客户",
                        amount, method, item["account_id"], remark, operator,
                    ),
                )
                cost_id = cur.fetchone()["id"]

                note = "退款 ¥%s，任务金额 %s → %s" % (
                    format_amount(amount), format_amount(revenue), format_amount(new_revenue),
                )
                if reason:
                    note += "；原因：" + reason
                insert_progress(cur, item["account_id"], "退款", "done", note, operator, stamp, item_id)
                recalc_order(cur, item["account_id"])

                cur.execute(
                    "SELECT revenue, profit, status, refund_amount FROM account_items WHERE id = %s",
                    (item_id,),
                )
                updated = cur.fetchone()
                cur.execute(
                    "SELECT status, revenue FROM account_records WHERE id = %s",
                    (item["account_id"],),
                )
                order = cur.fetchone()
            conn.commit()
        self.send_json({
            "code": 20000,
            "data": {
                "item_id": item_id,
                "cost_id": cost_id,
                "refund": amount,
                "revenue": float(updated["revenue"] or 0),
                "profit": float(updated["profit"] or 0),
                "item_status": updated["status"],
                "refund_amount": float(updated["refund_amount"] or 0),
                "account_status": order["status"],
                "order_revenue": float(order["revenue"] or 0),
            },
        })

    def progress_owners(self):
        """主跟进人候选：系统用户 + 历史上出现过的跟进人（不要求管理员权限）。"""
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT username, name, avatar FROM users ORDER BY id")
                users = [{
                    "username": row["username"],
                    "name": row["name"] or row["username"],
                    "avatar": row["avatar"] or "",
                } for row in cur.fetchall()]
                cur.execute(
                    "SELECT DISTINCT operator FROM order_progress"
                    " WHERE COALESCE(operator, '') <> '' AND is_delete = 0 ORDER BY operator"
                )
                operators = [row["operator"] for row in cur.fetchall()]
        known = {item["username"] for item in users} | {item["name"] for item in users}
        for name in operators:
            if name and name not in known:
                users.append({"username": name, "name": name, "avatar": ""})
        self.send_json({"code": 20000, "data": {"items": users}})

    def progress_owner_set(self, body, user):
        """设置/清空某条任务的主跟进人（传空字符串表示改回自动推断）。"""
        item_id = int(body.get("item_id") or 0)
        owner = (body.get("owner") or "").strip()
        if not item_id:
            self.send_json({"code": 50000, "message": "缺少任务 id"})
            return
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM account_items WHERE id = %s AND is_delete = 0", (item_id,))
                if cur.fetchone() is None:
                    self.send_json({"code": 50000, "message": "任务不存在"})
                    return
                cur.execute(
                    "UPDATE account_items SET owner = %s, owner_updated_at = %s WHERE id = %s",
                    (owner or None, now_ms(), item_id),
                )
            conn.commit()
        self.send_json({"code": 20000, "data": {"item_id": item_id, "owner": owner}})

    # ---------------- 细分任务（执照下的业务项） ----------------

    def item_task_summary(self, cur, item_id, quiet=False):
        """回算一条任务的细分进度，顺手把主任务状态对齐。

        主任务只有两个状态：细分任务全办结 → 已完成；否则一律「进行中」
        （没有子任务可拆时，只把「待定」收成「进行中」，已完成 / 已取消不动）。
        quiet=True 时只对齐状态，不写跟进、不重算订单（订单保存流程里自己会重算）。
        """
        cur.execute(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'done') AS done,
                   COUNT(*) FILTER (WHERE status = 'doing') AS doing,
                   COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled
              FROM account_item_tasks WHERE item_id = %s AND is_delete = 0
            """,
            (item_id,),
        )
        stat = cur.fetchone()
        total = int(stat["total"] or 0)
        done = int(stat["done"] or 0)
        doing = int(stat["doing"] or 0)
        cancelled = int(stat["cancelled"] or 0)
        cur.execute("SELECT * FROM account_items WHERE id = %s FOR UPDATE", (item_id,))
        item = cur.fetchone()
        if item is None:
            return {"total": total, "done": done, "status": ""}
        if not total:
            # 没有可拆的子任务：待定收成进行中，别写状态变更记录免得时间线刷屏
            if (item["status"] or "") == "pending":
                cur.execute("UPDATE account_items SET status = 'doing' WHERE id = %s", (item_id,))
                if not quiet:
                    recalc_order(cur, item["account_id"])
                return {"total": 0, "done": 0, "status": "doing"}
            return {"total": 0, "done": 0, "status": item["status"] or ""}
        status = item["status"] or "pending"
        stamp = now_ms()
        new_status = status
        if status in ("pending", "doing", "done"):
            if cancelled >= total:
                # 子任务全被取消了：这个执照没有要做的事，随单取消，
                # 别一直挂在「进行中」堵着整单（整单状态由 recalc_order 收口）
                new_status = "cancelled"
            else:
                # 全办结 → 已完成；其余（含刚加了一条新子任务）→ 进行中
                new_status = "done" if done >= total else "doing"
        if new_status != status:
            cur.execute(
                """
                UPDATE account_items
                   SET status = %s,
                       completed_at = CASE WHEN %s = 'done' THEN %s ELSE NULL END,
                       cancelled_at = CASE WHEN %s = 'cancelled' THEN COALESCE(cancelled_at, %s) ELSE NULL END
                 WHERE id = %s
                """,
                (new_status, new_status, stamp, new_status, stamp, item_id),
            )
            if not quiet:
                if new_status == "done":
                    note = "细分任务 %d/%d 已办结，任务自动标记完成" % (done, total)
                elif new_status == "cancelled":
                    note = "细分任务已全部取消，执照任务随单取消"
                elif status == "done":
                    note = "细分任务被重新打开，任务状态回到「%s」" % ITEM_STATUS_LABELS.get(new_status, new_status)
                else:
                    note = "细分任务未全部办结，任务状态改为「%s」" % ITEM_STATUS_LABELS.get(new_status, new_status)
                insert_progress(
                    cur, item["account_id"], "取消订单" if new_status == "cancelled" else ("已完成" if new_status == "done" else "状态变更"),
                    "done" if new_status == "done" else "doing", note,
                    "", stamp, item_id,
                )
                recalc_order(cur, item["account_id"])
        return {"total": total, "done": done, "status": new_status}

    def progress_tasks_list(self, query):
        """取细分任务：传 account_id 一次取整个订单下所有执照的，传 item_id 只取一条执照的。

        订单编辑弹窗里用它把每个执照按业务项拆出来的子任务回显出来。
        """
        account_id = int(query.get("account_id") or 0)
        item_id = int(query.get("item_id") or 0)
        if not account_id and not item_id:
            self.send_json({"code": 50000, "message": "缺少订单 id 或任务 id"})
            return
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if item_id:
                    cur.execute("SELECT id FROM account_items WHERE id = %s AND is_delete = 0", (item_id,))
                else:
                    cur.execute(
                    "SELECT id FROM account_items WHERE account_id = %s AND is_delete = 0 ORDER BY sort, id",
                    (account_id,),
                )
                ids = [row["id"] for row in cur.fetchall()]
                grouped = fetch_item_tasks(cur, ids)
        self.send_json({"code": 20000, "data": {"tasks": {str(key): value for key, value in grouped.items()}}})

    def load_task(self, cur, task_id):
        if not task_id:
            return None
        cur.execute("SELECT * FROM account_item_tasks WHERE id = %s AND is_delete = 0", (task_id,))
        return cur.fetchone()

    def task_edit_allowed(self, user, task):
        """子任务只有它的跟进人本人和管理员能改；还没指定跟进人时谁都能改，第一次改就认领。"""
        if not task:
            return False
        if self.is_admin(user):
            return True
        username = (user or {}).get("username") or ""
        if not username:
            return False
        owner = (task.get("owner") or "").strip()
        return (not owner) or owner == username

    def claim_task(self, cur, user, task):
        """无跟进人的子任务被编辑时，把操作人记成跟进人（管理员代改不改归属）。"""
        if not task or task.get("owner") or not user or self.is_admin(user):
            return
        cur.execute(
            "UPDATE account_item_tasks SET owner = %s, updated_at = %s"
            " WHERE id = %s AND COALESCE(owner, '') = ''",
            (user["username"], now_ms(), task["id"]),
        )

    def progress_task_status(self, body, user):
        """把某个细分任务改成 未开始 / 办理中 / 已办结 / 已取消。"""
        task_id = int(body.get("id") or 0)
        status = str(body.get("status") or "").strip()
        if not task_id or status not in TASK_STATUS_LABELS:
            self.send_json({"code": 50000, "message": "缺少细分任务 id 或状态不合法"})
            return
        stamp = now_ms()
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM account_item_tasks WHERE id = %s AND is_delete = 0 FOR UPDATE", (task_id,))
                row = cur.fetchone()
                if row is None:
                    self.send_json({"code": 50000, "message": "细分任务不存在"})
                    return
                if not self.task_edit_allowed(user, row):
                    self.send_json({
                        "code": 50000,
                        "message": "这条子任务的跟进人是 %s，只有跟进人本人或管理员能改" % (row.get("owner") or "—"),
                    })
                    return
                cur.execute(
                    """
                    UPDATE account_item_tasks
                       SET status = %s,
                           done_at = CASE WHEN %s = 'done' THEN COALESCE(done_at, %s) ELSE NULL END,
                           owner = COALESCE(NULLIF(owner, ''), %s),
                           updated_at = %s
                     WHERE id = %s RETURNING *
                    """,
                    (status, status, stamp, user["username"] if user else "", stamp, task_id),
                )
                row = cur.fetchone()
                summary = self.item_task_summary(cur, row["item_id"])
            conn.commit()
        self.send_json({"code": 20000, "data": {"task": task_out(row), "summary": summary}})

    def progress_task_add(self, body, user):
        """手工补一条细分任务（业务项里没有的临时事项）。"""
        item_id = int(body.get("item_id") or 0)
        name = str(body.get("name") or "").strip()[:60]
        if not item_id or not name:
            self.send_json({"code": 50000, "message": "缺少任务 id 或细分任务名称"})
            return
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, account_id FROM account_items WHERE id = %s AND is_delete = 0", (item_id,))
                item = cur.fetchone()
                if item is None:
                    self.send_json({"code": 50000, "message": "任务不存在"})
                    return
                cur.execute(
                    "SELECT COALESCE(MAX(sort), -1) + 1 AS next"
                    " FROM account_item_tasks WHERE item_id = %s AND is_delete = 0",
                    (item_id,),
                )
                sort = int(cur.fetchone()["next"] or 0)
                cur.execute(
                    """
                    INSERT INTO account_item_tasks
                           (item_id, account_id, name, line, status, owner, updated_at, sort, source)
                    VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s, 'manual')
                    RETURNING *
                    """,
                    (item_id, item["account_id"], name, task_line_of(name),
                     user["username"] if user else "", now_ms(), sort),
                )
                row = cur.fetchone()
                summary = self.item_task_summary(cur, item_id)
            conn.commit()
        self.send_json({"code": 20000, "data": {"task": task_out(row), "summary": summary}})

    def progress_task_delete(self, body, user=None):
        item_id = int(body.get("id") or 0)
        if not item_id:
            self.send_json({"code": 50000, "message": "缺少细分任务 id"})
            return
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM account_item_tasks WHERE id = %s AND is_delete = 0", (item_id,))
                row = cur.fetchone()
                if row is None:
                    self.send_json({"code": 50000, "message": "细分任务不存在"})
                    return
                if not self.task_edit_allowed(user, row):
                    self.send_json({
                        "code": 50000,
                        "message": "这条子任务的跟进人是 %s，只有跟进人本人或管理员能删" % (row.get("owner") or "—"),
                    })
                    return
                task_item = row["item_id"]
                cur.execute(
                    "UPDATE account_item_tasks SET is_delete = 1 WHERE id = %s AND is_delete = 0",
                    (item_id,),
                )
                summary = self.item_task_summary(cur, task_item)
            conn.commit()
        self.send_json({"code": 20000, "data": {"summary": summary}})

    def progress_task_owner(self, body, user):
        """子任务的跟进人：管理员可改给任何人；当前跟进人可以把任务转给别人。

        留空表示回到「未分配」，之后谁先动手谁认领。
        """
        task_id = int(body.get("id") or 0)
        owner = str(body.get("owner") or "").strip()[:60]
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM account_item_tasks WHERE id = %s AND is_delete = 0 FOR UPDATE", (task_id,))
                row = cur.fetchone()
                if row is None:
                    self.send_json({"code": 50000, "message": "细分任务不存在"})
                    return
                username = (user or {}).get("username") or ""
                current = (row.get("owner") or "").strip()
                if not self.is_admin(user) and current and current != username:
                    self.send_json({
                        "code": 50000,
                        "message": "只有跟进人本人或管理员能转派这条子任务",
                    })
                    return
                cur.execute(
                    "UPDATE account_item_tasks SET owner = %s, updated_at = %s WHERE id = %s RETURNING *",
                    (owner, now_ms(), task_id),
                )
                row = cur.fetchone()
            conn.commit()
        self.send_json({"code": 20000, "data": {"task": task_out(row)}})

    # ---------------- 成本记录 ----------------

    def cost_values(self, body, user, existing=None):
        def pick(key, default=""):
            if key in body:
                return body.get(key)
            if existing is not None:
                return existing.get(key)
            return default

        stamp = parse_ms(body.get("timestamp") if "timestamp" in body else (existing["timestamp"] if existing else None))
        biz_date = pick("biz_date")
        if not biz_date:
            biz_date = datetime.fromtimestamp(stamp / 1000).strftime("%Y-%m-%d")
        related = pick("related_order", None)
        try:
            related = int(related) if related not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            related = None
        return {
            "timestamp": stamp,
            "biz_date": biz_date,
            "category": pick("category"),
            "payee": pick("payee"),
            "amount": to_number(pick("amount"), 0) or 0,
            "method": pick("method"),
            "related_order": related,
            "remark": pick("remark"),
            "creator": pick("creator") or (user["username"] if user else ""),
        }

    def cost_list(self, query):
        # 默认只看正常数据；include_deleted=1 时把已删除的也带出来供核对/恢复
        include_deleted = str((query or {}).get("include_deleted") or "") in ("1", "true", "yes")
        where = [] if include_deleted else ["is_delete = 0"]
        params = []
        keyword = (query.get("keyword") or "").strip()
        if keyword:
            where.append("(payee ILIKE %s OR remark ILIKE %s OR category ILIKE %s)")
            params.extend(["%" + keyword + "%"] * 3)
        if query.get("category"):
            where.append("category = %s")
            params.append(query["category"])
        if query.get("start"):
            where.append("biz_date >= %s")
            params.append(query["start"])
        if query.get("end"):
            where.append("biz_date <= %s")
            params.append(query["end"])
        condition = (" WHERE " + " AND ".join(where)) if where else ""
        page = max(int(query.get("page") or 1), 1)
        limit = min(max(int(query.get("limit") or 20), 1), 200)
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) AS total, COALESCE(SUM(amount), 0) AS amount FROM cost_records" + condition, params)
                row = cur.fetchone()
                total = int(row["total"] or 0)
                amount = float(row["amount"] or 0)
                cur.execute(
                    "SELECT * FROM cost_records" + condition + " ORDER BY biz_date DESC, id DESC LIMIT %s OFFSET %s",
                    params + [limit, (page - 1) * limit],
                )
                items = [cost_out(item) for item in cur.fetchall()]
        self.send_json({
            "code": 20000,
            "data": {"total": total, "amount": amount, "items": items, "categories": COST_CATEGORIES},
        })

    def cost_summary(self, query):
        month = (query.get("month") or "").strip()
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS amount"
                    " FROM cost_records WHERE is_delete = 0"
                )
                overall = cur.fetchone()
                if month:
                    cur.execute(
                        "SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS amount"
                        " FROM cost_records WHERE is_delete = 0 AND LEFT(biz_date, 7) = %s",
                        (month,),
                    )
                    month_row = cur.fetchone()
                else:
                    month_row = {"cnt": 0, "amount": 0}
                cur.execute("""
                    SELECT COALESCE(NULLIF(category, ''), '未分类') AS category,
                           COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS amount
                      FROM cost_records WHERE is_delete = 0 GROUP BY 1 ORDER BY amount DESC
                """)
                by_category = [
                    {"category": row["category"], "count": int(row["cnt"]), "amount": float(row["amount"] or 0)}
                    for row in cur.fetchall()
                ]
                cur.execute("""
                    SELECT COALESCE(NULLIF(biz_date, ''), '未填日期') AS biz_date,
                           COALESCE(SUM(amount), 0) AS amount
                      FROM cost_records WHERE is_delete = 0 GROUP BY 1 ORDER BY 1 DESC LIMIT 6
                """)
                by_date = [{"biz_date": row["biz_date"], "amount": float(row["amount"] or 0)} for row in cur.fetchall()]
        self.send_json({
            "code": 20000,
            "data": {
                "total": float(overall["amount"] or 0),
                "count": int(overall["cnt"] or 0),
                "month": month,
                "month_total": float(month_row["amount"] or 0),
                "month_count": int(month_row["cnt"] or 0),
                "by_category": by_category,
                "by_date": by_date,
                "categories": COST_CATEGORIES,
            },
        })

    def dashboard_overview(self):
        """首页分析：KPI、近 6 个月趋势、收入/成本结构、订单进度分布、待办清单。"""

        def money(value):
            return round(float(value or 0), 2)

        now = datetime.now()
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM account_records WHERE is_delete = 0 ORDER BY id DESC")
                accounts = cur.fetchall()
                cur.execute("SELECT * FROM cost_records WHERE is_delete = 0")
                costs = cur.fetchall()
                cur.execute(
                    """
                    SELECT DISTINCT ON (account_id) account_id, step, status, note, timestamp
                      FROM order_progress
                     WHERE is_delete = 0
                     ORDER BY account_id, timestamp DESC, id DESC
                    """
                )
                latest = {row["account_id"]: row for row in cur.fetchall()}
                cur.execute(
                    "SELECT account_id, COUNT(*) AS cnt FROM order_progress"
                    " WHERE is_delete = 0 GROUP BY account_id"
                )
                counts = {row["account_id"]: int(row["cnt"] or 0) for row in cur.fetchall()}

        months = [shift_month(now, offset).strftime("%Y-%m") for offset in range(-5, 1)]
        trend = {key: {"revenue": 0.0, "cost": 0.0, "profit": 0.0, "orders": 0} for key in months}
        revenue_total = 0.0
        order_cost_total = 0.0
        # 收入按订单状态拆开：已完成才是真收入，进行中算在途，待定单独看
        revenue_done = 0.0
        order_cost_done = 0.0
        revenue_doing = 0.0
        revenue_pending = 0.0
        revenue_other = 0.0
        month_done_revenue = 0.0
        by_category = {}
        by_status = {"pending": 0, "doing": 0, "done": 0}
        by_client = {}

        for row in accounts:
            revenue = float(row["revenue"] or 0)
            cost = float(row["cost"] or 0)
            status = row["status"] or "pending"
            revenue_total += revenue
            order_cost_total += cost
            if status == "done":
                revenue_done += revenue
                order_cost_done += cost
            elif status == "doing":
                revenue_doing += revenue
            elif status == "pending":
                revenue_pending += revenue
            else:
                # 已退款 / 取消订单：金额一般已冲成 0，单独归一类，不混进在途和待定
                revenue_other += revenue
            month = biz_month_key(row["biz_date"], row.get("created_at"))
            if month in trend:
                # 趋势图的「订单数」仍按下单月统计（开单量）；收支按下面完成月的口径走
                trend[month]["orders"] += 1
            # 订单哪个月完成，收入就算哪个月：已完成订单的收入 / 成本都归完成月；
            # 在途订单的钱还没赚到，收入不进趋势，成本也不摊进月度利润
            if status == "done":
                month = ms_month_key(row.get("completed_at")) or month
                if month in trend:
                    trend[month]["revenue"] += revenue
                    trend[month]["cost"] += cost
                    trend[month]["done_revenue"] = trend[month].get("done_revenue", 0.0) + revenue
                    trend[month]["done_cost"] = trend[month].get("done_cost", 0.0) + cost
            category = (row["category"] or "").strip() or "未分类"
            bucket = by_category.setdefault(
                category, {"name": category, "revenue": 0.0, "cost": 0.0, "profit": 0.0, "count": 0}
            )
            bucket["revenue"] += revenue
            bucket["cost"] += cost
            bucket["profit"] += revenue - cost
            bucket["count"] += 1
            by_status[status] = by_status.get(status, 0) + 1
            client = (row["client"] or "").strip() or "散客"
            client_bucket = by_client.setdefault(
                client, {"client": client, "revenue": 0.0, "profit": 0.0, "orders": 0}
            )
            client_bucket["revenue"] += revenue
            client_bucket["profit"] += revenue - cost
            client_bucket["orders"] += 1

        extra_cost_total = 0.0
        refund_cost_total = 0.0
        cost_by_category = {}
        for row in costs:
            amount = float(row["amount"] or 0)
            # 退单成本（取消/退款时退给客户的钱）既是现金流出也是收入抵减：
            # 不进经营成本，单独归集给首页总收入 / 总支出 / 净利润，以及本月利润
            if (row.get("kind") or "") == "refund":
                refund_cost_total += amount
                month = biz_month_key(row["biz_date"], row.get("created_at"))
                if month in trend:
                    trend[month]["refund_cost"] = trend[month].get("refund_cost", 0.0) + amount
                continue
            extra_cost_total += amount
            month = biz_month_key(row["biz_date"], row.get("created_at"))
            if month in trend:
                trend[month]["cost"] += amount
                trend[month]["extra_cost"] = trend[month].get("extra_cost", 0.0) + amount
            category = (row["category"] or "").strip() or "未分类"
            bucket = cost_by_category.setdefault(category, {"name": category, "amount": 0.0, "count": 0})
            bucket["amount"] += amount
            bucket["count"] += 1

        for key in months:
            trend[key]["profit"] = trend[key]["revenue"] - trend[key]["cost"]

        total_cost = order_cost_total + extra_cost_total
        # 总支出（全部现金流出）= 经营成本 + 订单成本 + 退单成本；只用于展示，不参与利润
        total_cost_all = total_cost + refund_cost_total
        profit_total = revenue_total - total_cost
        # 首页「总收入 / 净利润」按已完成订单口径：执照任务没全部办结的订单，
        # 钱还没赚到，收入不进总收入，成本也不参与毛利
        # 被退的订单不计入 revenue_done，它的收入冲减也不影响已完成订单口径，
        # 所以退单成本要在这里单独扣一次，否则退款损失会漏在净利润之外
        profit_done = revenue_done - order_cost_done - extra_cost_total - refund_cost_total
        # 和净利润对得上的支出：已完成订单成本 + 经营成本（在途订单成本单独摆出来，免得对不上账）
        total_cost_done = order_cost_done + extra_cost_total
        order_cost_open = order_cost_total - order_cost_done
        done_count = by_status.get("done", 0)
        doing_count = by_status.get("doing", 0)
        pending_count = by_status.get("pending", 0)
        orders = len(accounts)
        current, previous = months[-1], months[-2]
        month_revenue = trend[current]["revenue"]
        month_done_revenue = trend[current].get("done_revenue", 0.0)
        prev_done_revenue = trend[previous].get("done_revenue", 0.0)
        done_growth = (
            round((month_done_revenue - prev_done_revenue) / prev_done_revenue * 100, 1)
            if prev_done_revenue else None
        )
        month_cost = trend[current]["cost"]
        # 本月「已完成口径」毛利：只算已办结订单的收入与成本，经营成本全算，
        # 再减去本月退单成本（取支出管理里的退款记录，按发生月归集，与总收入/总支出同口径）
        month_refund_cost = trend[current].get("refund_cost", 0.0)
        month_profit_done = (
            month_done_revenue
            - trend[current].get("done_cost", 0.0)
            - trend[current].get("extra_cost", 0.0)
            - month_refund_cost
        )
        prev_revenue = trend[previous]["revenue"]
        growth = round((month_revenue - prev_revenue) / prev_revenue * 100, 1) if prev_revenue else None

        now_ts = now.timestamp()
        todos = []
        for row in accounts:
            last = latest.get(row["id"])
            step = (last["step"] if last else "") or ""
            progress_status = (last["status"] if last else "") or ""
            if (row["status"] or "") == "done" or step == "已完成":
                continue
            stamp = int((last["timestamp"] if last else row["timestamp"]) or 0)
            stamp_sec = stamp / 1000.0 if stamp > 1e11 else float(stamp)
            days = max(0, int((now_ts - stamp_sec) // 86400)) if stamp else 0
            if progress_status == "blocked":
                level, reason = "danger", "进度受阻"
            elif last is None:
                level, reason = "danger", "还没有跟进记录"
            elif days >= 7:
                level, reason = "danger", "已 %d 天未更新" % days
            elif days >= 3:
                level, reason = "warning", "已 %d 天未更新" % days
            else:
                level, reason = "normal", "正常推进"
            if step in PROGRESS_STEPS:
                index = PROGRESS_STEPS.index(step)
                next_step = PROGRESS_STEPS[index + 1] if index + 1 < len(PROGRESS_STEPS) else "已完成"
            else:
                next_step = PROGRESS_STEPS[1]
            revenue = float(row["revenue"] or 0)
            cost = float(row["cost"] or 0)
            todos.append({
                "id": row["id"],
                "client": row["client"] or "",
                "items": row["items"] or "",
                "category": row["category"] or "",
                "biz_date": row["biz_date"] or "",
                "status": row["status"] or "pending",
                "revenue": money(revenue),
                "profit": money(revenue - cost),
                "last_step": step,
                "last_status": progress_status,
                "last_note": (last["note"] if last else "") or "",
                "next_step": next_step,
                "progress_count": counts.get(row["id"], 0),
                "days": days,
                "level": level,
                "reason": reason,
            })
        level_rank = {"danger": 0, "warning": 1, "normal": 2}
        todos.sort(key=lambda item: (level_rank[item["level"]], -item["days"], -item["revenue"]))

        step_counter = {}
        for row in latest.values():
            step_counter[row["step"]] = step_counter.get(row["step"], 0) + 1
        step_dist = [
            {"step": step, "count": step_counter.get(step, 0)}
            for step in PROGRESS_STEPS
            if step_counter.get(step, 0)
        ]

        self.send_json({
            "code": 20000,
            "data": {
                "kpi": {
                    # revenue / profit 仍是全部订单口径，给图表和其它地方用
                    "revenue": money(revenue_total),
                    "profit": money(profit_total),
                    "margin": round(profit_total / revenue_total * 100, 1) if revenue_total else 0,
                    # 已完成订单口径：首页「总收入 / 净利润」按这个显示
                    "revenue_done": money(revenue_done),
                    "profit_done": money(profit_done),
                    "margin_done": round(profit_done / revenue_done * 100, 1) if revenue_done else 0,
                    # 在途（进行中）与待定订单的金额
                    "revenue_doing": money(revenue_doing),
                    "revenue_pending": money(revenue_pending),
                    "revenue_other": money(revenue_other),
                    "count_done": done_count,
                    "count_doing": doing_count,
                    "count_pending": pending_count,
                    "avg_done": money(revenue_done / done_count) if done_count else 0,
                    "avg_doing": money(revenue_doing / doing_count) if doing_count else 0,
                    "avg_pending": money(revenue_pending / pending_count) if pending_count else 0,
                    "month_revenue_done": money(month_done_revenue),
                    "month_done_growth": done_growth,
                    "month_profit_done": money(month_profit_done),
                    "order_cost": money(order_cost_total),
                    # 已完成订单对应的成本，净利润口径用它，避免在途订单的成本摊进毛利
                    "order_cost_done": money(order_cost_done),
                    # 在途（未办结）订单的成本，不进净利润，单独展示好对账
                    "order_cost_open": money(order_cost_open),
                    "extra_cost": money(extra_cost_total),
                    # 退单成本：首页总收入 / 净利润 / 总支出用支出管理里的退款记录金额
                    "refund_cost": money(refund_cost_total),
                    # 本月退单成本：支出管理里的退款记录按发生月归集，单独给「本月利润」扣减
                    "month_refund_cost": money(month_refund_cost),
                    "total_cost": money(total_cost),
                    # 首页「总支出」用这个：经营成本 + 订单成本 + 退单成本
                    "total_cost_all": money(total_cost_all),
                    # 与净利润同口径的支出：已完成订单成本 + 经营成本
                    "total_cost_done": money(total_cost_done),
                    # 本月已完成口径的四段（收入 / 订单成本 / 经营成本 / 本月退单成本）
                    "month_order_cost_done": money(trend[current].get("done_cost", 0.0)),
                    "month_extra_cost": money(trend[current].get("extra_cost", 0.0)),
                    "month_refund_cost": money(month_refund_cost),
                    "orders": orders,
                    "avg_ticket": money(revenue_total / orders) if orders else 0,
                    "month_revenue": money(month_revenue),
                    "month_cost": money(month_cost),
                    "month_profit": money(trend[current]["profit"]),
                    "month_growth": growth,
                    "open_orders": len(todos),
                    "risk_orders": len([item for item in todos if item["level"] == "danger"]),
                    "pending_orders": pending_count,
                },
                "trend": {
                    "months": months,
                    "revenue": [money(trend[key]["revenue"]) for key in months],
                    "cost": [money(trend[key]["cost"]) for key in months],
                    "refund_cost": [money(trend[key].get("refund_cost", 0.0)) for key in months],
                    "profit": [money(trend[key]["profit"]) for key in months],
                    "orders": [trend[key]["orders"] for key in months],
                },
                "revenue_by_category": sorted(
                    [{**item, "revenue": money(item["revenue"]), "cost": money(item["cost"]),
                      "profit": money(item["profit"])} for item in by_category.values()],
                    key=lambda item: item["revenue"],
                    reverse=True,
                ),
                "cost_by_category": sorted(
                    [{"name": "订单直接成本", "amount": money(order_cost_total), "count": orders}]
                    + [{**item, "amount": money(item["amount"])} for item in cost_by_category.values()],
                    key=lambda item: item["amount"],
                    reverse=True,
                ),
                "status_dist": [
                    {"key": "pending", "name": "待定", "count": by_status.get("pending", 0)},
                    {"key": "doing", "name": "进行中", "count": by_status.get("doing", 0)},
                    {"key": "done", "name": "已完成", "count": by_status.get("done", 0)},
                    {"key": "refunded", "name": "已退款", "count": by_status.get("refunded", 0)},
                    {"key": "cancelled", "name": "取消订单", "count": by_status.get("cancelled", 0)},
                ],
                "step_dist": step_dist,
                "todos": todos[:20],
                "top_clients": sorted(
                    [{**item, "revenue": money(item["revenue"]), "profit": money(item["profit"])}
                     for item in by_client.values()],
                    key=lambda item: item["revenue"],
                    reverse=True,
                )[:6],
                "recent": [account_out(row) for row in accounts[:8]],
            },
        })

    def cost_create(self, body, user):
        values = self.cost_values(body, user)
        if not values["category"]:
            self.send_json({"code": 50000, "message": "请选择成本类别"})
            return
        columns = COST_FIELDS
        params = [values[column] for column in columns]
        sql = (
            "INSERT INTO cost_records (" + ", ".join(columns) + ") VALUES ("
            + ", ".join(["%s"] * len(columns)) + ") RETURNING *"
        )
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
            conn.commit()
        self.send_json({"code": 20000, "data": cost_out(row)})

    def cost_update(self, body):
        record_id = int(body.get("id") or 0)
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM cost_records WHERE id = %s AND is_delete = 0",
                    (record_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    self.send_json({"code": 50000, "message": "成本记录不存在"})
                    return
                values = self.cost_values(body, None, existing)
                assignments = []
                params = []
                for column in COST_FIELDS:
                    if column not in body and column not in ("timestamp",):
                        continue
                    assignments.append(column + " = %s")
                    params.append(values[column])
                if not assignments:
                    self.send_json({"code": 20000, "data": cost_out(existing)})
                    return
                params.append(record_id)
                cur.execute(
                    "UPDATE cost_records SET " + ", ".join(assignments) + " WHERE id = %s RETURNING *",
                    params,
                )
                row = cur.fetchone()
            conn.commit()
        self.send_json({"code": 20000, "data": cost_out(row)})

    def cost_delete(self, body):
        """软删除：只标记状态，不删库。"""
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE cost_records SET is_delete = 1 WHERE id = %s AND is_delete = 0",
                    (int(body.get("id") or 0),),
                )
            conn.commit()
        self.send_json({"code": 20000, "data": "success"})

    def cost_restore(self, body):
        """恢复一条已删除的支出记录。"""
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE cost_records SET is_delete = 0 WHERE id = %s AND is_delete = 1",
                    (int(body.get("id") or 0),),
                )
            conn.commit()
        self.send_json({"code": 20000, "data": "success"})

    def routes(self):
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT routes FROM roles WHERE key = 'admin'")
                row = cur.fetchone()
        self.send_json({"code": 20000, "data": row["routes"] if row else []})

    def roles(self):
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT r.key, r.name, r.description, r.routes,
                           (SELECT COUNT(*) FROM users u WHERE r.key = ANY(u.roles)) AS user_count
                      FROM roles r
                     ORDER BY r.id
                    """
                )
                items = []
                for row in cur.fetchall():
                    item = dict(row)
                    item["user_count"] = int(item.get("user_count") or 0)
                    items.append(item)
        self.send_json({"code": 20000, "data": items})

    # ---------------- 菜单管理 ----------------

    def menu_list(self):
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM menus ORDER BY parent ASC, sort ASC, id ASC")
                rows = cur.fetchall()
        self.send_json({"code": 20000, "data": [menu_out(row) for row in rows]})

    def menu_create(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可新增菜单")
            return
        path = (body.get("path") or "").strip()
        title = (body.get("title") or "").strip()
        if not path or not title:
            self.send_json({"code": 50000, "message": "页面和菜单名称不能为空"})
            return
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM menus WHERE path = %s", (path,))
                if cur.fetchone():
                    self.send_json({"code": 50000, "message": "该页面已经在菜单里了"})
                    return
                cur.execute(
                    """
                    INSERT INTO menus (path, title, icon, parent, sort, visible)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        path, title, body.get("icon") or "", body.get("parent") or "",
                        int(body.get("sort") or 0), bool(body.get("visible", True)),
                    ),
                )
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    def menu_update(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可修改菜单")
            return
        menu_id = int(body.get("id") or 0)
        path = (body.get("path") or "").strip()
        title = (body.get("title") or "").strip()
        if not menu_id or not path or not title:
            self.send_json({"code": 50000, "message": "菜单信息不完整"})
            return
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM menus WHERE path = %s AND id <> %s", (path, menu_id))
                if cur.fetchone():
                    self.send_json({"code": 50000, "message": "该页面已经被别的菜单占用"})
                    return
                cur.execute(
                    """
                    UPDATE menus SET path = %s, title = %s, icon = %s, parent = %s, sort = %s, visible = %s
                     WHERE id = %s
                    """,
                    (
                        path, title, body.get("icon") or "", body.get("parent") or "",
                        int(body.get("sort") or 0), bool(body.get("visible", True)), menu_id,
                    ),
                )
                if cur.rowcount == 0:
                    self.send_json({"code": 50000, "message": "菜单不存在"})
                    return
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    def menu_delete(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可删除菜单")
            return
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM menus WHERE id = %s", (int(body.get("id") or 0),))
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    # ---------------- 平台管理 ----------------

    def platform_list(self, query=None):
        keyword = (query or {}).get("keyword", "").strip()
        where_sql = ""
        params = []
        if keyword:
            where_sql = " WHERE name ILIKE %s OR remark ILIKE %s"
            keyword = "%" + keyword + "%"
            params = [keyword, keyword]
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT p.*,
                           (SELECT COUNT(*) FROM account_records a
                             WHERE a.platform = p.name AND a.is_delete = 0) AS order_count
                      FROM platforms p
                    """ + where_sql + " ORDER BY p.sort ASC, p.id ASC",
                    params,
                )
                rows = cur.fetchall()
        items = [{
            "id": row["id"],
            "name": row["name"],
            "sort": int(row["sort"] or 0),
            "remark": row["remark"] or "",
            "order_count": int(row["order_count"] or 0),
        } for row in rows]
        self.send_json({"code": 20000, "data": items})

    def platform_create(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可新增平台")
            return
        name = (body.get("name") or "").strip()
        if not name:
            self.send_json({"code": 50000, "message": "平台名称不能为空"})
            return
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM platforms WHERE name = %s", (name,))
                if cur.fetchone():
                    self.send_json({"code": 50000, "message": "平台已存在"})
                    return
                cur.execute(
                    "INSERT INTO platforms (name, sort, remark) VALUES (%s, %s, %s)",
                    (name, int(body.get("sort") or 0), body.get("remark") or ""),
                )
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    def platform_update(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可修改平台")
            return
        platform_id = int(body.get("id") or 0)
        name = (body.get("name") or "").strip()
        if not platform_id or not name:
            self.send_json({"code": 50000, "message": "平台信息不完整"})
            return
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM platforms WHERE name = %s AND id <> %s", (name, platform_id))
                if cur.fetchone():
                    self.send_json({"code": 50000, "message": "平台名称已存在"})
                    return
                cur.execute(
                    "UPDATE platforms SET name = %s, sort = %s, remark = %s WHERE id = %s",
                    (name, int(body.get("sort") or 0), body.get("remark") or "", platform_id),
                )
                if cur.rowcount == 0:
                    self.send_json({"code": 50000, "message": "平台不存在"})
                    return
                # 订单上存的平台名跟着改，保证统计口径一致
                if body.get("rename_orders", True):
                    old = body.get("old_name") or ""
                    if old and old != name:
                        cur.execute("UPDATE account_records SET platform = %s WHERE platform = %s", (name, old))
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    def platform_delete(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可删除平台")
            return
        platform_id = int(body.get("id") or 0)
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT name FROM platforms WHERE id = %s", (platform_id,))
                row = cur.fetchone()
                if row is None:
                    self.send_json({"code": 50000, "message": "平台不存在"})
                    return
                # 仅当没有订单使用该平台时才允许删除，避免历史订单的平台名失效
                cur.execute(
                    "SELECT COUNT(*) AS total FROM account_records"
                    " WHERE platform = %s AND is_delete = 0",
                    (row["name"],),
                )
                if cur.fetchone()["total"] > 0:
                    self.send_json({"code": 50000, "message": "该平台已有订单使用，无法删除，可改为停用名称或在订单里调整"})
                    return
                cur.execute("DELETE FROM platforms WHERE id = %s", (platform_id,))
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    # ---------------- 业务项配置 ----------------
    # 订单里的「业务项」是多选组合（A+B），字典里只维护原子项与默认单价。

    def biz_item_usage(self, cur):
        """统计每个业务项被多少条执照明细用到：按 + 拆开再数，避免「解非」误命中「税务非正常解除」。"""
        cur.execute(
        "SELECT items FROM account_items"
        " WHERE COALESCE(items, '') <> '' AND is_delete = 0"
    )
        usage = {}
        for row in cur.fetchall():
            text = row["items"] if isinstance(row, dict) else row[0]
            for name in split_biz_items(text):
                usage[name] = usage.get(name, 0) + 1
        return usage

    def bizitem_list(self, query=None):
        keyword = (query or {}).get("keyword", "").strip()
        where_sql = ""
        params = []
        if keyword:
            where_sql = " WHERE name ILIKE %s OR remark ILIKE %s"
            like = "%" + keyword + "%"
            params = [like, like]
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM biz_items" + where_sql + " ORDER BY sort ASC, id ASC",
                    params,
                )
                rows = cur.fetchall()
                usage = self.biz_item_usage(cur)
        items = [{
            "id": row["id"],
            "name": row["name"],
            "unit_price": float(row["unit_price"] or 0),
            "remark": row["remark"] or "",
            "sort": int(row["sort"] or 0),
            "active": bool(row["active"]),
            "used_count": int(usage.get(row["name"], 0)),
        } for row in rows]
        self.send_json({"code": 20000, "data": items})

    def bizitem_create(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可新增业务项")
            return
        name = (body.get("name") or "").strip()
        if not name:
            self.send_json({"code": 50000, "message": "业务项名称不能为空"})
            return
        if ITEM_SPLIT_RE.search(name):
            self.send_json({"code": 50000, "message": "业务项是单个项目，不要带 + / 、等分隔符"})
            return
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM biz_items WHERE name = %s", (name,))
                if cur.fetchone():
                    self.send_json({"code": 50000, "message": "该业务项已存在"})
                    return
                cur.execute(
                    """
                    INSERT INTO biz_items (name, unit_price, remark, sort, active)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        name, float(body.get("unit_price") or 0), body.get("remark") or "",
                        int(body.get("sort") or 0), bool(body.get("active", True)),
                    ),
                )
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    def bizitem_update(self, body, user):
        item_id = int(body.get("id") or 0)
        name = (body.get("name") or "").strip()
        # 只改启用状态时（列表里的开关）其余字段不动
        only_toggle = bool(body.get("only_toggle"))
        if not self.is_admin(user):
            self.deny("仅管理员可修改业务项")
            return
        if not item_id:
            self.send_json({"code": 50000, "message": "业务项信息不完整"})
            return
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM biz_items WHERE id = %s", (item_id,))
                current = cur.fetchone()
                if current is None:
                    self.send_json({"code": 50000, "message": "业务项不存在"})
                    return
                if only_toggle:
                    cur.execute(
                        "UPDATE biz_items SET active = %s WHERE id = %s",
                        (bool(body.get("active", True)), item_id),
                    )
                    conn.commit()
                    self.send_json({"code": 20000, "data": {"status": "success"}})
                    return
                if not name:
                    self.send_json({"code": 50000, "message": "业务项名称不能为空"})
                    return
                if ITEM_SPLIT_RE.search(name):
                    self.send_json({"code": 50000, "message": "业务项是单个项目，不要带 + / 、等分隔符"})
                    return
                cur.execute("SELECT 1 FROM biz_items WHERE name = %s AND id <> %s", (name, item_id))
                if cur.fetchone():
                    self.send_json({"code": 50000, "message": "该业务项已存在"})
                    return
                cur.execute(
                    """
                    UPDATE biz_items SET name = %s, unit_price = %s, remark = %s, sort = %s, active = %s
                     WHERE id = %s
                    """,
                    (
                        name, float(body.get("unit_price") or 0), body.get("remark") or "",
                        int(body.get("sort") or 0), bool(body.get("active", True)), item_id,
                    ),
                )
                old_name = current["name"]
                if old_name != name:
                    # 改名时同步历史明细与订单级业务项，否则老订单里会留下改名前的老名字
                    cur.execute(
                        "SELECT id, items FROM account_items WHERE COALESCE(items, '') LIKE %s",
                        ("%" + old_name + "%",),
                    )
                    for row in cur.fetchall():
                        parts = [name if part == old_name else part for part in split_biz_items(row["items"])]
                        cur.execute(
                            "UPDATE account_items SET items = %s WHERE id = %s",
                            ("+".join(parts), row["id"]),
                        )
                    cur.execute(
                        "SELECT id, items FROM account_records WHERE COALESCE(items, '') LIKE %s",
                        ("%" + old_name + "%",),
                    )
                    for row in cur.fetchall():
                        parts = [name if part == old_name else part for part in split_biz_items(row["items"])]
                        cur.execute(
                            "UPDATE account_records SET items = %s WHERE id = %s",
                            ("+".join(parts), row["id"]),
                        )
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    def bizitem_delete(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可删除业务项")
            return
        item_id = int(body.get("id") or 0)
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT name FROM biz_items WHERE id = %s", (item_id,))
                row = cur.fetchone()
                if row is None:
                    self.send_json({"code": 50000, "message": "业务项不存在"})
                    return
                usage = self.biz_item_usage(cur)
                if usage.get(row["name"], 0) > 0:
                    self.send_json({
                        "code": 50000,
                        "message": f"已有 {usage[row['name']]} 条执照任务用到该业务项，不能删除，可改为「停用」",
                    })
                    return
                cur.execute("DELETE FROM biz_items WHERE id = %s", (item_id,))
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    # ---------------- 价格配置 ----------------

    def price_rows(self, cur, keyword="", category="", only_active=False):
        where = []
        params = []
        if keyword:
            like = "%" + keyword + "%"
            where.append("(name ILIKE %s OR condition ILIKE %s OR category ILIKE %s OR remark ILIKE %s)")
            params.extend([like] * 4)
        if category:
            where.append("category = %s")
            params.append(category)
        if only_active:
            where.append("active = TRUE")
        sql = "SELECT * FROM price_items"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY sort ASC, id ASC"
        cur.execute(sql, params)
        return cur.fetchall()

    def price_out(self, row):
        price = float(row["price"] or 0)
        peer = float(row["peer_price"] or 0)
        return {
            "id": row["id"],
            "category": row["category"] or "",
            "name": row["name"],
            "condition": row["condition"] or "",
            "price": price,
            "peer_price": peer,
            # 与同行价对比：负数是比同行便宜，正数是比同行贵，供查看页直观标色
            "diff": round(price - peer, 2),
            "remark": row["remark"] or "",
            "sort": int(row["sort"] or 0),
            "active": bool(row["active"]),
            "updated_at": int(row["updated_at"].timestamp() * 1000) if row["updated_at"] else 0,
        }

    def price_categories(self, cur):
        """类别顺序按预置顺序排，后加的自定义类别排在后面。"""
        cur.execute("SELECT DISTINCT category FROM price_items WHERE COALESCE(category, '') <> ''")
        present = [row["category"] for row in cur.fetchall()]
        ordered = [name for name in PRICE_CATEGORY_ORDER if name in present]
        ordered.extend(sorted(name for name in present if name not in PRICE_CATEGORY_ORDER))
        return ordered

    def price_list(self, query=None):
        query = query or {}
        keyword = (query.get("keyword") or "").strip()
        category = (query.get("category") or "").strip()
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                rows = self.price_rows(cur, keyword, category)
                categories = self.price_categories(cur)
                cur.execute("SELECT key, value FROM price_settings")
                settings = {row["key"]: row["value"] or "" for row in cur.fetchall()}
                # 全量口径的统计，不受搜索条件影响，避免数字随筛选跳动
                cur.execute(
                    """
                    SELECT COUNT(*) AS total,
                           COUNT(*) FILTER (WHERE active) AS active_total,
                           COALESCE(AVG(price), 0) AS avg_price,
                           COALESCE(MIN(price), 0) AS min_price,
                           COALESCE(MAX(price), 0) AS max_price,
                           COUNT(*) FILTER (WHERE price < peer_price AND peer_price > 0) AS cheaper_total
                      FROM price_items
                    """
                )
                stat = cur.fetchone()
        items = [self.price_out(row) for row in rows]
        stats = {
            "total": int(stat["total"] or 0),
            "active_total": int(stat["active_total"] or 0),
            "avg_price": round(float(stat["avg_price"] or 0), 2),
            "min_price": float(stat["min_price"] or 0),
            "max_price": float(stat["max_price"] or 0),
            "cheaper_total": int(stat["cheaper_total"] or 0),
        }
        self.send_json({
            "code": 20000,
            "data": {
                "items": items,
                "categories": categories,
                "settings": {
                    "notice": settings.get("notice", ""),
                    "tips": settings.get("tips", ""),
                },
                "stats": stats,
            },
        })

    def price_payload(self, body):
        """校验并整理前端提交的价目字段，返回 (payload, 错误信息)。"""
        name = (body.get("name") or "").strip()
        category = (body.get("category") or "").strip()
        if not name:
            return None, "服务项目名称不能为空"
        if not category:
            return None, "类别不能为空"
        try:
            price = float(body.get("price") or 0)
            peer_price = float(body.get("peer_price") or 0)
        except (TypeError, ValueError):
            return None, "价格必须是数字"
        if price < 0 or peer_price < 0:
            return None, "价格不能为负数"
        return {
            "name": name,
            "category": category,
            "condition": (body.get("condition") or "").strip(),
            "price": price,
            "peer_price": peer_price,
            "remark": (body.get("remark") or "").strip(),
            "sort": int(body.get("sort") or 0),
            "active": bool(body.get("active", True)),
        }, ""

    def price_create(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可维护价格")
            return
        payload, message = self.price_payload(body)
        if payload is None:
            self.send_json({"code": 50000, "message": message})
            return
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM price_items WHERE name = %s", (payload["name"],))
                if cur.fetchone():
                    self.send_json({"code": 50000, "message": "该服务项目已存在，直接改价即可"})
                    return
                sort = payload["sort"]
                if not sort:
                    # 新项目默认排在同类最后，保持用户手工排序的空间
                    cur.execute(
                        "SELECT COALESCE(MAX(sort), 0) FROM price_items WHERE category = %s",
                        (payload["category"],),
                    )
                    sort = int(cur.fetchone()[0] or 0) + 10
                cur.execute(
                    """
                    INSERT INTO price_items
                           (category, name, condition, price, peer_price, remark, sort, active, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                    """,
                    (
                        payload["category"], payload["name"], payload["condition"],
                        payload["price"], payload["peer_price"], payload["remark"],
                        sort, payload["active"],
                    ),
                )
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    def price_update(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可维护价格")
            return
        item_id = int(body.get("id") or 0)
        if not item_id:
            self.send_json({"code": 50000, "message": "缺少价格记录 id"})
            return
        # 列表里的启用开关只改状态，其余字段不动
        only_toggle = bool(body.get("only_toggle"))
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM price_items WHERE id = %s", (item_id,))
                current = cur.fetchone()
                if current is None:
                    self.send_json({"code": 50000, "message": "价格记录不存在"})
                    return
                if only_toggle:
                    cur.execute(
                        "UPDATE price_items SET active = %s, updated_at = now() WHERE id = %s",
                        (bool(body.get("active", True)), item_id),
                    )
                    conn.commit()
                    self.send_json({"code": 20000, "data": {"status": "success"}})
                    return
                payload, message = self.price_payload(body)
                if payload is None:
                    self.send_json({"code": 50000, "message": message})
                    return
                cur.execute(
                    "SELECT 1 FROM price_items WHERE name = %s AND id <> %s",
                    (payload["name"], item_id),
                )
                if cur.fetchone():
                    self.send_json({"code": 50000, "message": "已有同名服务项目"})
                    return
                cur.execute(
                    """
                    UPDATE price_items
                       SET category = %s, name = %s, condition = %s, price = %s,
                           peer_price = %s, remark = %s, sort = %s, active = %s,
                           updated_at = now()
                     WHERE id = %s
                    """,
                    (
                        payload["category"], payload["name"], payload["condition"],
                        payload["price"], payload["peer_price"], payload["remark"],
                        payload["sort"] or int(current["sort"] or 0), payload["active"], item_id,
                    ),
                )
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    def price_delete(self, body, user):
        if not self.is_admin(user):
            self.deny("仅管理员可删除价格")
            return
        item_id = int(body.get("id") or 0)
        if not item_id:
            self.send_json({"code": 50000, "message": "缺少价格记录 id"})
            return
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM price_items WHERE id = %s", (item_id,))
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    def price_save_settings(self, body, user):
        """保存价目表的免责声明与特别提醒（价格查看页顶部/底部展示）。"""
        if not self.is_admin(user):
            self.deny("仅管理员可修改价格说明")
            return
        with connect() as conn:
            with conn.cursor() as cur:
                for key in ("notice", "tips"):
                    if key not in body:
                        continue
                    cur.execute(
                        """
                        INSERT INTO price_settings (key, value, updated_at)
                        VALUES (%s, %s, now())
                        ON CONFLICT (key) DO UPDATE
                           SET value = EXCLUDED.value, updated_at = now()
                        """,
                        (key, str(body.get(key) or "")),
                    )
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    def role_create(self, body, user=None):
        if user is not None and not self.is_admin(user):
            self.deny("仅管理员可新增角色")
            return
        key = (body.get("key") or "").strip() or ("role" + secrets.token_hex(3))
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM roles WHERE key = %s", (key,))
                if cur.fetchone():
                    self.send_json({"code": 50000, "message": "Role already exists"})
                    return
                cur.execute(
                    "INSERT INTO roles (key, name, description, routes) VALUES (%s, %s, %s, %s)",
                    (key, body.get("name") or key, body.get("description") or "", Json(body.get("routes") or [])),
                )
            conn.commit()
        self.send_json({"code": 20000, "data": {"key": key}})

    def role_update(self, key, body, user=None):
        if user is not None and not self.is_admin(user):
            self.deny("仅管理员可修改角色")
            return
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE roles SET name = %s, description = %s, routes = %s WHERE key = %s",
                    (body.get("name") or key, body.get("description") or "", Json(body.get("routes") or []), key),
                )
                if cur.rowcount == 0:
                    self.send_json({"code": 50000, "message": "Role not found"})
                    return
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    def role_delete(self, key, user=None):
        if user is not None and not self.is_admin(user):
            self.deny("仅管理员可删除角色")
            return
        if key == "admin":
            self.send_json({"code": 50000, "message": "内置管理员角色不能删除"})
            return
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM roles WHERE key = %s", (key,))
            conn.commit()
        self.send_json({"code": 20000, "data": {"status": "success"}})

    def search_user(self, query):
        name = (query.get("name") or "").strip()
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if name:
                    cur.execute("SELECT name FROM contacts WHERE name ILIKE %s ORDER BY name LIMIT 50", ("%" + name + "%",))
                else:
                    cur.execute("SELECT name FROM contacts ORDER BY name LIMIT 50")
                items = [{"name": row["name"]} for row in cur.fetchall()]
        self.send_json({"code": 20000, "data": {"items": items}})

    def transactions(self):
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT order_no, timestamp, username, price, status FROM transactions ORDER BY id DESC")
                items = []
                for row in cur.fetchall():
                    items.append({
                        "order_no": row["order_no"],
                        "timestamp": int(row["timestamp"]),
                        "username": row["username"],
                        "price": float(row["price"]),
                        "status": row["status"],
                    })
        self.send_json({"code": 20000, "data": {"total": len(items), "items": items}})

    def upload(self, body):
        field = body.get("_file")
        if field is None:
            self.send_json({"code": 50000, "message": "file missing"})
            return
        filename = field.filename or "file"
        ext = Path(filename).suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf", ".txt", ".zip", ".xlsx", ".csv"):
            ext = ".bin"
        name = secrets.token_hex(16) + ext
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target = UPLOAD_DIR / name
        data = field.file.read()
        if len(data) > MAX_UPLOAD:
            self.send_json({"code": 50000, "message": "file too large"})
            return
        target.write_bytes(data)
        os.chmod(target, 0o644)
        url = "/uploads/" + name
        self.send_json({"code": 20000, "data": {"url": url, "qiniu_url": url, "qiniu_key": name, "qiniu_token": "local"}})

    def serve_upload(self, path):
        name = os.path.basename(path)
        target = UPLOAD_DIR / name
        if not target.is_file():
            self.send_error(404)
            return
        data = target.read_bytes()
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".csv": "text/csv",
        }.get(target.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_UPLOAD + 1024 * 1024:
            raise ValueError("body too large")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        if "multipart/form-data" in ctype:
            file_field = parse_multipart_file(raw, ctype)
            return {"_file": file_field}
        if "application/json" in ctype or raw[:1] in (b"{", b"["):
            return json.loads(raw.decode("utf-8"))
        parsed = parse_qs(raw.decode("utf-8"))
        return {key: values[-1] for key, values in parsed.items()}

    def send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), App)
    print("vue-admin-api listening on %s:%s" % (HOST, PORT), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
