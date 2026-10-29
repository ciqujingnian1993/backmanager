import hashlib
import io
import json
import os
import secrets
import time
from datetime import datetime, timezone
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

ARTICLE_FIELDS = [
    "timestamp", "author", "reviewer", "title", "content_short", "content",
    "forecast", "importance", "type", "status", "display_time", "comment_disabled",
    "pageviews", "image_uri", "platforms", "source_uri", "remark",
]

ACCOUNT_FIELDS = [
    "timestamp", "biz_date", "category", "client", "items", "unit_price", "quantity",
    "revenue", "cost", "profit", "status", "remark", "creator",
]

COST_FIELDS = [
    "timestamp", "biz_date", "category", "payee", "amount", "method", "related_order",
    "remark", "creator",
]

# 订单进度可选的阶段，前端下拉与此保持一致
PROGRESS_STEPS = ["已录入", "已联系", "已报价", "已付款", "办理中", "已交付", "已完成"]

COST_CATEGORIES = ["采购", "物流", "人工", "房租", "水电", "推广", "差旅", "办公", "其他"]

PROGRESS_STATUS = ("pending", "doing", "done", "blocked")


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
        "remark": row["remark"] or "",
        "creator": row["creator"] or "",
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
    ]
    with connect() as conn:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
            cur.execute("SELECT COUNT(*) FROM users")
            if cur.fetchone()[0] == 0:
                seed(cur)
            sync_account_route(cur)
        conn.commit()


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
                    self.send_json({"code": 50008, "message": "Login failed, unable to get user details."})
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
            self.role_create(body)
        elif path.startswith("/vue-element-admin/role/") and method == "PUT":
            self.role_update(path.rsplit("/", 1)[-1], body)
        elif path.startswith("/vue-element-admin/role/") and method == "DELETE":
            self.role_delete(path.rsplit("/", 1)[-1])
        elif path == "/vue-element-admin/search/user" and method == "GET":
            self.search_user(query)
        elif path == "/vue-element-admin/transaction/list" and method == "GET":
            self.transactions()
        elif path == "/vue-element-admin/account/list" and method == "GET":
            self.account_list(query)
        elif path == "/vue-element-admin/account/detail" and method == "GET":
            self.account_detail(query)
        elif path == "/vue-element-admin/account/summary" and method == "GET":
            self.account_summary()
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
            where.append("(client ILIKE %s OR items ILIKE %s OR category ILIKE %s OR remark ILIKE %s)")
            params.extend([keyword] * 4)
        if query.get("status"):
            where.append("status = %s")
            params.append(query["status"])
        if query.get("category"):
            where.append("category = %s")
            params.append(query["category"])
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

    def account_summary(self):
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
                    """
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
            biz_date = datetime.fromtimestamp(stamp / 1000).strftime("%m/%d")
        status = pick("status", "pending") or "pending"
        if status not in ("pending", "doing", "done"):
            status = "pending"
        return {
            "timestamp": stamp,
            "biz_date": biz_date,
            "category": pick("category"),
            "client": pick("client"),
            "items": pick("items"),
            "unit_price": unit_price,
            "quantity": quantity,
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
            "status": status,
            "remark": pick("remark"),
            "creator": pick("creator") or (user["username"] if user else ""),
        }

    def account_create(self, body, user):
        values = self.account_values(body, user)
        columns = ACCOUNT_FIELDS
        params = [values[column] for column in columns]
        sql = (
            "INSERT INTO account_records (" + ", ".join(columns) + ") VALUES ("
            + ", ".join(["%s"] * len(columns)) + ") RETURNING *"
        )
        with connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                # 订单录入的同时自动建一条初始进度，保证每个订单都有进度可跟
                auto_progress(cur, account_out(row), user["username"] if user else "")
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
                    insert_progress(
                        cur, record_id, "状态变更", "done" if new_status == "done" else "doing",
                        "订单状态更新为「%s」" % label, user["username"] if user else "",
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
                cur.execute("SELECT key, name, description, routes FROM roles ORDER BY id")
                items = [dict(row) for row in cur.fetchall()]
        self.send_json({"code": 20000, "data": items})

    def role_create(self, body):
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

    def role_update(self, key, body):
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

    def role_delete(self, key):
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
