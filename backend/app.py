import hashlib
import io
import json
import os
import re
import secrets
import time
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
    "timestamp", "biz_date", "category", "client", "platform", "items", "unit_price", "quantity",
    "revenue", "cost", "profit", "status", "remark", "creator",
    "license_name", "credit_code", "legal_person", "legal_id",
]

COST_FIELDS = [
    "timestamp", "biz_date", "category", "payee", "amount", "method", "related_order",
    "remark", "creator",
]

# 订单进度可选的阶段，前端下拉与此保持一致
PROGRESS_STEPS = ["已录入", "已联系", "已报价", "已付款", "办理中", "已交付", "已完成"]

COST_CATEGORIES = ["采购", "物流", "人工", "房租", "水电", "推广", "差旅", "办公", "其他"]

PROGRESS_STATUS = ("pending", "doing", "done", "blocked")


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


def account_message(record):
    lines = ["【订单】"]
    head = " ".join(part for part in [record.get("biz_date"), record.get("category")] if part)
    if head:
        lines.append(head)
    subject = "".join(part for part in [record.get("client"), record.get("items")] if part)
    if subject:
        lines.append(subject)
    if record.get("license_name"):
        lines.append("执照：" + record["license_name"])
    if record.get("legal_person"):
        lines.append("法人：" + record["legal_person"])
    lines.append("单价：" + format_amount(record.get("unit_price")))
    quantity = record.get("quantity")
    if quantity is not None and float(quantity) != 1:
        lines.append("数量：" + format_amount(quantity))
        lines.append("金额：" + format_amount(record.get("revenue")))
    lines.append("成本：" + format_amount(record.get("cost")))
    lines.append("利润：" + format_amount(record.get("profit")))
    if record.get("remark"):
        lines.append("备注：" + record["remark"])
    return "\n".join(lines)


def account_out(row):
    record = {
        "id": row["id"],
        "timestamp": int(row["timestamp"] or 0),
        "biz_date": row["biz_date"] or "",
        "category": row["category"] or "",
        "client": row["client"] or "",
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
        "license_name": row.get("license_name") or "",
        "credit_code": row.get("credit_code") or "",
        "legal_person": row.get("legal_person") or "",
        "legal_id": row.get("legal_id") or "",
    }
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
        "step": row["step"] or "",
        "status": row["status"] or "doing",
        "note": row["note"] or "",
        "operator": row["operator"] or "",
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
    }


def insert_progress(cur, account_id, step, status, note, operator, stamp=None):
    """写入一条订单进度记录。订单创建/状态变更时自动调用。"""
    if status not in PROGRESS_STATUS:
        status = "doing"
    cur.execute(
        """
        INSERT INTO order_progress (account_id, step, status, note, operator, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (account_id, step, status, note or "", operator or "", stamp or now_ms()),
    )


def auto_progress(cur, record, operator):
    """根据订单内容生成一条「已录入」初始进度。"""
    subject = "".join(part for part in [record.get("client"), record.get("items")] if part)
    amount = format_amount(record.get("revenue"))
    note = "订单已录入：" + (subject or "未命名订单") + "，金额 " + amount
    insert_progress(cur, record["id"], "已录入", "done", note, operator, record.get("timestamp"))


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
        CREATE INDEX IF NOT EXISTS order_progress_account_idx
        ON order_progress (account_id, timestamp DESC)
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
    ]
    with connect() as conn:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
            cur.execute("SELECT COUNT(*) FROM users")
            if cur.fetchone()[0] == 0:
                seed(cur)
            sync_account_route(cur)
            seed_menus(cur)
            seed_platforms(cur)
        conn.commit()


# 系统内置页面 → 默认菜单项。菜单可在「菜单管理」里改名/改图标/排序/隐藏/删除，
# 但页面本体由前端路由提供，菜单只是这些页面的入口配置。
MENU_SEED = [
    ("/account/index", "订单管理", "money", "", 10),
    ("/account/query", "订单查询", "table", "", 20),
    ("/progress/index", "订单进度", "tree", "", 30),
    ("/cost/index", "支出管理", "money", "", 40),
    ("/cost/query", "成本查询", "table", "", 50),
    ("/system/user", "用户管理", "user", "/system", 110),
    ("/system/role", "角色管理", "lock", "/system", 120),
    ("/system/menu", "菜单管理", "list", "/system", 130),
    ("/system/platform", "平台管理", "shopping", "/system", 140),
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


def seed_menus(cur):
    # 先把旧路径改名（如平台管理并入系统管理），再补插新增菜单
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
            self.send_json({"code": 50000, "message": "Server error"})

    def dispatch(self, method, path, query, body, user):
        if path == "/vue-element-admin/user/login" and method == "POST":
            self.login(body)
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
        elif path == "/vue-element-admin/account/progress/list" and method == "GET":
            self.progress_list(query)
        elif path == "/vue-element-admin/account/progress/overview" and method == "GET":
            self.progress_overview(query)
        elif path == "/vue-element-admin/account/progress/summary" and method == "GET":
            self.progress_summary()
        elif path == "/vue-element-admin/account/progress/create" and method == "POST":
            self.progress_create(body, user)
        elif path == "/vue-element-admin/account/progress/delete" and method == "POST":
            self.progress_delete(body)
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
        self.send_json({"code": 20000, "data": {"token": token}})

    def user_info(self, user):
        self.send_json({
            "code": 20000,
            "data": {
                "id": user["id"],
                "username": user["username"],
                "roles": list(user["roles"]),
                "introduction": user["introduction"] or "",
                "avatar": user["avatar"] or "",
                "name": user["name"],
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
        where = []
        params = []
        if query.get("keyword"):
            keyword = "%" + query["keyword"] + "%"
            where.append(
                "(client ILIKE %s OR items ILIKE %s OR category ILIKE %s OR remark ILIKE %s"
                " OR license_name ILIKE %s OR credit_code ILIKE %s OR legal_person ILIKE %s)"
            )
            params.extend([keyword] * 7)
        if query.get("status"):
            where.append("status = %s")
            params.append(query["status"])
        if query.get("category"):
            where.append("category = %s")
            params.append(query["category"])
        if query.get("platform"):
            where.append("platform = %s")
            params.append(query["platform"])
        if query.get("month"):
            # biz_date 存 "MM/dd"（历史上有 "YYYY-MM-dd"），两种写法都按月份前缀匹配
            month = str(query["month"]).split("-")[-1].strip()
            where.append("(biz_date LIKE %s OR biz_date LIKE %s)")
            params.extend([month + "/%", "%-" + month + "-%"])
        sql = "SELECT * FROM account_records"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC"
        page = max(int(query.get("page") or 1), 1)
        limit = min(max(int(query.get("limit") or 20), 1), 200)
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT COUNT(*) AS total FROM account_records" + (" WHERE " + " AND ".join(where) if where else ""),
                    params,
                )
                total = cur.fetchone()["total"]
                cur.execute(sql + " LIMIT %s OFFSET %s", params + [limit, (page - 1) * limit])
                items = [account_out(row) for row in cur.fetchall()]
        self.send_json({"code": 20000, "data": {"total": total, "items": items}})

    def account_detail(self, query):
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM account_records WHERE id = %s", (int(query.get("id") or 0),))
                row = cur.fetchone()
        if row is None:
            self.send_json({"code": 50000, "message": "Record not found"})
            return
        self.send_json({"code": 20000, "data": account_out(row)})

    def account_summary(self, query=None):
        where_sql = ""
        params = []
        if query and query.get("month"):
            month = str(query["month"]).split("-")[-1].strip()
            where_sql = " WHERE (biz_date LIKE %s OR biz_date LIKE %s)"
            params = [month + "/%", "%-" + month + "-%"]
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS count,
                           COALESCE(SUM(revenue), 0) AS revenue,
                           COALESCE(SUM(cost), 0) AS cost,
                           COALESCE(SUM(COALESCE(profit, 0)), 0) AS profit,
                           COUNT(*) FILTER (WHERE profit IS NULL) AS pending
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
            },
        })

    def account_values(self, body, user, existing=None):
        def pick(key, default=""):
            if key in body:
                return body.get(key)
            if existing is not None:
                return existing.get(key)
            return default

        stamp = parse_ms(body.get("timestamp") if "timestamp" in body else (existing["timestamp"] if existing else None))
        unit_price = to_number(pick("unit_price"), None)
        quantity = to_number(pick("quantity", 1), 1)
        revenue = to_number(pick("revenue"), None)
        if "revenue" not in body and ("unit_price" in body or "quantity" in body):
            revenue = None
        if revenue is None and unit_price is not None:
            revenue = unit_price * quantity
        cost = to_number(pick("cost"), None)
        profit = to_number(body.get("profit"), None) if "profit" in body else None
        if profit is None and revenue is not None and cost is not None:
            profit = revenue - cost
        biz_date = pick("biz_date")
        if not biz_date:
            # 服务器在 UTC，业务日期按北京时间算，避免凌晨录入落到前一天/前一月
            moment = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc) + timedelta(hours=8)
            biz_date = moment.strftime("%m/%d")
        status = pick("status", "pending") or "pending"
        if status not in ("pending", "doing", "done"):
            status = "pending"
        # 完成时间：状态为已完成时记录（首次完成取当前时间，之后保持不变），
        # 状态改回待定/进行中则清空，等再次完成时重新记录
        if status == "done":
            prior = existing.get("completed_at") if existing is not None else None
            completed_at = int(prior) if prior else now_ms()
        else:
            completed_at = None
        return {
            "timestamp": stamp,
            "biz_date": biz_date,
            "category": pick("category"),
            "client": pick("client"),
            "platform": pick("platform"),
            "items": pick("items"),
            "unit_price": unit_price,
            "quantity": quantity,
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
            "status": status,
            "completed_at": completed_at,
            "remark": pick("remark"),
            "creator": pick("creator") or (user["username"] if user else ""),
            "license_name": (pick("license_name") or "").strip(),
            "credit_code": (pick("credit_code") or "").strip().upper(),
            "legal_person": (pick("legal_person") or "").strip(),
            "legal_id": (pick("legal_id") or "").strip().upper(),
        }

    def account_create(self, body, user):
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
                operator = user["username"] if user else ""
                # 订单录入的同时自动建一条初始进度，保证每个订单都有进度可跟
                auto_progress(cur, account_out(row), operator)
                # 录入时就标记已完成的，补一条完成记录，保证完成时间在进度里可查
                if (row["status"] or "") == "done":
                    insert_progress(
                        cur, row["id"], "已完成", "done",
                        "订单已完成，完成时间 " + format_completed(row["completed_at"]), operator,
                    )
            conn.commit()
        self.send_json({"code": 20000, "data": account_out(row)})

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
                assignments = []
                params = []
                for column in ACCOUNT_FIELDS:
                    if column not in body and column not in ("timestamp", "revenue", "profit"):
                        continue
                    assignments.append(column + " = %s")
                    params.append(values[column])
                if "status" in body:
                    assignments.append("completed_at = %s")
                    params.append(values["completed_at"])
                if not assignments:
                    self.send_json({"code": 20000, "data": account_out(existing)})
                    return
                params.append(record_id)
                cur.execute(
                    "UPDATE account_records SET " + ", ".join(assignments) + " WHERE id = %s RETURNING *",
                    params,
                )
                row = cur.fetchone()
                new_status = values["status"]
                if "status" in body and new_status != (existing["status"] or "pending"):
                    label = {"pending": "待定", "doing": "进行中", "done": "已完成"}.get(new_status, new_status)
                    if new_status == "done":
                        note = "订单已完成，完成时间 " + format_completed(values["completed_at"])
                    else:
                        note = "订单状态更新为「%s」" % label
                    insert_progress(
                        cur, record_id, "已完成" if new_status == "done" else "状态变更",
                        "done" if new_status == "done" else "doing",
                        note, user["username"] if user else "",
                    )
            conn.commit()
        self.send_json({"code": 20000, "data": account_out(row)})

    def account_delete(self, body):
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM account_records WHERE id = %s", (int(body.get("id") or 0),))
            conn.commit()
        self.send_json({"code": 20000, "data": "success"})

    # ---------------- 订单进度 ----------------

    def progress_list(self, query):
        account_id = int(query.get("account_id") or 0)
        if not account_id:
            self.send_json({"code": 50000, "message": "缺少订单 id"})
            return
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM order_progress WHERE account_id = %s ORDER BY timestamp ASC, id ASC",
                    (account_id,),
                )
                items = [progress_out(row) for row in cur.fetchall()]
        self.send_json({"code": 20000, "data": {"items": items, "steps": PROGRESS_STEPS}})

    def progress_overview(self, query):
        where = []
        params = []
        keyword = (query.get("keyword") or "").strip()
        if keyword:
            where.append("(a.client ILIKE %s OR a.items ILIKE %s OR a.remark ILIKE %s)")
            params.extend(["%" + keyword + "%"] * 3)
        if query.get("status"):
            where.append("a.status = %s")
            params.append(query["status"])
        condition = (" WHERE " + " AND ".join(where)) if where else ""
        page = max(int(query.get("page") or 1), 1)
        limit = min(max(int(query.get("limit") or 20), 1), 200)
        sql = """
            SELECT a.*,
                   p.step AS last_step,
                   p.status AS last_status,
                   p.note AS last_note,
                   p.operator AS last_operator,
                   p.timestamp AS last_timestamp,
                   COALESCE(c.cnt, 0) AS progress_count
              FROM account_records a
              LEFT JOIN LATERAL (
                   SELECT * FROM order_progress
                    WHERE account_id = a.id
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 1
              ) p ON TRUE
              LEFT JOIN (
                   SELECT account_id, COUNT(*) AS cnt FROM order_progress GROUP BY account_id
              ) c ON c.account_id = a.id
        """
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) AS total FROM account_records a" + condition, params)
                total = cur.fetchone()["total"]
                cur.execute(sql + condition + " ORDER BY a.id DESC LIMIT %s OFFSET %s", params + [limit, (page - 1) * limit])
                items = []
                for row in cur.fetchall():
                    record = account_out(row)
                    record.update({
                        "last_step": row["last_step"] or "",
                        "last_status": row["last_status"] or "",
                        "last_note": row["last_note"] or "",
                        "last_operator": row["last_operator"] or "",
                        "last_timestamp": int(row["last_timestamp"] or 0),
                        "progress_count": int(row["progress_count"] or 0),
                    })
                    items.append(record)
        self.send_json({"code": 20000, "data": {"total": total, "items": items, "steps": PROGRESS_STEPS}})

    def progress_summary(self):
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT step, COUNT(*) AS cnt FROM (
                        SELECT DISTINCT ON (account_id) account_id, step
                          FROM order_progress
                         ORDER BY account_id, timestamp DESC, id DESC
                    ) latest GROUP BY step ORDER BY cnt DESC, step
                """)
                by_step = [{"step": row["step"], "count": int(row["cnt"])} for row in cur.fetchall()]
                cur.execute("SELECT COUNT(DISTINCT account_id) AS cnt FROM order_progress")
                covered = int(cur.fetchone()["cnt"] or 0)
                cur.execute("SELECT COUNT(*) AS cnt FROM account_records")
                orders = int(cur.fetchone()["cnt"] or 0)
                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM account_records a
                     WHERE NOT EXISTS (SELECT 1 FROM order_progress p WHERE p.account_id = a.id)
                """)
                missing = int(cur.fetchone()["cnt"] or 0)
        self.send_json({
            "code": 20000,
            "data": {"by_step": by_step, "covered": covered, "orders": orders, "missing": missing},
        })

    def progress_create(self, body, user):
        account_id = int(body.get("account_id") or 0)
        step = (body.get("step") or "").strip()
        if not account_id or not step:
            self.send_json({"code": 50000, "message": "订单与进度阶段不能为空"})
            return
        status = body.get("status") or "doing"
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, status FROM account_records WHERE id = %s", (account_id,))
                if cur.fetchone() is None:
                    self.send_json({"code": 50000, "message": "订单不存在"})
                    return
                insert_progress(cur, account_id, step, status, body.get("note"), user["username"] if user else "")
                # 进度推进到「已完成」时同步订单状态
                if step == "已完成":
                    cur.execute("UPDATE account_records SET status = 'done' WHERE id = %s", (account_id,))
                elif status == "doing":
                    cur.execute("UPDATE account_records SET status = 'doing' WHERE id = %s AND status = 'pending'", (account_id,))
                cur.execute("SELECT * FROM order_progress WHERE account_id = %s ORDER BY id DESC LIMIT 1", (account_id,))
                row = cur.fetchone()
            conn.commit()
        self.send_json({"code": 20000, "data": progress_out(row)})

    def progress_delete(self, body):
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM order_progress WHERE id = %s", (int(body.get("id") or 0),))
            conn.commit()
        self.send_json({"code": 20000, "data": "success"})

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
        where = []
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
                cur.execute("SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS amount FROM cost_records")
                overall = cur.fetchone()
                if month:
                    cur.execute(
                        "SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS amount"
                        " FROM cost_records WHERE LEFT(biz_date, 7) = %s",
                        (month,),
                    )
                    month_row = cur.fetchone()
                else:
                    month_row = {"cnt": 0, "amount": 0}
                cur.execute("""
                    SELECT COALESCE(NULLIF(category, ''), '未分类') AS category,
                           COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS amount
                      FROM cost_records GROUP BY 1 ORDER BY amount DESC
                """)
                by_category = [
                    {"category": row["category"], "count": int(row["cnt"]), "amount": float(row["amount"] or 0)}
                    for row in cur.fetchall()
                ]
                cur.execute("""
                    SELECT COALESCE(NULLIF(biz_date, ''), '未填日期') AS biz_date,
                           COALESCE(SUM(amount), 0) AS amount
                      FROM cost_records GROUP BY 1 ORDER BY 1 DESC LIMIT 6
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
                cur.execute("SELECT * FROM account_records ORDER BY id DESC")
                accounts = cur.fetchall()
                cur.execute("SELECT * FROM cost_records")
                costs = cur.fetchall()
                cur.execute(
                    """
                    SELECT DISTINCT ON (account_id) account_id, step, status, note, timestamp
                      FROM order_progress
                     ORDER BY account_id, timestamp DESC, id DESC
                    """
                )
                latest = {row["account_id"]: row for row in cur.fetchall()}
                cur.execute("SELECT account_id, COUNT(*) AS cnt FROM order_progress GROUP BY account_id")
                counts = {row["account_id"]: int(row["cnt"] or 0) for row in cur.fetchall()}

        months = [shift_month(now, offset).strftime("%Y-%m") for offset in range(-5, 1)]
        trend = {key: {"revenue": 0.0, "cost": 0.0, "profit": 0.0, "orders": 0} for key in months}

        revenue_total = 0.0
        order_cost_total = 0.0
        by_category = {}
        by_status = {"pending": 0, "doing": 0, "done": 0}
        by_client = {}

        for row in accounts:
            revenue = float(row["revenue"] or 0)
            cost = float(row["cost"] or 0)
            revenue_total += revenue
            order_cost_total += cost
            month = biz_month_key(row["biz_date"], row.get("created_at"))
            if month in trend:
                trend[month]["revenue"] += revenue
                trend[month]["cost"] += cost
                trend[month]["orders"] += 1
            category = (row["category"] or "").strip() or "未分类"
            bucket = by_category.setdefault(
                category, {"name": category, "revenue": 0.0, "cost": 0.0, "profit": 0.0, "count": 0}
            )
            bucket["revenue"] += revenue
            bucket["cost"] += cost
            bucket["profit"] += revenue - cost
            bucket["count"] += 1
            status = row["status"] or "pending"
            by_status[status] = by_status.get(status, 0) + 1
            client = (row["client"] or "").strip() or "散客"
            client_bucket = by_client.setdefault(
                client, {"client": client, "revenue": 0.0, "profit": 0.0, "orders": 0}
            )
            client_bucket["revenue"] += revenue
            client_bucket["profit"] += revenue - cost
            client_bucket["orders"] += 1

        extra_cost_total = 0.0
        cost_by_category = {}
        for row in costs:
            amount = float(row["amount"] or 0)
            extra_cost_total += amount
            month = biz_month_key(row["biz_date"], row.get("created_at"))
            if month in trend:
                trend[month]["cost"] += amount
            category = (row["category"] or "").strip() or "未分类"
            bucket = cost_by_category.setdefault(category, {"name": category, "amount": 0.0, "count": 0})
            bucket["amount"] += amount
            bucket["count"] += 1

        for key in months:
            trend[key]["profit"] = trend[key]["revenue"] - trend[key]["cost"]

        total_cost = order_cost_total + extra_cost_total
        profit_total = revenue_total - total_cost
        orders = len(accounts)
        current, previous = months[-1], months[-2]
        month_revenue = trend[current]["revenue"]
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
                    "revenue": money(revenue_total),
                    "order_cost": money(order_cost_total),
                    "extra_cost": money(extra_cost_total),
                    "total_cost": money(total_cost),
                    "profit": money(profit_total),
                    "margin": round(profit_total / revenue_total * 100, 1) if revenue_total else 0,
                    "orders": orders,
                    "avg_ticket": money(revenue_total / orders) if orders else 0,
                    "month_revenue": money(month_revenue),
                    "month_cost": money(trend[current]["cost"]),
                    "month_profit": money(trend[current]["profit"]),
                    "month_growth": growth,
                    "open_orders": len(todos),
                    "risk_orders": len([item for item in todos if item["level"] == "danger"]),
                    "pending_orders": by_status.get("pending", 0),
                },
                "trend": {
                    "months": months,
                    "revenue": [money(trend[key]["revenue"]) for key in months],
                    "cost": [money(trend[key]["cost"]) for key in months],
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
                cur.execute("SELECT * FROM cost_records WHERE id = %s", (record_id,))
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
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM cost_records WHERE id = %s", (int(body.get("id") or 0),))
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
        items = [{
            "id": row["id"],
            "path": row["path"],
            "title": row["title"],
            "icon": row["icon"] or "",
            "parent": row["parent"] or "",
            "sort": int(row["sort"] or 0),
            "visible": bool(row["visible"]),
        } for row in rows]
        self.send_json({"code": 20000, "data": items})

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
                           (SELECT COUNT(*) FROM account_records a WHERE a.platform = p.name) AS order_count
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
                cur.execute("SELECT COUNT(*) AS total FROM account_records WHERE platform = %s", (row["name"],))
                if cur.fetchone()["total"] > 0:
                    self.send_json({"code": 50000, "message": "该平台已有订单使用，无法删除，可改为停用名称或在订单里调整"})
                    return
                cur.execute("DELETE FROM platforms WHERE id = %s", (platform_id,))
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
