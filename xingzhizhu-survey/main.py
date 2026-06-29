from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from typing import Dict, Any
import csv
import io
import json
import os
import re
import requests
from urllib.parse import parse_qs
import zipfile
from html import escape

app = FastAPI(title="幸之住需求洞察系统")

app.mount("/static", StaticFiles(directory="static"), name="static")

FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")
BASE_URL = os.getenv("BASE_URL", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
DB_PATH = "survey.db"
ADMIN_COOKIE = "jiabao_admin"


def _pg_conn():
    from urllib.parse import urlparse
    from pg8000.native import Connection
    parsed = urlparse(DATABASE_URL)
    return Connection(
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path[1:] if parsed.path else "",
    )


def init_db():
    if DATABASE_URL:
        conn = _pg_conn()
        conn.run(
            """
            CREATE TABLE IF NOT EXISTS surveys (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                basic TEXT,
                kitchen TEXT,
                bathroom TEXT,
                sleep TEXT,
                living TEXT,
                entryway TEXT,
                kids TEXT,
                study TEXT,
                balcony TEXT,
                laundry TEXT,
                storage TEXT,
                learning TEXT,
                fitness TEXT,
                entertainment TEXT,
                environment TEXT,
                special TEXT,
                report TEXT,
                name TEXT,
                phone TEXT
            )
            """
        )
        for col in ["living", "entryway", "kids", "study", "balcony", "laundry", "storage", "learning", "fitness", "entertainment", "environment", "special", "name", "phone"]:
            try:
                conn.run(f'ALTER TABLE surveys ADD COLUMN IF NOT EXISTS {col} TEXT')
            except Exception:
                pass
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                basic TEXT,
                kitchen TEXT,
                bathroom TEXT,
                sleep TEXT,
                living TEXT,
                entryway TEXT,
                kids TEXT,
                study TEXT,
                balcony TEXT,
                laundry TEXT,
                storage TEXT,
                learning TEXT,
                fitness TEXT,
                entertainment TEXT,
                environment TEXT,
                special TEXT,
                report TEXT,
                name TEXT,
                phone TEXT
            )
            """
        )
        for col in ["living", "entryway", "kids", "study", "balcony", "laundry", "storage", "learning", "fitness", "entertainment", "environment", "special", "name", "phone"]:
            try:
                c.execute(f'ALTER TABLE surveys ADD COLUMN {col} TEXT')
            except Exception:
                pass
        conn.commit()
        conn.close()


init_db()


def _admin_authorized(request: Request) -> bool:
    if not ADMIN_PASSWORD:
        return True
    cookie_value = request.cookies.get(ADMIN_COOKIE, "")
    header_value = request.headers.get("x-admin-password", "")
    return cookie_value == ADMIN_PASSWORD or header_value == ADMIN_PASSWORD


def _admin_unauthorized_response():
    return JSONResponse({"code": 401, "message": "需要后台密码"}, status_code=401)


def _safe_json(value):
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _as_list(value):
    if isinstance(value, list):
        return value
    if value:
        return [value]
    return []


def _join_values(value):
    return "、".join([str(item) for item in _as_list(value) if item]) or "-"


def _summary_house_type(value):
    text = str(value or "").strip()
    if not text or text == "-":
        return "-"
    if "精装" in text:
        return "精装房"
    if "毛坯" in text:
        return "毛坯"
    if any(keyword in text for keyword in ["二手", "旧房", "旧改", "局部", "翻新", "改造"]):
        return "旧改"
    return text


def _summary_from_payload(row_id, created_at, name, phone, basic, report):
    basic = _safe_json(basic)
    report = _safe_json(report)
    scenes = report.get("scenes", {}) if isinstance(report.get("scenes", {}), dict) else {}
    core_scenes = _as_list(scenes.get("core"))
    minor_scenes = _as_list(scenes.get("minor"))
    focus_scenes = core_scenes or minor_scenes

    return {
        "id": row_id,
        "created_at": str(created_at),
        "name": basic.get("wechat_name") or name or basic.get("name", "-"),
        "phone": phone or basic.get("phone", "-"),
        "house_type": _summary_house_type(basic.get("type")),
        "area": basic.get("area", "-"),
        "people": basic.get("people", "-"),
        "population_structure": _join_values(basic.get("structure")),
        "budget": basic.get("budget", "-"),
        "lifestyle_focus": _join_values(focus_scenes),
        "core_scenes": _join_values(core_scenes),
        "minor_scenes": _join_values(minor_scenes),
    }


SUMMARY_COLUMNS = [
    ("id", "客户ID"),
    ("created_at", "提交时间"),
    ("name", "微信/姓名"),
    ("phone", "手机号"),
    ("house_type", "房屋类型"),
    ("area", "房屋面积"),
    ("people", "常住人口"),
    ("population_structure", "人口结构"),
    ("budget", "预算"),
    ("lifestyle_focus", "生活方式重点"),
    ("core_scenes", "核心场景"),
    ("minor_scenes", "次要场景"),
]


def _all_survey_summaries():
    query = """
        SELECT id, created_at, name, phone, basic, report
        FROM surveys
        ORDER BY id DESC
    """
    if DATABASE_URL:
        conn = _pg_conn()
        rows = conn.run(query)
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(query)
        rows = c.fetchall()
        conn.close()

    return [
        _summary_from_payload(row[0], row[1], row[2], row[3], row[4], row[5])
        for row in rows
    ]


def _admin_status_payload():
    if DATABASE_URL:
        conn = _pg_conn()
        total_rows = conn.run("SELECT COUNT(*) FROM surveys")
        unique_rows = conn.run("SELECT COUNT(DISTINCT phone) FROM surveys WHERE phone IS NOT NULL AND phone != ''")
        latest_rows = conn.run(
            """
            SELECT id, created_at, name, phone, basic
            FROM surveys
            ORDER BY id DESC
            LIMIT 1
            """
        )
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM surveys")
        total_rows = c.fetchall()
        c.execute("SELECT COUNT(DISTINCT phone) FROM surveys WHERE phone IS NOT NULL AND phone != ''")
        unique_rows = c.fetchall()
        c.execute(
            """
            SELECT id, created_at, name, phone, basic
            FROM surveys
            ORDER BY id DESC
            LIMIT 1
            """
        )
        latest_rows = c.fetchall()
        conn.close()

    latest = None
    if latest_rows:
        row = latest_rows[0]
        basic = _safe_json(row[4])
        latest = {
            "id": row[0],
            "created_at": str(row[1]),
            "name": basic.get("wechat_name") or row[2] or basic.get("name", "-"),
            "phone": row[3] or basic.get("phone", "-"),
        }

    return {
        "total_submissions": total_rows[0][0] if total_rows else 0,
        "unique_customers": unique_rows[0][0] if unique_rows else 0,
        "latest": latest,
        "database": "PostgreSQL" if DATABASE_URL else "SQLite",
        "feishu": "已配置" if FEISHU_WEBHOOK else "未配置",
        "admin_auth": "已开启" if ADMIN_PASSWORD else "未开启",
    }


def _xlsx_col_name(index):
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_cell(cell_ref, value, style=None):
    style_attr = f' s="{style}"' if style else ""
    text = escape(str(value if value is not None else ""))
    return f'<c r="{cell_ref}" t="inlineStr"{style_attr}><is><t>{text}</t></is></c>'


def _build_summary_xlsx(summaries):
    rows = []
    header_cells = [
        _xlsx_cell(f"{_xlsx_col_name(col_index)}1", title, "1")
        for col_index, (_, title) in enumerate(SUMMARY_COLUMNS, start=1)
    ]
    rows.append(f'<row r="1">{"".join(header_cells)}</row>')

    for row_index, summary in enumerate(summaries, start=2):
        cells = []
        for col_index, (key, _) in enumerate(SUMMARY_COLUMNS, start=1):
            cells.append(_xlsx_cell(f"{_xlsx_col_name(col_index)}{row_index}", summary.get(key, "")))
        rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    col_defs = "".join(
        f'<col min="{idx}" max="{idx}" width="{width}" customWidth="1"/>'
        for idx, width in enumerate([10, 20, 18, 16, 14, 14, 12, 24, 14, 30, 30, 30], start=1)
    )
    dimension = f"A1:{_xlsx_col_name(len(SUMMARY_COLUMNS))}{max(len(summaries) + 1, 1)}"
    sheet_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="{dimension}"/>
  <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft" activeCell="A2" sqref="A2"/></sheetView></sheetViews>
  <cols>{col_defs}</cols>
  <sheetData>{"".join(rows)}</sheetData>
  <autoFilter ref="{dimension}"/>
</worksheet>'''
    workbook_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="客户摘要" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''
    styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><name val="Arial"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>'''
    rels_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''
    workbook_rels_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''
    content_types_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/styles.xml", styles_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return output.getvalue()


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/jiabao-ai", response_class=HTMLResponse)
async def jiabao_ai():
    with open("static/jiabao-ai.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "database": "postgres" if DATABASE_URL else "sqlite",
        "feishu": "configured" if FEISHU_WEBHOOK else "missing",
        "admin_auth": "enabled" if ADMIN_PASSWORD else "disabled",
    }


@app.post("/api/submit")
async def submit_survey(request: Request):
    data = await request.json()

    for field in ["basic", "report"]:
        if field not in data:
            return JSONResponse(
                {"code": 400, "message": f"缺少字段: {field}"}, status_code=400
            )

    basic_data = data.get("basic", {})
    wechat_name = basic_data.get("wechat_name", "").strip()
    name = basic_data.get("name", "").strip()
    phone = basic_data.get("phone", "").strip()

    if not wechat_name:
        return JSONResponse({"code": 400, "message": "请填写微信昵称"}, status_code=400)
    if phone and not re.match(r'^\d{11}$', phone):
        return JSONResponse({"code": 400, "message": "请填写正确的11位手机号"}, status_code=400)

    def _d(field):
        return json.dumps(data.get(field, {}), ensure_ascii=False)

    basic_json = _d("basic")
    kitchen_json = _d("kitchen")
    bathroom_json = _d("bathroom")
    sleep_json = _d("sleep")
    laundry_json = _d("laundry")
    storage_json = _d("storage")
    learning_json = _d("learning")
    fitness_json = _d("fitness")
    entertainment_json = _d("entertainment")
    environment_json = _d("environment")
    special_json = _d("special")
    report_json = _d("report")

    if DATABASE_URL:
        conn = _pg_conn()
        existing = conn.run("SELECT id FROM surveys WHERE phone = :phone", phone=phone) if phone else []
        if existing:
            survey_id = existing[0][0]
            conn.run(
                """
                UPDATE surveys SET
                    basic = :basic, kitchen = :kitchen, bathroom = :bathroom,
                    sleep = :sleep, laundry = :laundry, storage = :storage,
                    learning = :learning, fitness = :fitness, entertainment = :entertainment,
                    environment = :environment, special = :special, report = :report,
                    name = :name, phone = :phone, created_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """,
                id=survey_id,
                basic=basic_json,
                kitchen=kitchen_json,
                bathroom=bathroom_json,
                sleep=sleep_json,
                laundry=laundry_json,
                storage=storage_json,
                learning=learning_json,
                fitness=fitness_json,
                entertainment=entertainment_json,
                environment=environment_json,
                special=special_json,
                report=report_json,
                name=name,
                phone=phone,
            )
        else:
            result = conn.run(
                """
                INSERT INTO surveys (basic, kitchen, bathroom, sleep, laundry, storage, learning, fitness, entertainment, environment, special, report, name, phone)
                VALUES (:basic, :kitchen, :bathroom, :sleep, :laundry, :storage, :learning, :fitness, :entertainment, :environment, :special, :report, :name, :phone)
                RETURNING id
                """,
                basic=basic_json,
                kitchen=kitchen_json,
                bathroom=bathroom_json,
                sleep=sleep_json,
                laundry=laundry_json,
                storage=storage_json,
                learning=learning_json,
                fitness=fitness_json,
                entertainment=entertainment_json,
                environment=environment_json,
                special=special_json,
                report=report_json,
                name=name,
                phone=phone,
            )
            survey_id = result[0][0]
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if phone:
            c.execute("SELECT id FROM surveys WHERE phone = ?", (phone,))
            existing = c.fetchone()
        else:
            existing = None
        if existing:
            survey_id = existing[0]
            c.execute(
                """
                UPDATE surveys SET
                    basic = :basic, kitchen = :kitchen, bathroom = :bathroom,
                    sleep = :sleep, laundry = :laundry, storage = :storage,
                    learning = :learning, fitness = :fitness, entertainment = :entertainment,
                    environment = :environment, special = :special, report = :report,
                    name = :name, phone = :phone, created_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """,
                {
                    "id": survey_id,
                    "basic": basic_json,
                    "kitchen": kitchen_json,
                    "bathroom": bathroom_json,
                    "sleep": sleep_json,
                    "laundry": laundry_json,
                    "storage": storage_json,
                    "learning": learning_json,
                    "fitness": fitness_json,
                    "entertainment": entertainment_json,
                    "environment": environment_json,
                    "special": special_json,
                    "report": report_json,
                    "name": name,
                    "phone": phone,
                },
            )
        else:
            c.execute(
                """
                INSERT INTO surveys (basic, kitchen, bathroom, sleep, laundry, storage, learning, fitness, entertainment, environment, special, report, name, phone)
                VALUES (:basic, :kitchen, :bathroom, :sleep, :laundry, :storage, :learning, :fitness, :entertainment, :environment, :special, :report, :name, :phone)
                RETURNING id
                """,
                {
                    "basic": basic_json,
                    "kitchen": kitchen_json,
                    "bathroom": bathroom_json,
                    "sleep": sleep_json,
                    "laundry": laundry_json,
                    "storage": storage_json,
                    "learning": learning_json,
                    "fitness": fitness_json,
                    "entertainment": entertainment_json,
                    "environment": environment_json,
                    "special": special_json,
                    "report": report_json,
                    "name": name,
                    "phone": phone,
                },
            )
            survey_id = c.fetchone()[0]
        conn.commit()
        conn.close()

    feishu_status = "未配置"
    if FEISHU_WEBHOOK:
        try:
            send_feishu(survey_id, data["basic"], data["report"])
            feishu_status = "推送成功"
        except Exception as e:
            feishu_status = f"推送失败: {str(e)}"

    return {"code": 0, "id": survey_id, "message": "提交成功", "feishu_status": feishu_status}


@app.get("/api/surveys")
async def list_surveys(request: Request):
    if not _admin_authorized(request):
        return _admin_unauthorized_response()

    if DATABASE_URL:
        conn = _pg_conn()
        rows = conn.run(
            """
            SELECT DISTINCT ON (phone) id, to_char(created_at, 'YYYY-MM-DD HH24:MI:SS'), name, phone, basic, report
            FROM surveys WHERE phone IS NOT NULL AND phone != '' ORDER BY phone, id DESC
            """
        )
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            SELECT s.id, s.created_at, s.name, s.phone, s.basic, s.report
            FROM surveys s
            INNER JOIN (SELECT MAX(id) as max_id FROM surveys WHERE phone IS NOT NULL AND phone != '' GROUP BY phone) latest ON s.id = latest.max_id
            ORDER BY s.id DESC
            """
        )
        rows = c.fetchall()
        conn.close()

    result = []
    for row in rows:
        basic = json.loads(row[4] or "{}")
        report = json.loads(row[5] or "{}")
        scenes = report.get("scenes", {})
        completeness = f"{len(scenes.get('core', [])) + len(scenes.get('minor', []))}/9"
        result.append(
            {
                "id": row[0],
                "created_at": str(row[1]),
                "name": basic.get("wechat_name") or row[2] or basic.get("name", "-"),
                "phone": row[3] or basic.get("phone", "-"),
                "people": basic.get("people", "-"),
                "area": basic.get("area", "-"),
                "budget": basic.get("budget", "-"),
                "core_scenes": ", ".join(scenes.get("core", [])),
                "completeness": completeness,
            }
        )
    return result


@app.get("/api/admin/status")
async def admin_status(request: Request):
    if not _admin_authorized(request):
        return _admin_unauthorized_response()
    return _admin_status_payload()


@app.get("/api/surveys/export.csv")
async def export_surveys_csv(request: Request):
    if not _admin_authorized(request):
        return _admin_unauthorized_response()

    columns = [
        "id",
        "created_at",
        "name",
        "phone",
        "basic",
        "kitchen",
        "bathroom",
        "sleep",
        "living",
        "entryway",
        "kids",
        "study",
        "balcony",
        "laundry",
        "storage",
        "learning",
        "fitness",
        "entertainment",
        "environment",
        "special",
        "report",
    ]
    query = """
        SELECT id, created_at, name, phone, basic, kitchen, bathroom, sleep,
               living, entryway, kids, study, balcony, laundry, storage,
               learning, fitness, entertainment, environment, special, report
        FROM surveys
        ORDER BY id DESC
    """

    if DATABASE_URL:
        conn = _pg_conn()
        rows = conn.run(query)
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(query)
        rows = c.fetchall()
        conn.close()

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([str(value) if value is not None else "" for value in row])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jiabao-surveys.csv"},
    )


@app.get("/api/surveys/summary.xlsx")
async def export_survey_summary_xlsx(request: Request):
    if not _admin_authorized(request):
        return _admin_unauthorized_response()

    summaries = _all_survey_summaries()
    xlsx_bytes = _build_summary_xlsx(summaries)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=jiabao-survey-summary.xlsx"},
    )


@app.get("/api/surveys/{survey_id}")
async def get_survey(survey_id: int):
    if DATABASE_URL:
        conn = _pg_conn()
        rows = conn.run(
            "SELECT id, created_at, basic, kitchen, bathroom, sleep, living, entryway, kids, study, balcony, laundry, storage, learning, fitness, entertainment, environment, special, report FROM surveys WHERE id = :id",
            id=survey_id
        )
        conn.close()
        if not rows:
            return JSONResponse(
                {"code": 404, "message": "未找到"}, status_code=404
            )
        row = rows[0]
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, created_at, basic, kitchen, bathroom, sleep, living, entryway, kids, study, balcony, laundry, storage, learning, fitness, entertainment, environment, special, report FROM surveys WHERE id = ?", (survey_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return JSONResponse(
                {"code": 404, "message": "未找到"}, status_code=404
            )

    return {
        "id": row[0],
        "created_at": str(row[1]),
        "basic": json.loads(row[2] or "{}"),
        "kitchen": json.loads(row[3] or "{}"),
        "bathroom": json.loads(row[4] or "{}"),
        "sleep": json.loads(row[5] or "{}"),
        "living": json.loads(row[6] or "{}"),
        "entryway": json.loads(row[7] or "{}"),
        "kids": json.loads(row[8] or "{}"),
        "study": json.loads(row[9] or "{}"),
        "balcony": json.loads(row[10] or "{}"),
        "laundry": json.loads(row[11] or "{}"),
        "storage": json.loads(row[12] or "{}"),
        "learning": json.loads(row[13] or "{}"),
        "fitness": json.loads(row[14] or "{}"),
        "entertainment": json.loads(row[15] or "{}"),
        "environment": json.loads(row[16] or "{}"),
        "special": json.loads(row[17] or "{}"),
        "report": json.loads(row[18] or "{}"),
    }


@app.get("/api/survey_by_phone")
async def get_survey_by_phone(phone: str):
    if not phone or not re.match(r'^\d{11}$', phone):
        return JSONResponse({"code": 400, "message": "手机号格式错误"}, status_code=400)

    if DATABASE_URL:
        conn = _pg_conn()
        rows = conn.run(
            "SELECT id, created_at, basic, kitchen, bathroom, sleep, living, entryway, kids, study, balcony, laundry, storage, learning, fitness, entertainment, environment, special, report FROM surveys WHERE phone = :phone ORDER BY id DESC LIMIT 1",
            phone=phone
        )
        conn.close()
        if not rows:
            return JSONResponse({"code": 404, "message": "未找到"}, status_code=404)
        row = rows[0]
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, created_at, basic, kitchen, bathroom, sleep, living, entryway, kids, study, balcony, laundry, storage, learning, fitness, entertainment, environment, special, report FROM surveys WHERE phone = ? ORDER BY id DESC LIMIT 1", (phone,))
        row = c.fetchone()
        conn.close()
        if not row:
            return JSONResponse({"code": 404, "message": "未找到"}, status_code=404)

    return {
        "id": row[0],
        "created_at": str(row[1]),
        "basic": json.loads(row[2] or "{}"),
        "kitchen": json.loads(row[3] or "{}"),
        "bathroom": json.loads(row[4] or "{}"),
        "sleep": json.loads(row[5] or "{}"),
        "living": json.loads(row[6] or "{}"),
        "entryway": json.loads(row[7] or "{}"),
        "kids": json.loads(row[8] or "{}"),
        "study": json.loads(row[9] or "{}"),
        "balcony": json.loads(row[10] or "{}"),
        "laundry": json.loads(row[11] or "{}"),
        "storage": json.loads(row[12] or "{}"),
        "learning": json.loads(row[13] or "{}"),
        "fitness": json.loads(row[14] or "{}"),
        "entertainment": json.loads(row[15] or "{}"),
        "environment": json.loads(row[16] or "{}"),
        "special": json.loads(row[17] or "{}"),
        "report": json.loads(row[18] or "{}"),
    }


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    if not _admin_authorized(request):
        return """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>幸之住 · 后台登录</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f5f5f7; min-height: 100vh; display: grid; place-items: center; padding: 20px; }
                form { width: min(360px, 100%); background: #fff; padding: 28px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
                h1 { font-size: 22px; margin-bottom: 18px; }
                input { width: 100%; padding: 12px 14px; border: 1px solid #d2d2d7; border-radius: 8px; font-size: 16px; margin-bottom: 14px; }
                button { width: 100%; padding: 12px 14px; border: 0; border-radius: 8px; background: #0071e3; color: #fff; font-size: 15px; font-weight: 700; cursor: pointer; }
                p { margin-top: 12px; color: #86868b; font-size: 13px; line-height: 1.5; }
            </style>
        </head>
        <body>
            <form method="post" action="/admin/login">
                <h1>后台登录</h1>
                <input type="password" name="password" placeholder="后台密码" autocomplete="current-password" autofocus>
                <button type="submit">进入后台</button>
                <p>密码由环境变量 ADMIN_PASSWORD 控制。</p>
            </form>
        </body>
        </html>
        """

    return """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>幸之住 · 问卷管理后台</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f5f5f7; padding: 40px 20px; }
            .container { max-width: 960px; margin: 0 auto; }
            h1 { font-size: 28px; margin-bottom: 24px; }
            .toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 24px; }
            .toolbar h1 { margin-bottom: 0; }
            .actions { display: flex; gap: 8px; align-items: center; }
            .btn { display: inline-block; padding: 10px 14px; border-radius: 8px; background: #0071e3; color: #fff; font-size: 14px; font-weight: 600; }
            .btn.green { background: #248a3d; }
            .btn.secondary { background: #f5f5f7; color: #1d1d1f; }
            .status-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 24px; }
            .status-card { background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); min-height: 92px; }
            .status-label { color: #6e6e73; font-size: 13px; margin-bottom: 8px; }
            .status-value { color: #1d1d1f; font-size: 22px; font-weight: 700; line-height: 1.2; }
            .status-note { color: #86868b; font-size: 12px; margin-top: 8px; line-height: 1.4; word-break: break-all; }
            table { width: 100%; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
            th, td { padding: 14px 16px; text-align: left; border-bottom: 1px solid #f0f0f0; }
            th { background: #fafafa; font-weight: 600; font-size: 14px; color: #666; }
            td { font-size: 14px; }
            tr:hover { background: #fafafa; }
            a { color: #0071e3; text-decoration: none; }
            .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; background: #ffe5e5; color: #d32f2f; }
            @media (max-width: 640px) {
                body { padding: 20px 12px; }
                .toolbar { align-items: flex-start; flex-direction: column; }
                .actions { flex-wrap: wrap; }
                .status-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                table { font-size: 12px; }
                th, td { padding: 10px 8px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="toolbar">
                <h1>客户档案列表</h1>
                <div class="actions">
                    <a class="btn green" href="/api/surveys/summary.xlsx">导出摘要Excel</a>
                    <a class="btn" href="/api/surveys/export.csv">导出CSV</a>
                    <a class="btn secondary" href="/admin/logout">退出</a>
                </div>
            </div>
            <div class="status-grid" id="status-grid">
                <div class="status-card">
                    <div class="status-label">总提交数</div>
                    <div class="status-value">-</div>
                    <div class="status-note">全部问卷提交记录</div>
                </div>
                <div class="status-card">
                    <div class="status-label">去重客户数</div>
                    <div class="status-value">-</div>
                    <div class="status-note">按手机号去重</div>
                </div>
                <div class="status-card">
                    <div class="status-label">最近提交</div>
                    <div class="status-value">-</div>
                    <div class="status-note">暂无记录</div>
                </div>
                <div class="status-card">
                    <div class="status-label">系统状态</div>
                    <div class="status-value">-</div>
                    <div class="status-note">数据库 / 飞书 / 后台保护</div>
                </div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>更新时间</th>
                        <th>微信/姓名</th>
                        <th>手机号</th>
                        <th>人口</th>
                        <th>面积</th>
                        <th>预算</th>
                        <th>核心场景</th>
                        <th>完整度</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody id="list"></tbody>
            </table>
        </div>
        <script>
            function escapeHtml(value) {
                return String(value ?? '').replace(/[&<>"']/g, ch => ({
                    '&': '&amp;',
                    '<': '&lt;',
                    '>': '&gt;',
                    '"': '&quot;',
                    "'": '&#39;'
                }[ch]));
            }

            function renderStatus(status) {
                const latest = status.latest;
                const latestNote = latest
                    ? `${escapeHtml(latest.created_at)} · ${escapeHtml(latest.name)} · ${escapeHtml(latest.phone)}`
                    : '暂无记录';
                document.getElementById('status-grid').innerHTML = `
                    <div class="status-card">
                        <div class="status-label">总提交数</div>
                        <div class="status-value">${escapeHtml(status.total_submissions ?? 0)}</div>
                        <div class="status-note">全部问卷提交记录</div>
                    </div>
                    <div class="status-card">
                        <div class="status-label">去重客户数</div>
                        <div class="status-value">${escapeHtml(status.unique_customers ?? 0)}</div>
                        <div class="status-note">按手机号去重</div>
                    </div>
                    <div class="status-card">
                        <div class="status-label">最近提交</div>
                        <div class="status-value">${latest ? '#' + escapeHtml(latest.id) : '-'}</div>
                        <div class="status-note">${latestNote}</div>
                    </div>
                    <div class="status-card">
                        <div class="status-label">系统状态</div>
                        <div class="status-value">${escapeHtml(status.database || '-')}</div>
                        <div class="status-note">飞书：${escapeHtml(status.feishu || '-')}；后台：${escapeHtml(status.admin_auth || '-')}</div>
                    </div>
                `;
            }

            fetch('/api/admin/status')
                .then(r => r.json())
                .then(renderStatus)
                .catch(() => {});

            fetch('/api/surveys')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('list');
                    tbody.innerHTML = data.map(item => `
                        <tr>
                            <td>#${item.id}</td>
                            <td>${item.created_at}</td>
                            <td>${item.name}</td>
                            <td>${item.phone}</td>
                            <td>${item.people}人</td>
                            <td>${item.area}</td>
                            <td>${item.budget}</td>
                            <td>${item.core_scenes ? '<span class="tag">' + item.core_scenes + '</span>' : '-'}</td>
                            <td>${item.completeness}</td>
                            <td><a href="/report/${item.id}" target="_blank">查看档案</a></td>
                        </tr>
                    `).join('');
                });
        </script>
    </body>
    </html>
    """


@app.post("/admin/login")
async def admin_login(request: Request):
    body = (await request.body()).decode("utf-8")
    password = parse_qs(body).get("password", [""])[0]
    if not ADMIN_PASSWORD or password != ADMIN_PASSWORD:
        return HTMLResponse(
            """
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>登录失败</title></head>
            <body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:40px;">
                <p>后台密码错误。</p>
                <p><a href="/admin">返回登录</a></p>
            </body>
            </html>
            """,
            status_code=401,
        )
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(
        ADMIN_COOKIE,
        password,
        httponly=True,
        samesite="lax",
        secure=BASE_URL.startswith("https://"),
    )
    return response


@app.get("/admin/logout")
async def admin_logout():
    response = RedirectResponse("/admin", status_code=303)
    response.delete_cookie(ADMIN_COOKIE)
    return response


@app.get("/report/{survey_id}", response_class=HTMLResponse)
async def report_page(survey_id: int):
    html = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>需求画像报告 #%s</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f5f5f7; padding: 40px 20px; }
            .container { max-width: 720px; margin: 0 auto; }
            .report { background: #fff; border-radius: 16px; padding: 40px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
            .report-header { text-align: center; margin-bottom: 40px; padding-bottom: 30px; border-bottom: 2px solid #f5f5f7; }
            .report-header h2 { font-size: 28px; margin-bottom: 8px; }
            .report-section { margin-bottom: 32px; }
            .report-section h3 { font-size: 18px; font-weight: 700; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
            .report-section h3::before { content: ""; display: inline-block; width: 4px; height: 20px; background: #0071e3; border-radius: 2px; }
            .report-table { width: 100%; border-collapse: collapse; }
            .report-table td { padding: 12px 0; border-bottom: 1px solid #f5f5f7; }
            .report-table td:first-child { width: 30%; color: #86868b; font-weight: 500; }
            .tag { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; margin-right: 6px; margin-bottom: 6px; }
            .tag-red { background: #ffe5e5; color: #d32f2f; }
            .tag-yellow { background: #fff8e1; color: #f9a825; }
            .tag-gray { background: #f5f5f5; color: #757575; }
            .tag-blue { background: #e3f2fd; color: #1976d2; }
            .pain-item { background: #fff8f0; border-left: 3px solid #ff9800; padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 10px; }
            .pain-scene { font-weight: 700; font-size: 14px; color: #e65100; margin-bottom: 4px; }
            .pain-text { font-size: 15px; color: #424242; }
            .btn { display: inline-block; padding: 12px 24px; background: #0071e3; color: #fff; border: none; border-radius: 10px; font-size: 14px; cursor: pointer; margin-top: 20px; }
            @media print { body { background: #fff; } .container { padding: 0; } .btn { display: none; } }
            @media (max-width: 640px) { .container { padding: 0; } .report { padding: 24px; } }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="report" id="reportContent"></div>
            <div style="text-align: center; margin-top: 24px;">
                <button class="btn" onclick="window.print()">打印/保存PDF</button>
                <button class="btn" style="background: #34c759; margin-left: 12px;" onclick="window.location.href='/admin'">返回列表</button>
            </div>
        </div>
        <script>
            const container = document.getElementById('reportContent');
            container.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#86868b;">加载中...</div>';

            fetch('/api/surveys/%s')
                .then(res => {
                    if (!res.ok) throw new Error('请求失败: ' + res.status);
                    return res.json();
                })
                .then(d => {
                    if (!d || d.code === 404) {
                        container.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#d32f2f;">未找到该报告</div>';
                        return;
                    }
                    const r = d.report || {};
                    const b = d.basic || {};
                    const persona = r.persona || null;

                    const safeArray = (v) => Array.isArray(v) ? v : [];
                    const safeJoin = (v, sep) => safeArray(v).join(sep) || '无';

                    const scenes = r.scenes || {};
                    const focusScenes = safeArray(scenes.core).length ? safeArray(scenes.core) : safeArray(scenes.minor);
                    const pains = safeArray(r.pains);
                    const params = safeArray(r.params);
                    const constraints = safeArray(r.constraints);
                    const seeds = safeArray(r.seeds);

                    const personaHtml = persona ? `
                        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 16px; padding: 32px; color: #fff; text-align: center; margin-bottom: 32px;">
                            <div style="font-size: 12px; opacity: 0.8; margin-bottom: 8px; letter-spacing: 2px;">SBTI 居住人格</div>
                            <div style="font-size: 36px; font-weight: 800; letter-spacing: 4px; margin-bottom: 4px;">${persona.code || ''}</div>
                            <div style="font-size: 22px; font-weight: 700; margin-bottom: 12px;">${persona.name || ''}</div>
                            <div style="font-size: 14px; opacity: 0.95; line-height: 1.6; max-width: 400px; margin: 0 auto;">${persona.desc || ''}</div>
                            <div style="margin-top: 12px;">${safeArray(persona.tags).map(t => `<span style="display:inline-block;background:rgba(255,255,255,0.2);padding:4px 12px;border-radius:12px;font-size:12px;margin:4px;">${t}</span>`).join('')}</div>
                        </div>
                    ` : '';

                    container.innerHTML = `
                        <div class="report-header">
                            <h2>需求画像报告</h2>
                            <p style="color:#86868b; margin-top:8px;">编号 #${d.id || %s} · ${d.created_at || '-'}</p>
                        </div>
                        ${personaHtml}
                        <div class="report-section">
                            <h3>客户摘要</h3>
                            <table class="report-table">
                                <tr><td>房屋类型</td><td>${b.type || '-'}</td></tr>
                                <tr><td>房屋面积</td><td>${b.area || '-'}</td></tr>
                                <tr><td>常住人口</td><td>${b.people || '-'} 人</td></tr>
                                <tr><td>人口结构</td><td>${safeJoin(b.structure, '、')}</td></tr>
                                <tr><td>预算区间</td><td>${b.budget || '-'}</td></tr>
                                <tr><td>生活方式重点</td><td>${safeJoin(focusScenes, '、')}</td></tr>
                                <tr><td>优先结构</td><td>核心：${safeJoin(scenes.core, '、')}；次要：${safeJoin(scenes.minor, '、')}；暂无：${safeJoin(scenes.none, '、')}</td></tr>
                            </table>
                        </div>
                        <div class="report-section">
                            <h3>基础锚点</h3>
                            <table class="report-table">
                                <tr><td>微信昵称</td><td>${b.wechat_name || '-'}</td></tr>
                                <tr><td>客户姓名</td><td>${b.name || '-'}</td></tr>
                                <tr><td>手机号</td><td>${b.phone || '-'}</td></tr>
                                <tr><td>常住人口</td><td>${b.people || '-'} 人</td></tr>
                                <tr><td>人口结构</td><td>${safeJoin(b.structure, '、')}</td></tr>
                                <tr><td>房屋面积</td><td>${b.area || '-'}</td></tr>
                                <tr><td>装修类型</td><td>${b.type || '-'}</td></tr>
                                <tr><td>预算区间</td><td>${b.budget || '-'}</td></tr>
                            </table>
                        </div>
                        <div class="report-section">
                            <h3>场景分级</h3>
                            <div style="margin-bottom:12px;">
                                <span class="tag tag-red">核心场景</span>
                                <span>${safeJoin(scenes.core, '、')}</span>
                            </div>
                            <div style="margin-bottom:12px;">
                                <span class="tag tag-yellow">次要场景</span>
                                <span>${safeJoin(scenes.minor, '、')}</span>
                            </div>
                            <div>
                                <span class="tag tag-gray">暂无需求</span>
                                <span>${safeJoin(scenes.none, '、')}</span>
                            </div>
                        </div>
                        <div class="report-section">
                            <h3>痛点清单</h3>
                            ${pains.length ? pains.map(p => `
                                <div class="pain-item">
                                    <div class="pain-scene">${p.scene || ''}</div>
                                    <div class="pain-text">${p.text || ''}</div>
                                </div>
                            `).join('') : '<p style="color:#86868b;">暂无明确痛点</p>'}
                        </div>
                        <div class="report-section">
                            <h3>设计参数</h3>
                            <table class="report-table">
                                ${params.length ? params.map(p => `
                                    <tr><td>${p.scene || ''}</td><td>${p.item || ''} <span class="tag ${p.level==='必须有'?'tag-red':p.level==='最好有'?'tag-yellow':'tag-gray'}">${p.level || ''}</span></td></tr>
                                `).join('') : '<tr><td colspan="2" style="color:#86868b;">暂无</td></tr>'}
                            </table>
                        </div>
                        <div class="report-section">
                            <h3>特殊约束</h3>
                            ${constraints.length ? constraints.map(c => `
                                <div style="margin-bottom:10px; padding:12px; background:#fff3f3; border-radius:8px; border-left:3px solid #d32f2f;">
                                    <strong>${c.type || ''}</strong>：${c.desc || ''}
                                </div>
                            `).join('') : '<p style="color:#86868b;">暂无</p>'}
                        </div>
                        <div class="report-section">
                            <h3>种草待确认</h3>
                            ${seeds.length ? seeds.map(s => `
                                <div style="margin-bottom:10px; padding:12px; background:#f0f7ff; border-radius:8px; border-left:3px solid #1976d2;">
                                    <strong>${s.item || ''}</strong>：${s.reason || ''}
                                </div>
                            `).join('') : '<p style="color:#86868b;">暂无</p>'}
                        </div>
                    `;
                })
                .catch(err => {
                    console.error(err);
                    container.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#d32f2f;">加载报告失败，请刷新重试<br><span style="font-size:13px;color:#86868b;">' + (err.message || '网络错误') + '</span></div>';
                });
        </script>
    </body>
    </html>
    """
    return html.replace('%s', str(survey_id), 1).replace('%s', str(survey_id), 1).replace('%s', str(survey_id), 1)


# ========== 飞书推送 ==========
def send_feishu(survey_id: int, basic: Dict[str, Any], report: Dict[str, Any]):
    """推送结构化报告到飞书群/机器人"""
    if not FEISHU_WEBHOOK:
        return

    scenes = report.get("scenes", {})
    pains = report.get("pains", [])
    params = report.get("params", [])
    client_name = basic.get("wechat_name") or basic.get("name") or "未知客户"
    client_phone = basic.get("phone", "")

    # 构造痛点文本
    pain_text = (
        "\n".join([f"• {p['scene']}：{p['text']}" for p in pains[:5]])
        if pains
        else "暂无"
    )

    # 构造设计参数文本（只取"必须有"）
    must_params = [p for p in params if p.get("level") == "必须有"]
    param_text = (
        "\n".join([f"• {p['scene']}：{p['item']}" for p in must_params[:5]])
        if must_params
        else "暂无"
    )

    content = [
        [{"tag": "text", "text": f"客户：{client_name} {client_phone}\n"}],
        [
            {
                "tag": "text",
                "text": f"核心场景：{', '.join(scenes.get('core', [])) or '待补充'}\n",
            }
        ],
        [
            {
                "tag": "text",
                "text": f"次要场景：{', '.join(scenes.get('minor', [])) or '无'}\n",
            }
        ],
        [{"tag": "text", "text": "\n📍 痛点清单：\n" + pain_text + "\n"}],
        [{"tag": "text", "text": "\n🔧 必须有（设计参数）：\n" + param_text + "\n"}],
    ]

    if BASE_URL:
        content.append(
            [
                {
                    "tag": "a",
                    "text": "👉 查看完整报告",
                    "href": f"{BASE_URL}/report/{survey_id}",
                }
            ]
        )

    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": f"🎯 新客户需求画像 | {client_name} #{survey_id}",
                    "content": content,
                }
            }
        },
    }

    resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
    resp.raise_for_status()


# ========== 启动 ==========
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
