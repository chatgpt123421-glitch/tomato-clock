from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from typing import Dict, Any
import csv
import io
import json
import os
import re
import secrets
import requests
from urllib.parse import parse_qs
import zipfile
from html import escape

app = FastAPI(title="幸之住需求洞察系统")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/style-images", StaticFiles(directory="static/style-images"), name="style-images")

FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_SUMMARY_SPREADSHEET_TOKEN = os.getenv("FEISHU_SUMMARY_SPREADSHEET_TOKEN", "")
FEISHU_SUMMARY_SHEET_ID = os.getenv("FEISHU_SUMMARY_SHEET_ID", "")
FEISHU_SUMMARY_SYNC_ROWS = int(os.getenv("FEISHU_SUMMARY_SYNC_ROWS", "0"))
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
        conn.run(
            """
            CREATE TABLE IF NOT EXISTS family_projects (
                id SERIAL PRIMARY KEY,
                token TEXT UNIQUE NOT NULL,
                coordinator_token TEXT,
                coordinator_member_id INTEGER,
                home_name TEXT NOT NULL,
                home_profile TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.run("ALTER TABLE family_projects ADD COLUMN IF NOT EXISTS coordinator_token TEXT")
        conn.run("ALTER TABLE family_projects ADD COLUMN IF NOT EXISTS coordinator_member_id INTEGER")
        for row in conn.run(
            "SELECT id FROM family_projects WHERE coordinator_token IS NULL OR coordinator_token=''"
        ):
            conn.run(
                "UPDATE family_projects SET coordinator_token=:token WHERE id=:id",
                token=secrets.token_urlsafe(24),
                id=row[0],
            )
        conn.run(
            """
            CREATE TABLE IF NOT EXISTS family_members (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL,
                member_token TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT,
                age_group TEXT,
                answer_source TEXT,
                answers TEXT,
                report TEXT,
                status TEXT DEFAULT 'submitted',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.run(
            """
            UPDATE family_projects p
            SET coordinator_member_id=(
                SELECT MIN(m.id) FROM family_members m WHERE m.project_id=p.id
            )
            WHERE p.coordinator_member_id IS NULL
              AND EXISTS (SELECT 1 FROM family_members m WHERE m.project_id=p.id)
            """
        )
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
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS family_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                coordinator_token TEXT,
                coordinator_member_id INTEGER,
                home_name TEXT NOT NULL,
                home_profile TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        try:
            c.execute("ALTER TABLE family_projects ADD COLUMN coordinator_token TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE family_projects ADD COLUMN coordinator_member_id INTEGER")
        except Exception:
            pass
        for row in c.execute(
            "SELECT id FROM family_projects WHERE coordinator_token IS NULL OR coordinator_token=''"
        ).fetchall():
            c.execute(
                "UPDATE family_projects SET coordinator_token=? WHERE id=?",
                (secrets.token_urlsafe(24), row[0]),
            )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS family_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                member_token TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT,
                age_group TEXT,
                answer_source TEXT,
                answers TEXT,
                report TEXT,
                status TEXT DEFAULT 'submitted',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES family_projects(id)
            )
            """
        )
        c.execute(
            """
            UPDATE family_projects
            SET coordinator_member_id=(
                SELECT MIN(m.id) FROM family_members m WHERE m.project_id=family_projects.id
            )
            WHERE coordinator_member_id IS NULL
              AND EXISTS (SELECT 1 FROM family_members m WHERE m.project_id=family_projects.id)
            """
        )
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


def _summary_population(people, structure):
    people_text = str(people or "").strip()
    structure_values = _as_list(structure)
    structure_text = "、".join([str(item) for item in structure_values])
    combined = f"{people_text} {structure_text}"

    if "独居" in combined or people_text == "1":
        return "单身贵族"
    if people_text == "2":
        return "二人世界"
    if people_text == "3":
        return "三口之家"
    if people_text.startswith("4") or people_text.startswith("5") or "5+" in people_text:
        return "四世同堂"
    if any(keyword in structure_text for keyword in ["老人", "长辈"]) and any(keyword in structure_text for keyword in ["婴儿", "儿童", "青少年"]):
        return "四世同堂"
    if "夫妻" in structure_text:
        return "二人世界"
    return "-"


def _summary_budget(value):
    text = str(value or "").strip()
    if not text or text == "-":
        return "-"
    if "以上" in text and any(mark in text for mark in ["20", "30", "二十", "三十"]):
        return "20万以上"
    if "10万以下" in text or "10 万以下" in text or "八" in text or "8" in text:
        return "8万"
    if "10-15" in text or "10 - 15" in text or "10到15" in text:
        return "10万"
    if "15-20" in text or "15 - 20" in text or "15到20" in text:
        return "15万"
    if "20-30" in text or "20 - 30" in text or "20到30" in text:
        return "20万"
    if "12" in text or "十二" in text:
        return "12万"
    if "15" in text or "十五" in text:
        return "15万"
    if "20" in text or "二十" in text:
        return "20万"
    if "10" in text or "十" in text:
        return "10万"
    return text


def _summary_lifestyle_categories(basic, report, payloads=None):
    payloads = payloads or {}
    scenes = report.get("scenes", {}) if isinstance(report.get("scenes", {}), dict) else {}
    core_scenes = _as_list(scenes.get("core"))
    minor_scenes = _as_list(scenes.get("minor"))
    source_scenes = core_scenes or minor_scenes
    scene_text = "、".join([str(item) for item in source_scenes])
    all_scene_text = "、".join([str(item) for item in core_scenes + minor_scenes])

    structure_text = "、".join([str(item) for item in _as_list(basic.get("structure"))])
    tags_text = "、".join([str(item) for item in _as_list(basic.get("tags"))])
    kitchen_text = json.dumps(payloads.get("kitchen", {}), ensure_ascii=False)
    learning_text = json.dumps(payloads.get("learning", {}), ensure_ascii=False)
    fitness_text = json.dumps(payloads.get("fitness", {}), ensure_ascii=False)
    entertainment_text = json.dumps(payloads.get("entertainment", {}), ensure_ascii=False)
    environment_text = json.dumps(payloads.get("environment", {}), ensure_ascii=False)
    special_text = json.dumps(payloads.get("special", {}), ensure_ascii=False)
    combined = "、".join([scene_text, all_scene_text, structure_text, tags_text, kitchen_text, learning_text, fitness_text, entertainment_text, environment_text, special_text])

    has_child = any(keyword in structure_text or keyword in tags_text for keyword in ["婴儿", "儿童", "青少年", "孩子"])
    categories = []

    def add(category, condition):
        if condition and category not in categories:
            categories.append(category)

    add("亲子伴读", "学习成长" in combined and has_child)
    add("健身运动", "家庭健身" in combined or "健身" in fitness_text or "瑜伽" in fitness_text or "跑步" in fitness_text)
    add("宠物生活", "宠物" in combined or "猫" in special_text or "狗" in special_text)
    add("影音娱乐", "居家娱乐" in combined or "休闲娱乐" in combined or "电影" in entertainment_text or "游戏" in entertainment_text)
    add("艺术收藏", "二次元" in combined or "手办" in combined or "藏品" in combined or "展示柜" in special_text)
    add("名酒聚事", "酒" in kitchen_text or "聚会" in entertainment_text or "招待" in kitchen_text or "6人以上" in kitchen_text or "4-6人" in kitchen_text)
    add("办公学习", "学习成长" in combined and not has_child or "办公" in learning_text or "书房" in learning_text)
    add("美食烘焙", "餐厨茶饮" in combined or "烘焙" in kitchen_text or "做饭" in kitchen_text)
    add("智慧生活", "智慧收纳" in combined or "环境优化" in combined or "智能" in environment_text or "全屋智能" in environment_text)

    return "、".join(categories) or "-"


def _summary_style(basic):
    primary_style = str(basic.get("primary_style") or "").strip()
    if primary_style and primary_style != "-":
        return primary_style
    return _join_values(basic.get("style_preferences"))


def _summary_from_payload(row_id, created_at, name, phone, basic, report, payloads=None):
    basic = _safe_json(basic)
    report = _safe_json(report)

    return {
        "id": row_id,
        "created_at": str(created_at),
        "name": basic.get("wechat_name") or name or basic.get("name", "-"),
        "phone": phone or basic.get("phone", "-"),
        "house_type": _summary_house_type(basic.get("type")),
        "area": basic.get("area", "-"),
        "population_structure": _summary_population(basic.get("people"), basic.get("structure")),
        "budget": _summary_budget(basic.get("budget")),
        "style": _summary_style(basic),
        "lifestyle_focus": _summary_lifestyle_categories(basic, report, payloads),
    }


SUMMARY_COLUMNS = [
    ("id", "客户ID"),
    ("created_at", "提交时间"),
    ("name", "微信/姓名"),
    ("phone", "手机号"),
    ("house_type", "房屋类型"),
    ("area", "房屋面积"),
    ("population_structure", "人口结构"),
    ("budget", "预算"),
    ("style", "风格"),
    ("lifestyle_focus", "生活方式重点"),
]


def _all_survey_summaries():
    query = """
        SELECT id, created_at, name, phone, basic, kitchen, learning, fitness, entertainment, environment, special, report
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
        _summary_from_payload(
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[11],
            {
                "kitchen": _safe_json(row[5]),
                "learning": _safe_json(row[6]),
                "fitness": _safe_json(row[7]),
                "entertainment": _safe_json(row[8]),
                "environment": _safe_json(row[9]),
                "special": _safe_json(row[10]),
            },
        )
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
        "feishu_sheet": "已配置" if _feishu_sheet_configured() else "未配置",
        "admin_auth": "已开启" if ADMIN_PASSWORD else "未开启",
    }


def _feishu_sheet_configured():
    return all(
        [
            FEISHU_APP_ID,
            FEISHU_APP_SECRET,
            FEISHU_SUMMARY_SPREADSHEET_TOKEN,
            FEISHU_SUMMARY_SHEET_ID,
        ]
    )


def _summary_sheet_values(max_rows=None):
    summaries = _all_survey_summaries()
    values = [[title for _, title in SUMMARY_COLUMNS]]
    values.extend(
        [[summary.get(key, "") for key, _ in SUMMARY_COLUMNS] for summary in summaries]
    )

    target_rows = max(max_rows or FEISHU_SUMMARY_SYNC_ROWS or 0, len(values))
    blank_row = [""] * len(SUMMARY_COLUMNS)
    while len(values) < target_rows:
        values.append(blank_row.copy())
    return values


def _feishu_tenant_access_token():
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("msg") or "获取飞书 tenant_access_token 失败")
    return payload["tenant_access_token"]


def sync_feishu_summary_sheet():
    if not _feishu_sheet_configured():
        return {"ok": False, "status": "未配置"}

    values = _summary_sheet_values()
    end_col = _xlsx_col_name(len(SUMMARY_COLUMNS))
    target_range = f"{FEISHU_SUMMARY_SHEET_ID}!A1:{end_col}{len(values)}"
    token = _feishu_tenant_access_token()
    resp = requests.post(
        f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{FEISHU_SUMMARY_SPREADSHEET_TOKEN}/values_batch_update",
        headers={"Authorization": f"Bearer {token}"},
        json={"valueRanges": [{"range": target_range, "values": values}]},
        timeout=15,
    )
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"飞书表格写入失败: HTTP {resp.status_code} {resp.text[:500]}") from exc
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"飞书表格写入失败: {json.dumps(payload, ensure_ascii=False)[:500]}")
    return {"ok": True, "status": "同步成功", "range": target_range, "rows": len(values)}


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
        for idx, width in enumerate([10, 20, 18, 16, 14, 14, 24, 14, 20, 42], start=1)
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


FAMILY_SCENE_LABELS = {
    "kitchen": "餐厨茶饮",
    "bathroom": "卫浴漱妆",
    "sleep": "健康睡眠",
    "laundry": "衣物洗护",
    "storage": "智慧收纳",
    "learning": "学习成长",
    "fitness": "家庭健身",
    "entertainment": "居家娱乐",
    "environment": "环境优化",
    "special": "特殊生活",
}

FAMILY_SCENE_DESCRIPTIONS = {
    "kitchen": "做饭、吃饭、茶饮和家庭聚会",
    "bathroom": "洗漱、如厕、沐浴和梳妆",
    "sleep": "睡眠、夜间起居和个人放松",
    "laundry": "洗、烘、晾、熨、整理和换季",
    "storage": "进门、日用品、个人物品和全屋秩序",
    "learning": "办公、学习、阅读和孩子成长",
    "fitness": "日常运动、器械和运动后整理",
    "entertainment": "观影、游戏、会客和兴趣展示",
    "environment": "空气、水、温度、灯光、智能和安防",
    "special": "婴幼儿、老人、宠物、庭院、车库等扩展生活",
}

FAMILY_SCENE_DESIGN_CHECKLISTS = {
    "kitchen": ["高频做饭、简餐或外卖及同时操作人数", "开放式、半开放、可开可合或中西双厨", "岛台、水吧、早餐台及餐边柜一体化", "蒸烤箱、洗碗机、直饮机、制冰机等厨电清单与内嵌方式", "长桌、圆桌、日常用餐与最大聚餐人数", "台面杂乱、插座、食品囤货及餐后清洁路线", "油烟、声音和餐厨互动边界"],
    "bathroom": ["早晚高峰和多人并行使用", "双台盆、加长台盆或分开洗漱位置", "洗漱、如厕、淋浴、浴缸和梳妆分区", "智能马桶、镜柜、吹风和护肤设备", "防滑、扶手、坐浴、夜间照明及老人儿童安全", "水压、热水等待、潮湿、异味和卫浴收纳"],
    "sleep": ["各成员作息、浅眠、噪声和互相干扰", "主卧套房、独立衣帽、梳妆、休息角和主卧水吧", "双人衣物、包袋、首饰及被褥收纳结构", "遮光、隔音、温湿度、空调直吹和睡眠照明", "夜间起身、饮水和就近卫浴路线", "儿童房、老人房、客房及未来成长转换"],
    "laundry": ["洗、烘、晾、熨和收衣责任人", "洗烘套装、护理机、手洗池及设备尺寸", "脏衣分类、净衣暂存、折叠和分发路线", "阳台并入、独立家政房、隐藏家政柜或隐形晾衣架", "自然晾晒、床品晾晒、采光和通风", "家政协作、清洁工具和耗材收纳"],
    "storage": ["玄关是否过小、是否需要落尘区和独立换鞋位置", "超大鞋柜、雨季杂物、钥匙包袋随手台和消杀区", "隐藏全身镜、坐换鞋凳及入户视线是否见杂乱", "全屋通顶高柜、食品囤货和独立储藏间", "扫地机器人基站、清洁工具和设备隐藏", "行李箱、运动户外、儿童物品和换季收纳", "展示与隐藏比例及外露电线设备控制"],
    "learning": ["独立书房、共享学习区或一房多用", "居家办公、视频会议、直播、阅读、电竞和创作", "儿童成长型书桌、陪伴学习和逐步独立", "隐形床、临时客房及茶室等多功能切换", "大量书籍、手办、藏品和资料展示收纳", "网络、插座、照明、会议背景、隔音和隐私"],
    "fitness": ["运动人、项目、频率和器械尺寸", "净高、承重、地面、减震和隔音", "通风、温控、镜面和照明", "器械收纳及安全边界", "运动前后更衣、饮水和沐浴路线"],
    "entertainment": ["横厅大通透、传统竖厅或分区公共空间", "会客商务感、居家慵懒感或亲子互动感", "是否拒绝笨重茶几、复杂吊顶和复杂造型", "电视背景、无电视柜、整墙收纳、电视或投影方向", "观影、游戏、K歌、背景音乐及专业影音", "声学、遮光、座位人数及对睡眠学习的影响", "收藏展示、防尘、避光和儿童安全"],
    "environment": ["纯白明亮、中性高级或暖深氛围", "主灯、无主灯、磁吸轨道、线性灯及防眩照明接受度", "中央空调、分区空调、地暖、新风和除湿", "前置、中央净水、软水、末端直饮和生活热水", "回家、离家、观影、睡眠、就餐等智能场景", "全屋网络、背景音乐、门禁、监控和报警", "冷热、湿度、空气、噪音及老人儿童易用性"],
    "special": ["老人房是否同层、无障碍、高差、扶手和夜间照明", "儿童成长、保姆房、家政专属收纳和佣人动线", "宠物喂养、活动、收纳、清洁和洗护", "地下室影音、KTV、茶室、酒窖、健身、储物及防潮声学", "庭院硬化、凉亭、水系、草坪、种植、户外水电和照明", "车库、车辆充电、工具收纳和大件搬运", "室内电梯、阁楼、露台、门窗和外立面", "结构、消防、物业、排水、通风及专业设备限制"],
}

FAMILY_SCENE_SEED_RULES = {
    "kitchen": {
        "中式爆炒": "讨论封闭中厨、半开放或可开可合餐厨，并核对排烟条件",
        "多人一起准备": "讨论双人操作动线、双备餐位或岛台辅助",
        "早餐与简餐": "讨论轻食区、早餐台或水吧方向",
        "烘焙或西餐": "预核对蒸烤设备、操作台面和食材收纳",
        "茶、咖啡或酒水": "讨论独立水吧、咖啡角或酒水收纳",
        "经常聚餐": "核对最大聚餐人数、餐桌形式和通行尺度",
        "采购囤货": "讨论食品储藏、冰箱冰柜和餐边高柜扩容",
        "餐后清洁": "讨论洗碗、垃圾分类和餐后回收路线",
    },
    "bathroom": {
        "早晚使用高峰": "讨论干湿分离或多功能并行使用",
        "多人同时准备": "讨论双台盆、加长台盆或分开洗漱位置",
        "洗漱与如厕分开": "讨论洗漱外置或功能分区",
        "泡澡放松": "核对真实频率、浴缸尺度和清洁维护成本",
        "护肤梳妆": "讨论独立梳妆、镜前照明和分类收纳",
        "儿童或老人安全": "讨论防滑、扶手、坐浴和夜间感应照明",
        "潮湿与异味": "核对通风、除湿、地漏和干区边界",
    },
    "sleep": {
        "浅眠或易醒": "讨论安静侧布置、隔音和睡眠场景控制",
        "作息时间不同": "讨论互不干扰的照明、盥洗和更衣路线",
        "怕光": "讨论分层遮光和低位夜间照明",
        "怕噪音": "核对门墙隔音、设备噪声和公共活动距离",
        "对冷热敏感": "讨论分区温控和避免直吹",
        "夜间起身": "讨论无高差路线、感应照明和就近使用",
        "卧室饮水": "讨论卧室水吧、饮水点或小冰箱预留",
    },
    "laundry": {
        "高频洗衣": "讨论集中洗护区及设备容量",
        "烘干": "核对洗烘组合、散热和排水条件",
        "自然晾晒": "保留日照通风合适的晾晒位置或隐形晾晒",
        "床品和大件晾晒": "核对床品晾晒尺度、承重、通风和视觉遮挡",
        "脏衣分类": "讨论分区脏衣收集和送洗路线",
        "净衣暂存": "讨论净衣折叠、暂存和分发位置",
        "熨烫护理": "讨论护理机、熨烫台和挂放位置",
        "清洁工具与耗材": "讨论清洁高柜、耗材分类和设备充电上下水",
        "家政协作": "区分家庭与家政操作、耗材和工具收纳",
    },
    "storage": {
        "入户随手物品": "讨论落尘、坐换鞋、随手台和分类入户收纳",
        "鞋子与雨季物品较多": "核对鞋量、雨具、湿物和雨季杂物收纳",
        "家庭囤货": "核对囤货类别、数量和独立储藏需求",
        "行李箱": "预留按尺寸可取放的大件收纳",
        "清洁工具": "讨论家政柜、机器人基站和上下水电源",
        "运动或户外装备": "讨论耐脏、通风和靠近出入口的装备收纳",
        "收藏展示": "讨论展示与封闭收纳、防尘避光和安全",
        "藏与露的平衡": "先确定展示比例，再规划柜体和开放格",
    },
    "learning": {
        "居家办公": "讨论独立或共享办公位置及长期使用舒适度",
        "视频会议": "核对网络、声学、照明和背景完整性",
        "儿童学习": "讨论可成长桌面、亲子陪伴与独立性",
        "乐器练习": "核对器械尺度、声学和对其他成员的影响",
        "电竞": "核对设备散热、网络、电力和长时坐姿",
        "大量书籍资料": "按藏书量核对书柜承重、防尘和取阅",
        "安静与隐私": "讨论远离公共活动或可关闭的学习环境",
    },
    "fitness": {
        "力量训练": "核对承重、地面保护和器械安全范围",
        "有氧器械": "核对器械尺寸、用电、通风和观看需求",
        "康复训练": "由专业人员核对动作尺度、扶持和安全条件",
        "器械收纳": "讨论器械就近归位和展开尺度",
        "减震隔音": "讨论结构条件下的减震地面和隔音处理",
        "运动后沐浴": "优化健身、更衣、饮水和沐浴路线",
    },
    "entertainment": {
        "家庭观影": "讨论电视或投影、座位、遮光和声场方向",
        "游戏": "核对网络、设备、电力、散热和多人互动",
        "K歌": "先核对声学、扰民和空间封闭条件",
        "亲友会客": "核对来访人数、坐席、茶饮和公私分区",
        "收藏展示": "讨论展示尺度、防尘避光和安防",
        "声音不打扰他人": "讨论娱乐与卧室学习区的距离及隔音",
    },
    "environment": {
        "空气质量": "请暖通专业人员比较新风、过滤和维护方案",
        "除湿防潮": "结合城市、楼层和地下空间核对专项除湿",
        "冬季采暖": "结合气候和使用习惯比较地暖、暖气或热泵",
        "夏季制冷": "核对分区负荷、送回风和避免直吹",
        "生活热水": "核对同时用水点、循环和等待时间",
        "饮水品质": "讨论前置、净水、软水和分区直饮",
        "灯光舒适": "讨论分层照明、防眩和生活场景控制",
        "落地窗与视野": "核对窗框、窗帘盒、家具遮挡和主要观看视线",
        "隐私与遮阳": "讨论分层窗帘、外遮阳和昼夜隐私",
        "网络稳定": "预做全屋有线、无线覆盖和设备位规划",
        "智能控制": "先定义真实场景，并保留断网断电基础操作",
        "安全守护": "讨论门禁、监控、报警和异常提醒",
        "安静环境": "核对外部噪声、设备噪声和房间相互影响",
    },
    "special": {
        "备孕或婴幼儿": "讨论照护视线、夜间路线、成长变化和安全",
        "儿童成长空间": "讨论常规床、书桌、榻榻米和未来功能转换",
        "老人同住": "讨论同层起居、少高差、夜间照明和就近卫浴",
        "行动不便": "请相关专业人员核对无障碍尺度和辅助设施",
        "客人留宿": "核对固定客房或多功能临时留宿方式",
        "保姆或家政人员同住": "讨论保姆房、家政收纳和相对独立的工作动线",
        "家庭厅或亲子共处": "讨论卧室层家庭厅、亲子互动和阅读共处",
        "宠物": "讨论喂养、清洁、洗护、收纳和活动边界",
        "户外装备": "讨论靠近出入口的耐脏清洁和装备收纳",
        "藏品或艺术创作": "核对展示、创作、照明、防尘避光和安全",
        "庭院生活": "讨论户外水电、排水、照明、活动和养护",
        "地下室使用": "先核对防潮、通风、采光、消防和疏散条件",
        "阁楼或露台": "讨论储物、休闲、茶饮、种植及结构防水限制",
        "车辆与充电": "核对车位、充电容量、安防和工具收纳",
        "室内电梯": "核对使用必要性、结构井道、设备和维护条件",
        "大件搬运": "核对入户、电梯、楼梯和转弯尺度",
    },
}

# 生活信号到设计需求的确定性翻译。这里只产出“设计需求候选”，最终布局、尺寸、
# 设备型号和结构做法仍需设计师结合现场、预算及对应专业条件确认。
FAMILY_SCENE_DESIGN_REQUIREMENT_RULES = {
    "kitchen": {
        "日常做饭": ("餐厨功能", "配置完整且连续的清洗、备餐、烹饪和出餐操作链", "核对做饭频率、主要烹饪者和常用锅具"),
        "中式爆炒": ("油烟控制", "餐厨必须具备可关闭或有效隔绝油烟的能力，并预留有效排烟路径", "核对烟道、补风、燃气和物业条件"),
        "多人一起准备": ("操作动线", "操作通道和备餐台需支持至少两人并行且互不挡路", "核对同时操作人数及主要站位"),
        "早餐与简餐": ("轻食功能", "在主烹饪区之外配置便捷的早餐或轻食操作点", "确认是否需要早餐台、水吧或小家电位"),
        "烘焙或西餐": ("厨电与台面", "预留烘焙或西餐所需的连续台面、蒸烤设备位、电力和食材收纳", "列出确定使用的设备及尺寸"),
        "茶、咖啡或酒水": ("饮品功能", "设置独立且就近取水取电的饮品操作与器具收纳位置", "确认茶、咖啡、酒水的使用频率和设备"),
        "经常聚餐": ("餐厅容量", "餐厅及通行尺度需按家庭最大聚餐人数校核", "确认日常人数、最大人数、圆桌或长桌偏好"),
        "采购囤货": ("食品收纳", "按实际囤货量配置食品高柜或储藏区，并预留冰箱、冰柜及补货动线", "核对囤货周期、品类和冷藏冷冻容量"),
        "餐后清洁": ("清洁回收", "配置洗碗、沥水、垃圾分类和餐具回收的连续路线", "确认洗碗机、垃圾处理及清洁习惯"),
    },
    "bathroom": {
        "早晚使用高峰": ("功能分区", "卫浴功能需允许高峰期洗漱、如厕或淋浴并行使用", "核对高峰时段、人数和使用冲突"),
        "多人同时准备": ("洗漱容量", "配置双台盆、加长台盆或分设洗漱点中的一种多人方案", "确认同时使用人数及台面物品量"),
        "洗漱与如厕分开": ("功能分区", "洗漱区与如厕区需物理或动线分离", "结合户型核对外置洗漱或三分离条件"),
        "泡澡放松": ("沐浴设备", "为独立浴缸保留适配尺度、给排水和清洁维护条件", "确认真实频率、使用人和是否接受维护成本"),
        "护肤梳妆": ("梳妆收纳", "配置镜前无阴影照明、护肤品分类收纳和可落座操作位置", "确认是在卫浴区还是独立梳妆区完成"),
        "儿童或老人安全": ("适老适幼", "卫浴需采用防滑、少高差、可扶持和夜间可识别的安全设计", "由设计师核对扶手、坐浴和无障碍尺度"),
        "水温水压": ("给排水机电", "热水系统需满足稳定水温、水压和多点同时用水", "核对入户水压、热源、回水和同时用水点"),
        "潮湿与异味": ("通风防潮", "卫浴需具备有效排风、干湿边界、排水和防返味措施", "核对风道、地漏、门缝补风和除湿条件"),
        "卫浴收纳": ("卫浴收纳", "按日常用品、备品和清洁用品配置干湿分区收纳", "核对各成员物品数量及取用高度"),
    },
    "sleep": {
        "浅眠或易醒": ("安静睡眠", "睡眠区应远离高频公共活动和设备噪声，并加强门墙隔音", "核对主要噪声源和可接受程度"),
        "作息时间不同": ("互不干扰", "更衣、洗漱、照明和进出路线需避免打扰同住者", "核对双方入睡起床时间及夜间活动"),
        "怕光": ("遮光照明", "配置分层遮光系统和不刺激睡眠的低位夜间照明", "确认自然醒需求及遮光程度"),
        "怕噪音": ("隔音", "门、墙、窗及设备选型需围绕睡眠噪声进行专项控制", "核对外部、楼板和室内活动噪声来源"),
        "对冷热敏感": ("分区温控", "睡眠区需支持独立温控并避免空调直吹", "核对冷热偏好、送回风和采暖方式"),
        "夜间起身": ("夜间动线", "床到卫生间及饮水点的路线应少高差、无障碍并设感应照明", "确认起夜频率和行动安全需求"),
        "睡前阅读": ("床边功能", "配置不影响同住者的定向阅读照明、充电和书物收纳", "确认阅读位置和持续时间"),
        "卧室饮水": ("卧室饮水", "在卧室层或套房内配置便捷取水及杯具、小电器收纳位置", "确认饮水点、小冰箱或水吧需求"),
        "个人独处": ("私密放松", "卧室或邻近区域需提供可独处、阅读或短时休息的位置", "确认独处活动和与睡眠区的关系"),
    },
    "laundry": {
        "高频洗衣": ("集中洗护", "设置容量匹配的集中洗护区，并组织洗、烘、晾、收连续路线", "核对每日衣量、分类方式和责任人"),
        "烘干": ("洗烘设备", "预留烘干设备位、散热、排水、电力及维护空间", "确认洗烘套装或一体机及设备尺寸"),
        "自然晾晒": ("晾晒", "保留采光通风合适且不破坏主要生活界面的自然晾晒位置", "确认晾晒量、床品和隐形晾衣接受度"),
        "床品和大件晾晒": ("大件晾晒", "晾晒位置需满足床品展开、承重、通风和不遮挡主要生活界面", "核对最大床品尺寸、频率和晾晒方式"),
        "手洗": ("手洗功能", "配置独立手洗池或适合手洗的深盆与临时沥水位置", "核对手洗衣物种类和频率"),
        "熨烫护理": ("衣物护理", "配置护理机或熨烫台、挂放和电源位置", "确认设备、展开尺寸和使用频率"),
        "脏衣分类": ("脏衣收集", "在更衣或卫浴附近设置分类脏衣收集，并形成送洗路线", "确认分类数量和收集位置"),
        "净衣暂存": ("净衣整理", "设置折叠、挂放、暂存和分发净衣的操作位置", "确认净衣是否当天归位及责任人"),
        "换季衣物": ("换季收纳", "设置防尘、可标识且便于周期取用的换季衣物收纳", "核对体量、箱包及被褥尺寸"),
        "清洁工具与耗材": ("家政收纳", "设置清洁工具高柜、耗材分类、设备充电及必要的上下水条件", "列出吸尘器、洗地机、机器人和耗材体量"),
        "家政协作": ("家政动线", "家庭与家政人员的洗护操作、耗材和工具收纳需清晰分区", "确认家政频率、工作边界和独立区域需求"),
    },
    "storage": {
        "入户随手物品": ("玄关系统", "玄关需形成落尘、坐换鞋、鞋柜、钥匙包袋随手台、雨具及全身镜的一体化系统", "核对鞋量、雨季物品、消杀需求和入户宽度"),
        "鞋子与雨季物品较多": ("玄关容量", "按家庭鞋量配置通风鞋柜，并为雨具、湿物和雨季杂物设置独立落位", "统计常用鞋、换季鞋、雨具及婴儿车等体量"),
        "家庭囤货": ("高柜储藏", "按囤货量配置通顶高柜、食品储藏或独立储藏间", "核对囤货品类、补货周期和取用人"),
        "个人衣物": ("衣物收纳", "衣柜内部需按挂衣、叠放、包袋、首饰和被褥比例定制", "分别统计每位成员的衣物结构"),
        "行李箱": ("大件收纳", "预留按行李箱实际尺寸可直接取放的大件收纳位置", "核对数量、最大尺寸和取用频率"),
        "清洁工具": ("家政收纳", "设置清洁工具高柜、耗材区及扫地机器人基站，并核对上下水和电源", "列出吸尘器、洗地机、机器人及工具尺寸"),
        "运动或户外装备": ("装备收纳", "在靠近出入口处设置耐脏、通风、可清洁的运动户外装备收纳", "核对装备种类、尺寸和清洁路线"),
        "收藏展示": ("展示系统", "展示柜需同时满足陈列、防尘、避光、承重和安全", "核对藏品尺寸、数量、价值和更新频率"),
        "儿童物品": ("儿童收纳", "儿童物品需按年龄配置低位可自主取放和可成长收纳", "核对玩具、书籍、手作及未来变化"),
        "藏与露的平衡": ("视觉秩序", "先确定隐藏收纳与开放展示比例，再规划柜体、开放格和设备遮蔽", "用图片确认可接受的外露程度"),
    },
    "learning": {
        "居家办公": ("办公空间", "配置可长期使用的桌椅尺度、文件收纳、充电和独立照明", "核对使用频率、设备和是否需独立房间"),
        "视频会议": ("会议条件", "办公位置需具备稳定网络、声学隐私、正面照明和整洁背景", "核对会议频率和保密要求"),
        "儿童学习": ("成长学习", "学习位置需支持儿童成长、陪伴与逐步独立，并预留书物扩容", "核对年龄、学习方式和未来五年变化"),
        "阅读": ("阅读功能", "配置舒适座位、定向照明和就近书籍收纳", "确认阅读人数、纸质书量和安静要求"),
        "乐器练习": ("乐器空间", "按乐器尺度配置演奏、收纳、承重和声学边界", "核对乐器类型、频率和对家人的影响"),
        "绘画手作": ("创作空间", "配置耐用工作台、材料分类收纳、清洁和作品晾放展示", "核对材料、用水和作品尺寸"),
        "电竞": ("电竞设备", "配置稳定网络、足够电力、散热、设备位和长时坐姿条件", "核对设备数量、多人使用和声音影响"),
        "大量书籍资料": ("书籍收纳", "按藏书量配置承重、防尘且便于检索的书柜系统", "统计藏书量、尺寸和新增速度"),
        "安静与隐私": ("学习私密", "学习办公区需可关闭或远离高噪声公共活动", "核对声音来源和是否允许共享"),
    },
    "fitness": {
        "瑜伽拉伸": ("轻运动", "预留完整垫面、伸展净空、镜面和器材就近收纳", "核对同时使用人数和课程设备"),
        "力量训练": ("力量器械", "地面、承重、器械安全范围和减震需按力量训练核对", "列出器械重量、尺寸和动作范围"),
        "有氧器械": ("有氧器械", "预留器械尺寸、用电、散热通风和观看条件", "确认跑步机、单车等设备型号"),
        "球类练习": ("运动净空", "净高、墙面保护、地面和安全边界需满足球类动作", "核对项目、频率和室内可行性"),
        "舞蹈": ("舞蹈训练", "配置连续净空、镜面、弹性地面、扶杆或音响条件", "核对舞种、人数和楼板影响"),
        "康复训练": ("康复辅助", "按专业建议预留安全动作尺度、扶持和无障碍条件", "由康复或医疗专业人员复核"),
        "器械收纳": ("健身收纳", "器械需就近归位且不占用主要通道", "统计器械尺寸、重量和取用频率"),
        "减震隔音": ("减震声学", "健身区需结合楼板和相邻房间进行减震隔音设计", "由结构或声学专业人员核对"),
        "运动后沐浴": ("运动后动线", "健身区到饮水、更衣、脏衣和沐浴需形成短而清晰的路线", "确认运动后的实际顺序"),
    },
    "entertainment": {
        "家庭观影": ("观影系统", "按观看距离、座位人数和环境光确定电视或投影及声场条件", "确认电视、投影、幕布和音响偏好"),
        "游戏": ("游戏设备", "配置稳定网络、设备电力、散热、显示和多人座位", "核对主机、电脑、体感及同时人数"),
        "K歌": ("影音声学", "K歌区域需具备可控制声泄漏的空间边界和声学条件", "先核对邻里、楼层、消防和声学可行性"),
        "亲友会客": ("会客客厅", "公共区需按来访人数组织沙发坐席、茶饮服务和公私分区", "确认商务会客、慵懒居家或亲子互动倾向"),
        "儿童活动": ("亲子公共区", "公共区需保留可看护、安全且可快速收纳的儿童活动范围", "核对年龄、活动类型和与会客的切换"),
        "个人娱乐": ("独立娱乐", "为个人娱乐提供不干扰家庭共处的设备、座位和声光边界", "核对活动类型、频率及私密程度"),
        "收藏展示": ("兴趣展示", "展示系统需匹配藏品尺度并满足防尘、避光、承重和安全", "统计藏品及是否需要恒温安防"),
        "家庭共处": ("公共空间", "客餐厅需支持家人同时进行不同活动并保持可交流的关系", "核对横厅、竖厅和活动组合偏好"),
        "声音不打扰他人": ("声学分区", "娱乐区与睡眠学习区需拉开距离或建立可关闭的隔音边界", "核对使用时间、音量和受影响成员"),
    },
    "environment": {
        "空气质量": ("新风空气", "按人数、房屋体量和污染源配置空气过滤与新风条件", "由暖通专业人员核对风量、管路和维护"),
        "除湿防潮": ("除湿防潮", "潮湿区域或地下空间需配置连续防潮、除湿和排水策略", "结合城市、楼层和现场含水情况核对"),
        "冬季采暖": ("采暖系统", "按城市气候和分区使用配置稳定且可控的采暖系统", "比较地暖、暖气片、热泵等方案及能耗"),
        "夏季制冷": ("制冷系统", "空调需按分区负荷配置并避免对人直吹", "由暖通专业人员核对负荷、送回风和室外机"),
        "生活热水": ("热水系统", "热水系统需满足多点同时使用、快速到水和稳定水温", "核对热源、循环、管径和用水峰值"),
        "饮水品质": ("全屋用水", "按饮用、洗浴和设备保护需求配置前置、净水、软水或直饮", "结合水质检测和维护成本确认"),
        "灯光舒适": ("照明系统", "采用分层、防眩、可调的生活场景照明，避免只依赖单一主灯", "核对明亮、中性或暖深氛围及无主灯接受度"),
        "落地窗与视野": ("窗景界面", "主要公共区需减少窗框、家具和窗帘对核心视线的遮挡", "核对门窗条件、窗帘盒、物业限制和主要观看方向"),
        "隐私与遮阳": ("遮阳隐私", "窗帘与遮阳系统需兼顾白天采光、夏季热负荷和夜间隐私", "核对朝向、周边视线和自动窗帘需求"),
        "网络稳定": ("网络系统", "预做全屋有线骨干、无线覆盖、弱电机柜和关键设备点位", "核对带宽、设备数量和影音办公需求"),
        "智能控制": ("全屋智能", "智能系统需围绕回家、离家、睡眠、观影等真实场景，并保留基础手动操作", "确认控制方式、家庭成员易用性和断网降级"),
        "安全守护": ("安防系统", "配置与家庭风险匹配的门禁、监控、报警和异常提醒", "核对老人儿童宠物、庭院和隐私边界"),
        "安静环境": ("全屋声学", "对外部噪声、设备噪声和房间相互干扰进行分区控制", "必要时由门窗或声学专业人员复核"),
    },
    "special": {
        "备孕或婴幼儿": ("婴幼儿照护", "布局需支持照护视线、夜间喂养、成长变化和安全收纳", "核对阶段、照护人及未来房间转换"),
        "儿童成长空间": ("儿童房", "儿童房需在常规床书桌、榻榻米多功能和成长转换之间保留可调整条件", "核对儿童年龄、学习方式、收纳和未来五年变化"),
        "老人同住": ("适老居住", "优先同层起居、少高差、就近卫浴、夜间照明和可扶持条件", "核对长期或阶段性同住及身体情况"),
        "行动不便": ("无障碍", "主要路线需满足通行、转身、扶持和无高差要求", "由相关专业人员按实际辅具尺寸复核"),
        "客人留宿": ("客房留宿", "按留宿频率选择固定客房或可转换的临时留宿空间", "核对来访关系、人数、频率和独立卫浴需求"),
        "保姆或家政人员同住": ("家政居住", "配置保姆休息、家政专属收纳及尽量不干扰家庭私密区的工作路线", "核对是否住家、工作内容和独立卫浴需求"),
        "家庭厅或亲子共处": ("卧室层家庭厅", "卧室层宜设置支持亲子互动、阅读和短时共处的家庭公共位置", "核对使用成员、活动类型和对卧室安静的影响"),
        "宠物": ("宠物系统", "设置喂养、清洁、洗护、用品收纳和人与宠物的活动边界", "核对宠物种类、数量和习惯"),
        "户外装备": ("户外装备", "靠近出入口设置耐脏、通风、可清洗的装备存放和维护区", "统计装备尺寸、泥水和晾干需求"),
        "藏品或艺术创作": ("收藏创作", "配置创作工作面、材料收纳、展示、防尘避光和安防条件", "核对作品材料、尺寸和更新频率"),
        "高频出差": ("行李与归家", "入户、更衣和洗护路线需支持快速收放行李及出差物品", "核对频率、行李数量和常备物品"),
        "庭院生活": ("庭院系统", "庭院需按活动配置硬化、排水、户外水电、照明、收纳和养护条件", "核对会客、种植、儿童宠物及物业边界"),
        "地下室使用": ("地下空间", "地下室功能布局必须同时解决防潮、通风、采光、排水、消防和疏散", "明确影音、健身、储藏等用途后由专业人员复核"),
        "阁楼或露台": ("顶层空间", "阁楼或露台需按储物、休闲、茶饮、种植等真实用途配置并控制荷载防水", "核对净高、结构、防水、排水、防坠和物业限制"),
        "车辆与充电": ("车库充电", "车库需匹配车位、充电、电力容量、通风、安防和工具收纳", "核对车型、数量和充电功率"),
        "室内电梯": ("垂直交通", "根据老人、大件搬运和楼层使用决定电梯或预留井道条件", "由结构、消防和设备专业人员核对"),
        "大件搬运": ("搬运动线", "入户、电梯、楼梯、门洞和转弯需按最大物件校核", "列出钢琴、家具和设备最大尺寸"),
    },
}

FAMILY_HOME_PROFESSIONAL_CHECKS = {
    "地下室": "防潮、防水、排水、通风、采光、消防和疏散需结合现场核对",
    "庭院": "边界、排水、户外水电、照明、绿化和物业限制需核对",
    "露台": "荷载、防水、排水、防坠和物业限制需核对",
    "阁楼": "净高、结构、保温、采光、消防和楼梯条件需核对",
    "车库": "车位尺度、充电容量、通风、排水和安防需核对",
    "室内电梯": "井道、结构、消防、电力、噪音和维护条件需核对",
    "户外泳池或水景": "结构、防水、循环水、机房、用电和儿童安全需专业核对",
    "独立家政区域": "上下水、电力、排风、设备尺寸和家政路线需核对",
}


def _family_project_by_token(token):
    if DATABASE_URL:
        conn = _pg_conn()
        rows = conn.run(
            "SELECT id, token, coordinator_token, coordinator_member_id, home_name, home_profile, status, created_at FROM family_projects WHERE token = :token",
            token=token,
        )
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT id, token, coordinator_token, coordinator_member_id, home_name, home_profile, status, created_at FROM family_projects WHERE token = ?",
            (token,),
        ).fetchall()
        conn.close()
    if not rows:
        return None
    row = rows[0]
    return {
        "id": row[0],
        "token": row[1],
        "coordinator_token": row[2],
        "coordinator_member_id": row[3],
        "home_name": row[4],
        "home_profile": _safe_json(row[5]),
        "status": row[6],
        "created_at": str(row[7]),
    }


def _family_project_by_id(project_id):
    if DATABASE_URL:
        conn = _pg_conn()
        rows = conn.run(
            "SELECT id, token, coordinator_token, coordinator_member_id, home_name, home_profile, status, created_at FROM family_projects WHERE id = :id",
            id=project_id,
        )
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT id, token, coordinator_token, coordinator_member_id, home_name, home_profile, status, created_at FROM family_projects WHERE id = ?",
            (project_id,),
        ).fetchall()
        conn.close()
    if not rows:
        return None
    row = rows[0]
    return {
        "id": row[0],
        "token": row[1],
        "coordinator_token": row[2],
        "coordinator_member_id": row[3],
        "home_name": row[4],
        "home_profile": _safe_json(row[5]),
        "status": row[6],
        "created_at": str(row[7]),
    }


def _family_members(project_id):
    query = """
        SELECT id, member_token, display_name, role, age_group, answer_source,
               answers, report, status, created_at
        FROM family_members WHERE project_id = {placeholder} ORDER BY id
    """
    if DATABASE_URL:
        conn = _pg_conn()
        rows = conn.run(query.format(placeholder=":project_id"), project_id=project_id)
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(query.format(placeholder="?"), (project_id,)).fetchall()
        conn.close()
    return [
        {
            "id": row[0],
            "member_token": row[1],
            "display_name": row[2],
            "role": row[3] or "家庭成员",
            "age_group": row[4] or "-",
            "answer_source": row[5] or "-",
            "answers": _safe_json(row[6]),
            "report": _safe_json(row[7]),
            "status": row[8],
            "created_at": str(row[9]),
        }
        for row in rows
    ]


def _family_project_list():
    if DATABASE_URL:
        conn = _pg_conn()
        rows = conn.run(
            """
            SELECT p.id, p.token, p.coordinator_token, p.home_name, p.home_profile, p.status, p.created_at,
                   COUNT(m.id) AS member_count
            FROM family_projects p
            LEFT JOIN family_members m ON m.project_id = p.id
            GROUP BY p.id, p.token, p.coordinator_token, p.home_name, p.home_profile, p.status, p.created_at
            ORDER BY p.id DESC
            """
        )
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            """
            SELECT p.id, p.token, p.coordinator_token, p.home_name, p.home_profile, p.status, p.created_at,
                   COUNT(m.id) AS member_count
            FROM family_projects p
            LEFT JOIN family_members m ON m.project_id = p.id
            GROUP BY p.id
            ORDER BY p.id DESC
            """
        ).fetchall()
        conn.close()
    return [
        {
            "id": row[0],
            "token": row[1],
            "coordinator_token": row[2],
            "home_name": row[3],
            "home_profile": _safe_json(row[4]),
            "status": row[5],
            "created_at": str(row[6]),
            "member_count": row[7],
        }
        for row in rows
    ]


def _count_values(members, getter):
    counts = {}
    names = {}
    for member in members:
        for value in _as_list(getter(member)):
            if not value:
                continue
            counts[value] = counts.get(value, 0) + 1
            names.setdefault(value, []).append(member["display_name"])
    return counts, names


def _preference_detail(preference):
    selections = [str(item) for item in _as_list(preference.get("selections")) if item]
    detail = str(preference.get("detail", "")).strip()
    return "、".join(selections + ([detail] if detail else []))


def _build_family_scene_reports(members):
    reports = []
    for scene_id, scene_name in FAMILY_SCENE_LABELS.items():
        member_views = []
        need_members = {}
        need_ratings = {}
        confirmed_wants = []
        confirmed_avoids = []
        pending_questions = []
        seed_candidates = {}
        important_count = 0
        affected_count = 0

        for member in members:
            answers = member["answers"]
            rating = answers.get("scene_scan", {}).get(scene_id, "未回答")
            detail = answers.get("scene_details", {}).get(scene_id, {})
            if not isinstance(detail, dict):
                detail = {}
            needs = [str(item) for item in _as_list(detail.get("needs")) if item]
            note = str(detail.get("note", "")).strip()
            impact = str(detail.get("impact", "")).strip()
            want = str(detail.get("want", "")).strip()
            avoid = str(detail.get("avoid", "")).strip()
            if rating == "经常参与，而且很重要":
                important_count += 1
            if rating in ["经常参与，而且很重要", "偶尔参与，但有明确想法", "不直接参与，但结果会影响我"]:
                affected_count += 1
            for need in needs:
                need_members.setdefault(need, []).append(member["display_name"])
                need_ratings.setdefault(need, []).append(rating)
                seed = FAMILY_SCENE_SEED_RULES.get(scene_id, {}).get(need)
                if seed:
                    seed_candidates.setdefault(seed, {"source": need, "members": []})["members"].append(
                        member["display_name"]
                    )
            if want:
                confirmed_wants.append({"member": member["display_name"], "item": want, "source": "场景明确想要"})
            if avoid:
                confirmed_avoids.append({"member": member["display_name"], "item": avoid, "source": "场景明确不要"})

            professional = []
            for key, preference in answers.get("professional", {}).items():
                if not key.startswith(f"{scene_id}_") or not isinstance(preference, dict):
                    continue
                status = str(preference.get("status", "")).strip()
                label = str(preference.get("label", key)).strip()
                detail_text = _preference_detail(preference)
                item = {"label": label, "status": status, "detail": detail_text}
                professional.append(item)
                if status == "已经明确想要":
                    if detail_text:
                        confirmed_wants.append(
                            {"member": member["display_name"], "item": f"{label}：{detail_text}", "source": "明确专业偏好"}
                        )
                    else:
                        pending_questions.append(
                            {"member": member["display_name"], "item": label, "status": "已选择明确想要，但具体形式未填写"}
                        )
                elif status == "明确不考虑":
                    confirmed_avoids.append(
                        {"member": member["display_name"], "item": label, "source": "明确专业偏好"}
                    )
                elif status in ["想了解，请设计师解释", "没有明确想法，请设计师判断"]:
                    pending_questions.append(
                        {"member": member["display_name"], "item": label, "status": status}
                    )

            if rating != "未回答" or needs or note or impact or want or avoid or professional:
                member_views.append(
                    {
                        "name": member["display_name"],
                        "role": member["role"],
                        "rating": rating,
                        "needs": needs,
                        "note": note,
                        "impact": impact,
                        "want": want,
                        "avoid": avoid,
                        "professional": professional,
                    }
                )

        if important_count >= 2:
            priority = "家庭共同重点"
        elif important_count == 1:
            priority = "成员重点"
        elif affected_count:
            priority = "相关或受影响"
        elif any(view["rating"] == "还没想过" for view in member_views):
            priority = "待启发"
        else:
            priority = "低关联"

        design_inputs = [
            {
                "level": "需要支持",
                "item": need,
                "members": names,
                "evidence": "成员在生活场景中主动选择",
            }
            for need, names in need_members.items()
        ]
        design_inputs.extend(
            {
                "level": "明确想要",
                "item": item["item"],
                "members": [item["member"]],
                "evidence": item["source"],
            }
            for item in confirmed_wants
        )
        design_requirements = []
        seen_requirements = set()
        for need, names in need_members.items():
            rule = FAMILY_SCENE_DESIGN_REQUIREMENT_RULES.get(scene_id, {}).get(need)
            if not rule:
                continue
            category, requirement, verify = rule
            key = (category, requirement)
            if key in seen_requirements:
                continue
            seen_requirements.add(key)
            ratings_for_need = need_ratings.get(need, [])
            if len(set(names)) >= 2:
                status = "家庭共同需求"
            elif "经常参与，而且很重要" in ratings_for_need:
                status = "重点确认"
            else:
                status = "设计候选"
            design_requirements.append(
                {
                    "category": category,
                    "requirement": requirement,
                    "status": status,
                    "evidence": need,
                    "members": list(dict.fromkeys(names)),
                    "verify": verify,
                }
            )
        for item in confirmed_wants:
            key = ("客户明确要求", item["item"])
            if key in seen_requirements:
                continue
            seen_requirements.add(key)
            design_requirements.append(
                {
                    "category": "客户明确要求",
                    "requirement": item["item"],
                    "status": "客户明确提出",
                    "evidence": item["source"],
                    "members": [item["member"]],
                    "verify": "确认具体落实方式、尺寸条件及与其他成员需求的关系",
                }
            )
        missing = []
        for view in member_views:
            if view["rating"] == "经常参与，而且很重要" and not any(
                [view["needs"], view["note"], view["want"], view["avoid"], view["professional"]]
            ):
                missing.append(f'{view["name"]}将此列为重要场景，但没有补充具体生活内容。')
        reports.append(
            {
                "id": scene_id,
                "name": scene_name,
                "description": FAMILY_SCENE_DESCRIPTIONS[scene_id],
                "priority": priority,
                "important_count": important_count,
                "affected_count": affected_count,
                "member_views": member_views,
                "design_inputs": design_inputs,
                "design_requirements": design_requirements,
                "confirmed_avoids": confirmed_avoids,
                "pending_questions": pending_questions,
                "seeds": [
                    {
                        "item": seed,
                        "reason": data["source"],
                        "members": list(dict.fromkeys(data["members"])),
                        "status": "待设计师结合现场和预算确认",
                    }
                    for seed, data in seed_candidates.items()
                ],
                "design_checklist": FAMILY_SCENE_DESIGN_CHECKLISTS[scene_id],
                "missing": missing,
            }
        )
    return reports


def _build_customer_family_summary(project, members, scene_reports=None):
    scene_reports = scene_reports or _build_family_scene_reports(members)
    feeling_counts, _ = _count_values(
        members, lambda member: member["answers"].get("vision", {}).get("feelings", [])
    )
    activity_counts, _ = _count_values(
        members, lambda member: member["answers"].get("vision", {}).get("future_activities", [])
    )
    boundary_counts, _ = _count_values(
        members, lambda member: member["answers"].get("vision", {}).get("boundaries", [])
    )
    shared_feelings = [value for value, count in feeling_counts.items() if count >= 2]
    shared_activities = [value for value, count in activity_counts.items() if count >= 2]
    shared_boundaries = [
        value
        for value, count in boundary_counts.items()
        if count >= 2 and value != "没有特别需要避免的体验"
    ]
    focus_scenes = [
        {
            "name": item["name"],
            "description": item["description"],
            "level": item["priority"],
        }
        for item in scene_reports
        if item["priority"] in ["家庭共同重点", "成员重点"]
    ]
    profile = project.get("home_profile") or {}
    headline_parts = []
    if shared_feelings:
        headline_parts.append(f'全家共同期待：{"、".join(shared_feelings[:3])}')
    if focus_scenes:
        headline_parts.append(f'重点生活：{"、".join(item["name"] for item in focus_scenes[:5])}')
    return {
        "home_name": project["home_name"],
        "home_profile": {
            key: profile.get(key)
            for key in ["house_type", "city", "area", "levels", "stage", "move_in", "future_changes", "home_features"]
            if profile.get(key)
        },
        "member_count": len(members),
        "headline": "；".join(headline_parts) or "家庭成员的生活需求已经完成汇总",
        "shared_feelings": shared_feelings,
        "shared_activities": shared_activities,
        "shared_boundaries": shared_boundaries,
        "focus_scenes": focus_scenes,
        "note": "这是一份家庭生活需求简报，不是户型布局、设备选型或最终设计方案。家庭成员的具体回答和分歧仅供设计师内部查看。",
    }


def _build_family_summary(project, members):
    feeling_counts, feeling_names = _count_values(
        members, lambda member: member["answers"].get("vision", {}).get("feelings", [])
    )
    boundary_counts, boundary_names = _count_values(
        members, lambda member: member["answers"].get("vision", {}).get("boundaries", [])
    )
    consensus = []
    if len(members) >= 2:
        for value, count in feeling_counts.items():
            if count >= 2:
                consensus.append({"type": "共同期待", "value": value, "members": feeling_names[value]})
        for value, count in boundary_counts.items():
            if count >= 2 and value != "没有特别需要避免的体验":
                consensus.append({"type": "共同边界", "value": value, "members": boundary_names[value]})
        for scene_id, scene_label in FAMILY_SCENE_LABELS.items():
            names = [
                member["display_name"]
                for member in members
                if member["answers"].get("scene_scan", {}).get(scene_id) == "经常参与，而且很重要"
            ]
            if len(names) >= 2:
                consensus.append({"type": "共同重点场景", "value": scene_label, "members": names})

    personal = []
    for member in members:
        answers = member["answers"]
        vision = answers.get("vision", {})
        final = answers.get("final", {})
        explicit_preferences = []
        for preference in answers.get("professional", {}).values():
            if not isinstance(preference, dict) or preference.get("status") != "已经明确想要":
                continue
            detail = _preference_detail(preference)
            explicit_preferences.append(
                f'{preference.get("label", "专业偏好")}：{detail or "尚未说明具体形式"}'
            )
        active_scenes = []
        important_scenes = []
        for scene_id, rating in answers.get("scene_scan", {}).items():
            if rating in ["经常参与，而且很重要", "偶尔参与，但有明确想法", "不直接参与，但结果会影响我"]:
                active_scenes.append(FAMILY_SCENE_LABELS.get(scene_id, scene_id))
            if rating == "经常参与，而且很重要":
                important_scenes.append(FAMILY_SCENE_LABELS.get(scene_id, scene_id))
        priorities = list(
            dict.fromkeys(
                _as_list(final.get("priorities"))
                + _as_list(vision.get("feelings"))
                + important_scenes
            )
        )
        personal.append(
            {
                "name": member["display_name"],
                "role": member["role"],
                "future_day": vision.get("future_day", ""),
                "priorities": priorities,
                "non_negotiable": final.get("non_negotiable", ""),
                "active_scenes": active_scenes,
                "explicit_preferences": explicit_preferences,
                "designer_questions": final.get("designer_questions", ""),
            }
        )

    professional_by_key = {}
    designer_checks = []
    for member in members:
        for key, preference in member["answers"].get("professional", {}).items():
            if not isinstance(preference, dict) or not preference.get("status"):
                continue
            professional_by_key.setdefault(key, []).append(
                {
                    "name": member["display_name"],
                    "label": preference.get("label", key),
                    "status": preference["status"],
                    "selections": _as_list(preference.get("selections")),
                    "detail": str(preference.get("detail", "")).strip(),
                }
            )
            if preference["status"] in ["想了解，请设计师解释", "没有明确想法，请设计师判断"]:
                designer_checks.append(
                    {
                        "member": member["display_name"],
                        "item": preference.get("label", key),
                        "status": preference["status"],
                    }
                )

    conflicts = []
    for preferences in professional_by_key.values():
        statuses = {item["status"] for item in preferences}
        if "已经明确想要" in statuses and "明确不考虑" in statuses:
            conflicts.append(
                {
                    "type": "专业偏好冲突",
                    "item": preferences[0]["label"],
                    "views": preferences,
                    "note": "只陈述分歧，请设计师结合生活原因与房屋条件组织讨论。",
                }
            )

    insufficient = []
    if len(members) < 2:
        insufficient.append("目前只有一位成员提交，暂不判断家庭共识或成员冲突。")
    if not project.get("home_profile"):
        insufficient.append("住宅基础资料尚未补充完整。")
    for member in members:
        pending_scenes = [
            FAMILY_SCENE_LABELS.get(scene_id, scene_id)
            for scene_id, rating in member["answers"].get("scene_scan", {}).items()
            if rating == "还没想过"
        ]
        if pending_scenes:
            insufficient.append(f'{member["display_name"]}尚未考虑：{"、".join(pending_scenes)}。')

    scene_reports = _build_family_scene_reports(members)
    report_stats = {
        "scene_count": len(scene_reports),
        "focus_scene_count": sum(
            1 for item in scene_reports if item["priority"] in ["家庭共同重点", "成员重点"]
        ),
        "design_requirement_count": sum(len(item["design_requirements"]) for item in scene_reports),
        "confirmed_requirement_count": sum(
            1
            for item in scene_reports
            for requirement in item["design_requirements"]
            if requirement["status"] in ["客户明确提出", "家庭共同需求"]
        ),
        "pending_count": sum(
            len(item["pending_questions"]) + len(item["missing"]) for item in scene_reports
        ),
    }
    styles = []
    for member in members:
        style_answers = member["answers"].get("styles", {})
        styles.append(
            {
                "member": member["display_name"],
                "liked": _as_list(style_answers.get("liked")),
                "avoid": str(style_answers.get("avoid", "")).strip(),
                "surface_finish": str(style_answers.get("surface_finish", "")).strip(),
                "wood_tone": str(style_answers.get("wood_tone", "")).strip(),
                "lasting_preference": str(style_answers.get("lasting_preference", "")).strip(),
                "avoid_details": str(style_answers.get("avoid_details", "")).strip(),
            }
        )
    style_likes = {}
    style_avoids = {}
    for item in styles:
        for style in item["liked"]:
            style_likes.setdefault(style, []).append(item["member"])
        if item["avoid"]:
            style_avoids.setdefault(item["avoid"], []).append(item["member"])
    for style in sorted(set(style_likes) & set(style_avoids)):
        views = [
            {"name": name, "status": "喜欢", "selections": [style], "detail": ""}
            for name in style_likes[style]
        ] + [
            {"name": name, "status": "明确避免", "selections": [style], "detail": ""}
            for name in style_avoids[style]
        ]
        conflicts.append(
            {
                "type": "视觉偏好冲突",
                "item": style,
                "views": views,
                "note": "保留原始表达，不自动判断最终风格；请设计师通过图片和材质继续核对。",
            }
        )
    home_profile = project.get("home_profile") or {}
    home_professional_checks = [
        {"item": feature, "check": FAMILY_HOME_PROFESSIONAL_CHECKS[feature]}
        for feature in _as_list(home_profile.get("home_features"))
        if feature in FAMILY_HOME_PROFESSIONAL_CHECKS
    ]
    if str(home_profile.get("known_limits", "")).strip():
        home_professional_checks.append(
            {"item": "已知限制", "check": str(home_profile["known_limits"]).strip()}
        )

    return {
        "project": project,
        "member_count": len(members),
        "members": [
            {
                "id": member["id"],
                "display_name": member["display_name"],
                "role": member["role"],
                "age_group": member["age_group"],
                "created_at": member["created_at"],
            }
            for member in members
        ],
        "consensus": consensus,
        "personal": personal,
        "conflicts": conflicts,
        "designer_checks": designer_checks,
        "insufficient": insufficient,
        "scene_reports": scene_reports,
        "report_stats": report_stats,
        "styles": styles,
        "home_professional_checks": home_professional_checks,
        "customer_summary": _build_customer_family_summary(project, members, scene_reports),
    }


def _create_family_project_record(home_name, home_profile=None):
    requested_name = str(home_name or "").strip()
    stored_name = requested_name or "我的新家"
    token = secrets.token_urlsafe(18)
    coordinator_token = secrets.token_urlsafe(24)
    profile_json = json.dumps(home_profile or {}, ensure_ascii=False)
    if DATABASE_URL:
        conn = _pg_conn()
        project_id = conn.run(
            """
            INSERT INTO family_projects (token, coordinator_token, home_name, home_profile)
            VALUES (:token, :coordinator_token, :home_name, :home_profile) RETURNING id
            """,
            token=token,
            coordinator_token=coordinator_token,
            home_name=stored_name,
            home_profile=profile_json,
        )[0][0]
        if not requested_name:
            stored_name = f"我的新家 #{project_id}"
            conn.run(
                "UPDATE family_projects SET home_name=:home_name WHERE id=:id",
                home_name=stored_name,
                id=project_id,
            )
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute(
            "INSERT INTO family_projects (token, coordinator_token, home_name, home_profile) VALUES (?, ?, ?, ?)",
            (token, coordinator_token, stored_name, profile_json),
        )
        project_id = cursor.lastrowid
        if not requested_name:
            stored_name = f"我的新家 #{project_id}"
            conn.execute(
                "UPDATE family_projects SET home_name=? WHERE id=?",
                (stored_name, project_id),
            )
        conn.commit()
        conn.close()
    return project_id, token, coordinator_token, stored_name


def _family_coordinator_authorized(project, request):
    supplied = request.headers.get("X-Family-Coordinator-Token", "").strip()
    expected = str(project.get("coordinator_token") or "").strip()
    return bool(supplied and expected and secrets.compare_digest(supplied, expected))


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/family.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers={"Cache-Control": "no-store"})


@app.get("/legacy-survey", response_class=HTMLResponse)
async def legacy_survey():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers={"Cache-Control": "no-store"})


@app.get("/jiabao-ai", response_class=HTMLResponse)
async def jiabao_ai():
    with open("static/jiabao-ai.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/family", response_class=HTMLResponse)
@app.get("/family/{project_token}", response_class=HTMLResponse)
async def family_survey(project_token: str = ""):
    with open("static/family.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers={"Cache-Control": "no-store"})


@app.get("/admin/families", response_class=HTMLResponse)
async def family_admin_page(request: Request):
    if not _admin_authorized(request):
        return RedirectResponse("/admin")
    with open("static/family-admin.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers={"Cache-Control": "no-store"})


@app.post("/api/admin/family-projects")
async def create_family_project(request: Request):
    if not _admin_authorized(request):
        return _admin_unauthorized_response()
    data = await request.json()
    home_name = str(data.get("home_name", "")).strip()
    if not home_name:
        return JSONResponse({"code": 400, "message": "请填写住宅称呼"}, status_code=400)
    project_id, token, coordinator_token, _ = _create_family_project_record(home_name, data.get("home_profile", {}))
    base_url = BASE_URL.rstrip("/") if BASE_URL else str(request.base_url).rstrip("/")
    return {
        "code": 0,
        "id": project_id,
        "token": token,
        "invite_url": f"{base_url}/family/{token}",
        "coordinator_url": f"{base_url}/family/{token}?coordinator={coordinator_token}",
    }


@app.post("/api/family-projects")
async def create_public_family_project(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    home_name = str(data.get("home_name", "")).strip() if isinstance(data, dict) else ""
    project_id, token, coordinator_token, stored_name = _create_family_project_record(home_name)
    base_url = BASE_URL.rstrip("/") if BASE_URL else str(request.base_url).rstrip("/")
    return {
        "code": 0,
        "id": project_id,
        "token": token,
        "invite_url": f"{base_url}/family/{token}",
        "coordinator_token": coordinator_token,
        "project": {
            "home_name": stored_name,
            "home_profile": {},
            "needs_home_profile": True,
            "member_count": 0,
            "status": "active",
        },
    }


@app.get("/api/admin/family-projects")
async def list_family_projects(request: Request):
    if not _admin_authorized(request):
        return _admin_unauthorized_response()
    return {"code": 0, "items": _family_project_list()}


@app.get("/api/admin/family-projects/{project_id}")
async def get_family_project_report(project_id: int, request: Request):
    if not _admin_authorized(request):
        return _admin_unauthorized_response()
    project = _family_project_by_id(project_id)
    if not project:
        return JSONResponse({"code": 404, "message": "家庭项目不存在"}, status_code=404)
    members = _family_members(project_id)
    return {"code": 0, "summary": _build_family_summary(project, members)}


@app.get("/api/family-projects/{project_token}")
async def get_family_project(project_token: str, request: Request):
    project = _family_project_by_token(project_token)
    if not project or project["status"] not in ["active", "ready_for_review"]:
        return JSONResponse({"code": 404, "message": "家庭需求链接无效或已关闭"}, status_code=404)
    members = _family_members(project["id"])
    is_coordinator = _family_coordinator_authorized(project, request)
    public_profile = {
        key: project["home_profile"].get(key)
        for key in ["house_type", "city", "area", "levels", "stage"]
        if project["home_profile"].get(key)
    }
    return {
        "code": 0,
        "project": {
            "home_name": project["home_name"],
            "home_profile": public_profile,
            "needs_home_profile": is_coordinator and not bool(project["home_profile"]),
            "member_count": len(members),
            "status": project["status"],
            "is_coordinator": is_coordinator,
            "coordinator_submitted": bool(is_coordinator and project.get("coordinator_member_id")),
            "coordinator_member_id": project.get("coordinator_member_id") if is_coordinator else None,
        },
    }


@app.get("/api/family-projects/{project_token}/summary")
async def get_customer_family_summary(project_token: str):
    project = _family_project_by_token(project_token)
    if not project or project["status"] != "ready_for_review":
        return JSONResponse({"code": 404, "message": "家庭需求简报尚未生成"}, status_code=404)
    members = _family_members(project["id"])
    if not members:
        return JSONResponse({"code": 404, "message": "暂无家庭成员答卷"}, status_code=404)
    return {"code": 0, "summary": _build_customer_family_summary(project, members)}


@app.post("/api/family-projects/{project_token}/complete")
async def complete_family_project(project_token: str, request: Request):
    project = _family_project_by_token(project_token)
    if not project:
        return JSONResponse({"code": 404, "message": "家庭需求链接无效"}, status_code=404)
    if not _family_coordinator_authorized(project, request):
        return JSONResponse(
            {"code": 403, "message": "只有最初收到主链接的家庭主理人可以结束家庭填写"},
            status_code=403,
        )
    if not project.get("coordinator_member_id"):
        return JSONResponse({"code": 400, "message": "请先提交家庭主理人的个人需求"}, status_code=400)
    members = _family_members(project["id"])
    if not members:
        return JSONResponse({"code": 400, "message": "至少需要一位家庭成员先提交"}, status_code=400)
    if DATABASE_URL:
        conn = _pg_conn()
        conn.run(
            "UPDATE family_projects SET status='ready_for_review', updated_at=CURRENT_TIMESTAMP WHERE id=:id",
            id=project["id"],
        )
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE family_projects SET status='ready_for_review', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (project["id"],),
        )
        conn.commit()
        conn.close()
    base_url = BASE_URL.rstrip("/") if BASE_URL else str(request.base_url).rstrip("/")
    return {
        "code": 0,
        "status": "ready_for_review",
        "member_count": len(members),
        "admin_report_url": f"{base_url}/admin/families?project={project['id']}",
        "message": "家庭填写已完成，汇总已进入设计师后台",
    }


@app.post("/api/family-projects/{project_token}/members")
async def submit_family_member(project_token: str, request: Request):
    project = _family_project_by_token(project_token)
    if not project or project["status"] != "active":
        return JSONResponse({"code": 404, "message": "家庭需求链接无效或已关闭"}, status_code=404)
    data = await request.json()
    identity = data.get("identity", {}) if isinstance(data.get("identity"), dict) else {}
    display_name = str(identity.get("display_name", "")).strip()
    role = str(identity.get("role", "")).strip()
    age_group = str(identity.get("age_group", "")).strip()
    answer_source = str(identity.get("answer_source", "")).strip() or "未单独询问"
    answers = data.get("answers", {}) if isinstance(data.get("answers"), dict) else {}
    if not role:
        return JSONResponse({"code": 400, "message": "请选择家庭身份"}, status_code=400)
    if not display_name:
        display_name = role
    if not answers.get("scene_scan"):
        return JSONResponse({"code": 400, "message": "请完成生活场景快速扫描"}, status_code=400)

    home_profile = data.get("home_profile") if isinstance(data.get("home_profile"), dict) else None
    answers_json = json.dumps(answers, ensure_ascii=False)
    report_json = json.dumps(data.get("report", {}), ensure_ascii=False)
    member_token = str(data.get("member_token", "")).strip()
    if DATABASE_URL:
        conn = _pg_conn()
        existing = []
        if member_token:
            existing = conn.run(
                "SELECT id FROM family_members WHERE member_token = :member_token AND project_id = :project_id",
                member_token=member_token,
                project_id=project["id"],
            )
        if existing:
            member_id = existing[0][0]
            conn.run(
                """
                UPDATE family_members SET display_name=:display_name, role=:role, age_group=:age_group,
                    answer_source=:answer_source, answers=:answers, report=:report,
                    status='submitted', updated_at=CURRENT_TIMESTAMP WHERE id=:id
                """,
                display_name=display_name,
                role=role,
                age_group=age_group,
                answer_source=answer_source,
                answers=answers_json,
                report=report_json,
                id=member_id,
            )
        else:
            member_token = secrets.token_urlsafe(18)
            member_id = conn.run(
                """
                INSERT INTO family_members
                    (project_id, member_token, display_name, role, age_group, answer_source, answers, report)
                VALUES (:project_id, :member_token, :display_name, :role, :age_group, :answer_source, :answers, :report)
                RETURNING id
                """,
                project_id=project["id"],
                member_token=member_token,
                display_name=display_name,
                role=role,
                age_group=age_group,
                answer_source=answer_source,
                answers=answers_json,
                report=report_json,
            )[0][0]
        if home_profile and not project["home_profile"]:
            submitted_home_name = str(home_profile.get("home_name", "")).strip() or project["home_name"]
            conn.run(
                "UPDATE family_projects SET home_name=:home_name, home_profile=:profile, updated_at=CURRENT_TIMESTAMP WHERE id=:id",
                home_name=submitted_home_name,
                profile=json.dumps(home_profile, ensure_ascii=False),
                id=project["id"],
            )
        if _family_coordinator_authorized(project, request) and not project.get("coordinator_member_id"):
            conn.run(
                "UPDATE family_projects SET coordinator_member_id=:member_id, updated_at=CURRENT_TIMESTAMP WHERE id=:id",
                member_id=member_id,
                id=project["id"],
            )
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        existing = None
        if member_token:
            existing = conn.execute(
                "SELECT id FROM family_members WHERE member_token = ? AND project_id = ?",
                (member_token, project["id"]),
            ).fetchone()
        if existing:
            member_id = existing[0]
            conn.execute(
                """
                UPDATE family_members SET display_name=?, role=?, age_group=?, answer_source=?,
                    answers=?, report=?, status='submitted', updated_at=CURRENT_TIMESTAMP WHERE id=?
                """,
                (display_name, role, age_group, answer_source, answers_json, report_json, member_id),
            )
        else:
            member_token = secrets.token_urlsafe(18)
            cursor = conn.execute(
                """
                INSERT INTO family_members
                    (project_id, member_token, display_name, role, age_group, answer_source, answers, report)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (project["id"], member_token, display_name, role, age_group, answer_source, answers_json, report_json),
            )
            member_id = cursor.lastrowid
        if home_profile and not project["home_profile"]:
            submitted_home_name = str(home_profile.get("home_name", "")).strip() or project["home_name"]
            conn.execute(
                "UPDATE family_projects SET home_name=?, home_profile=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (submitted_home_name, json.dumps(home_profile, ensure_ascii=False), project["id"]),
            )
        if _family_coordinator_authorized(project, request) and not project.get("coordinator_member_id"):
            conn.execute(
                "UPDATE family_projects SET coordinator_member_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (member_id, project["id"]),
            )
        conn.commit()
        conn.close()

    base_url = BASE_URL.rstrip("/") if BASE_URL else str(request.base_url).rstrip("/")
    return {
        "code": 0,
        "member_id": member_id,
        "member_token": member_token,
        "member_count": len(_family_members(project["id"])),
        "invite_url": f"{base_url}/family/{project_token}",
        "message": "您的个人需求已加入家庭项目",
    }


@app.post("/api/admin/family-projects/{project_id}/reopen")
async def reopen_family_project(project_id: int, request: Request):
    if not _admin_authorized(request):
        return _admin_unauthorized_response()
    project = _family_project_by_id(project_id)
    if not project:
        return JSONResponse({"code": 404, "message": "家庭项目不存在"}, status_code=404)
    if DATABASE_URL:
        conn = _pg_conn()
        conn.run(
            "UPDATE family_projects SET status='active', updated_at=CURRENT_TIMESTAMP WHERE id=:id",
            id=project_id,
        )
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE family_projects SET status='active', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (project_id,),
        )
        conn.commit()
        conn.close()
    return {"code": 0, "status": "active", "message": "家庭项目已重新开放填写"}


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "database": "postgres" if DATABASE_URL else "sqlite",
        "feishu": "configured" if FEISHU_WEBHOOK else "missing",
        "feishu_sheet": "configured" if _feishu_sheet_configured() else "missing",
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

    feishu_sheet_status = "未配置"
    if _feishu_sheet_configured():
        try:
            sync_feishu_summary_sheet()
            feishu_sheet_status = "同步成功"
        except Exception as e:
            feishu_sheet_status = f"同步失败: {str(e)}"

    return {
        "code": 0,
        "id": survey_id,
        "message": "提交成功",
        "feishu_status": feishu_status,
        "feishu_sheet_status": feishu_sheet_status,
    }


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


@app.post("/api/admin/sync-summary-sheet")
async def sync_summary_sheet(request: Request):
    if not _admin_authorized(request):
        return _admin_unauthorized_response()
    try:
        result = sync_feishu_summary_sheet()
    except Exception as e:
        return JSONResponse({"code": 500, "message": str(e)}, status_code=500)
    status_code = 200 if result.get("ok") else 400
    return JSONResponse({"code": 0 if result.get("ok") else 400, **result}, status_code=status_code)


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
                    <a class="btn" href="/admin/families">家庭需求项目</a>
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
                    <div class="status-note">数据库 / 飞书 / 飞书表格 / 后台保护</div>
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
                        <div class="status-note">飞书群：${escapeHtml(status.feishu || '-')}；飞书表格：${escapeHtml(status.feishu_sheet || '-')}；后台：${escapeHtml(status.admin_auth || '-')}</div>
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
