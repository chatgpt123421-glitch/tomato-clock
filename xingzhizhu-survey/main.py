from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Dict, Any
import json
import os

app = FastAPI(title="幸之住需求洞察系统")

app.mount("/static", StaticFiles(directory="static"), name="static")

FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")
BASE_URL = os.getenv("BASE_URL", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_PATH = "survey.db"


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
                report TEXT
            )
            """
        )
        for col in ["living", "entryway", "kids", "study", "balcony", "laundry", "storage", "learning", "fitness", "entertainment", "environment", "special"]:
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
                report TEXT
            )
            """
        )
        for col in ["living", "entryway", "kids", "study", "balcony", "laundry", "storage", "learning", "fitness", "entertainment", "environment", "special"]:
            try:
                c.execute(f'ALTER TABLE surveys ADD COLUMN {col} TEXT')
            except Exception:
                pass
        conn.commit()
        conn.close()


init_db()


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/submit")
async def submit_survey(request: Request):
    data = await request.json()

    for field in ["basic", "kitchen", "bathroom", "sleep", "laundry", "storage", "learning", "fitness", "entertainment", "environment", "special", "report"]:
        if field not in data:
            return JSONResponse(
                {"code": 400, "message": f"缺少字段: {field}"}, status_code=400
            )

    basic_json = json.dumps(data["basic"], ensure_ascii=False)
    kitchen_json = json.dumps(data["kitchen"], ensure_ascii=False)
    bathroom_json = json.dumps(data["bathroom"], ensure_ascii=False)
    sleep_json = json.dumps(data["sleep"], ensure_ascii=False)
    laundry_json = json.dumps(data["laundry"], ensure_ascii=False)
    storage_json = json.dumps(data["storage"], ensure_ascii=False)
    learning_json = json.dumps(data["learning"], ensure_ascii=False)
    fitness_json = json.dumps(data["fitness"], ensure_ascii=False)
    entertainment_json = json.dumps(data["entertainment"], ensure_ascii=False)
    environment_json = json.dumps(data["environment"], ensure_ascii=False)
    special_json = json.dumps(data["special"], ensure_ascii=False)
    report_json = json.dumps(data["report"], ensure_ascii=False)

    if DATABASE_URL:
        conn = _pg_conn()
        result = conn.run(
            """
            INSERT INTO surveys (basic, kitchen, bathroom, sleep, laundry, storage, learning, fitness, entertainment, environment, special, report)
            VALUES (:basic, :kitchen, :bathroom, :sleep, :laundry, :storage, :learning, :fitness, :entertainment, :environment, :special, :report)
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
        )
        survey_id = result[0][0]
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO surveys (basic, kitchen, bathroom, sleep, laundry, storage, learning, fitness, entertainment, environment, special, report)
            VALUES (:basic, :kitchen, :bathroom, :sleep, :laundry, :storage, :learning, :fitness, :entertainment, :environment, :special, :report)
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
            },
        )
        survey_id = c.fetchone()[0]
        conn.commit()
        conn.close()

    if FEISHU_WEBHOOK:
        try:
            send_feishu(survey_id, data["basic"], data["report"])
        except Exception as e:
            print(f"飞书推送失败: {e}")

    return {"code": 0, "id": survey_id, "message": "提交成功"}


@app.get("/api/surveys")
async def list_surveys():
    if DATABASE_URL:
        conn = _pg_conn()
        rows = conn.run(
            """
            SELECT id, to_char(created_at, 'YYYY-MM-DD HH24:MI:SS'), basic, report
            FROM surveys ORDER BY id DESC
            """
        )
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT id, created_at, basic, report FROM surveys ORDER BY id DESC"
        )
        rows = c.fetchall()
        conn.close()

    result = []
    for row in rows:
        basic = json.loads(row[2] or "{}")
        report = json.loads(row[3] or "{}")
        result.append(
            {
                "id": row[0],
                "created_at": str(row[1]),
                "name": basic.get("name", "-"),
                "people": basic.get("people", "-"),
                "area": basic.get("area", "-"),
                "budget": basic.get("budget", "-"),
                "core_scenes": ", ".join(report.get("scenes", {}).get("core", [])),
            }
        )
    return result


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


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
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
            table { width: 100%; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
            th, td { padding: 14px 16px; text-align: left; border-bottom: 1px solid #f0f0f0; }
            th { background: #fafafa; font-weight: 600; font-size: 14px; color: #666; }
            td { font-size: 14px; }
            tr:hover { background: #fafafa; }
            a { color: #0071e3; text-decoration: none; }
            .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; background: #ffe5e5; color: #d32f2f; }
            @media (max-width: 640px) {
                body { padding: 20px 12px; }
                table { font-size: 12px; }
                th, td { padding: 10px 8px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>问卷列表</h1>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>提交时间</th>
                        <th>客户姓名</th>
                        <th>人口</th>
                        <th>面积</th>
                        <th>预算</th>
                        <th>核心场景</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody id="list"></tbody>
            </table>
        </div>
        <script>
            fetch('/api/surveys')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('list');
                    tbody.innerHTML = data.map(item => `
                        <tr>
                            <td>#${item.id}</td>
                            <td>${item.created_at}</td>
                            <td>${item.name}</td>
                            <td>${item.people}人</td>
                            <td>${item.area}</td>
                            <td>${item.budget}</td>
                            <td>${item.core_scenes ? '<span class="tag">' + item.core_scenes + '</span>' : '-'}</td>
                            <td><a href="/report/${item.id}" target="_blank">查看报告</a></td>
                        </tr>
                    `).join('');
                });
        </script>
    </body>
    </html>
    """


@app.get("/report/{survey_id}", response_class=HTMLResponse)
async def report_page(survey_id: int):
    return f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>需求画像报告 #{survey_id}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f5f5f7; padding: 40px 20px; }}
            .container {{ max-width: 720px; margin: 0 auto; }}
            .report {{ background: #fff; border-radius: 16px; padding: 40px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }}
            .report-header {{ text-align: center; margin-bottom: 40px; padding-bottom: 30px; border-bottom: 2px solid #f5f5f7; }}
            .report-header h2 {{ font-size: 28px; margin-bottom: 8px; }}
            .report-section {{ margin-bottom: 32px; }}
            .report-section h3 {{ font-size: 18px; font-weight: 700; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }}
            .report-section h3::before {{ content: ""; display: inline-block; width: 4px; height: 20px; background: #0071e3; border-radius: 2px; }}
            .report-table {{ width: 100%; border-collapse: collapse; }}
            .report-table td {{ padding: 12px 0; border-bottom: 1px solid #f5f5f7; }}
            .report-table td:first-child {{ width: 30%; color: #86868b; font-weight: 500; }}
            .tag {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; margin-right: 6px; margin-bottom: 6px; }}
            .tag-red {{ background: #ffe5e5; color: #d32f2f; }}
            .tag-yellow {{ background: #fff8e1; color: #f9a825; }}
            .tag-gray {{ background: #f5f5f5; color: #757575; }}
            .tag-blue {{ background: #e3f2fd; color: #1976d2; }}
            .pain-item {{ background: #fff8f0; border-left: 3px solid #ff9800; padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 10px; }}
            .pain-scene {{ font-weight: 700; font-size: 14px; color: #e65100; margin-bottom: 4px; }}
            .pain-text {{ font-size: 15px; color: #424242; }}
            .btn {{ display: inline-block; padding: 12px 24px; background: #0071e3; color: #fff; border: none; border-radius: 10px; font-size: 14px; cursor: pointer; margin-top: 20px; }}
            @media print {{ body {{ background: #fff; }} .container {{ padding: 0; }} .btn {{ display: none; }} }}
            @media (max-width: 640px) {{ .container {{ padding: 0; }} .report {{ padding: 24px; }} }}
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
            fetch('/api/surveys/{survey_id}')
                .then(r => r.json())
                .then(d => {{
                    const r = d.report;
                    const b = d.basic;
                    document.getElementById('reportContent').innerHTML = `
                        <div class="report-header">
                            <h2>需求画像报告</h2>
                            <p style="color:#86868b; margin-top:8px;">编号 #${{d.id}} · ${{d.created_at}}</p>
                        </div>
                        <div class="report-section">
                            <h3>基础锚点</h3>
                            <table class="report-table">
                                <tr><td>客户姓名</td><td>${{b.name || '-'}}</td></tr>
                                <tr><td>手机号</td><td>${{b.phone || '-'}}</td></tr>
                                <tr><td>常住人口</td><td>${{b.people || '-'}} 人</td></tr>
                                <tr><td>人口结构</td><td>${{(b.structure || []).join('、') || '-'}}</td></tr>
                                <tr><td>房屋面积</td><td>${{b.area || '-'}}</td></tr>
                                <tr><td>装修类型</td><td>${{b.type || '-'}}</td></tr>
                                <tr><td>预算区间</td><td>${{b.budget || '-'}}</td></tr>
                            </table>
                        </div>
                        <div class="report-section">
                            <h3>场景分级</h3>
                            <div style="margin-bottom:12px;">
                                <span class="tag tag-red">核心场景</span>
                                <span>${{r.scenes.core.join('、') || '无'}}</span>
                            </div>
                            <div style="margin-bottom:12px;">
                                <span class="tag tag-yellow">次要场景</span>
                                <span>${{r.scenes.minor.join('、') || '无'}}</span>
                            </div>
                            <div>
                                <span class="tag tag-gray">暂无需求</span>
                                <span>${{r.scenes.none.join('、') || '无'}}</span>
                            </div>
                        </div>
                        <div class="report-section">
                            <h3>痛点清单</h3>
                            ${{r.pains.length ? r.pains.map(p => `
                                <div class="pain-item">
                                    <div class="pain-scene">${{p.scene}}</div>
                                    <div class="pain-text">${{p.text}}</div>
                                </div>
                            `).join('') : '<p style="color:#86868b;">暂无明确痛点</p>'}}
                        </div>
                        <div class="report-section">
                            <h3>设计参数</h3>
                            <table class="report-table">
                                ${{r.params.length ? r.params.map(p => `
                                    <tr><td>${{p.scene}}</td><td>${{p.item}} <span class="tag ${{p.level==='必须有'?'tag-red':p.level==='最好有'?'tag-yellow':'tag-gray'}}">${{p.level}}</span></td></tr>
                                `).join('') : '<tr><td colspan="2" style="color:#86868b;">暂无</td></tr>'}}
                            </table>
                        </div>
                        <div class="report-section">
                            <h3>特殊约束</h3>
                            ${{r.constraints.length ? r.constraints.map(c => `
                                <div style="margin-bottom:10px; padding:12px; background:#fff3f3; border-radius:8px; border-left:3px solid #d32f2f;">
                                    <strong>${{c.type}}</strong>：${{c.desc}}
                                </div>
                            `).join('') : '<p style="color:#86868b;">暂无</p>'}}
                        </div>
                        <div class="report-section">
                            <h3>种草待确认</h3>
                            ${{r.seeds.length ? r.seeds.map(s => `
                                <div style="margin-bottom:10px; padding:12px; background:#f0f7ff; border-radius:8px; border-left:3px solid #1976d2;">
                                    <strong>${{s.item}}</strong>：${{s.reason}}
                                </div>
                            `).join('') : '<p style="color:#86868b;">暂无</p>'}}
                        </div>
                    `;
                }});
        </script>
    </body>
    </html>
    """


# ========== 飞书推送 ==========
def send_feishu(survey_id: int, basic: Dict[str, Any], report: Dict[str, Any]):
    """推送结构化报告到飞书群/机器人"""
    if not FEISHU_WEBHOOK:
        return

    scenes = report.get("scenes", {})
    pains = report.get("pains", [])
    params = report.get("params", [])
    client_name = basic.get("name", "未知客户")
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
