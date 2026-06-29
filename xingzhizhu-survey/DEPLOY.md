# 幸之住需求洞察系统 · 部署指南

> 目标：1小时内完成从本地测试到线上部署

---

## 一、文件结构

```
xingzhizhu-survey/
├── main.py              # FastAPI后端（API + 管理后台 + 飞书推送）
├── requirements.txt     # Python依赖
├── static/
│   └── index.html       # 前端问卷页面
└── DEPLOY.md            # 本文件
```

---

## 二、本地测试（5分钟）

### 1. 安装依赖

```bash
cd xingzhizhu-survey
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python main.py
```

看到 `Uvicorn running on http://0.0.0.0:8000` 即成功。

### 3. 测试

- 打开浏览器访问 `http://localhost:8000` → 看到问卷页面
- 填完提交 → 看到"提交成功"提示
- 访问 `http://localhost:8000/admin` → 看到问卷列表

---

## 三、飞书机器人配置（10分钟）

这是"填完自动通知设计师"的关键步骤。

### 步骤

1. **打开飞书群**（设计师群或家宝工作群）
2. 点击群设置 → **添加机器人** → **自定义机器人**
3. 给机器人起个名字，如"家宝通知"
4. 复制 **Webhook地址**，格式类似：
   ```
   https://open.feishu.cn/open-apis/bot/v2/hook/xxxx-xxxx
   ```
5. 记住这个地址，下一步要用

### 测试Webhook是否通畅

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"msg_type":"text","content":{"text":"测试消息"}}' \
  https://open.feishu.cn/open-apis/bot/v2/hook/你的地址
```

群里收到"测试消息"即配置成功。

---

## 四、部署到Render（免费，15分钟）

Render是免费的Python托管平台，只需要一个Git仓库。

### 步骤

1. **把代码推送到GitHub**

   当前 `xingzhizhu-survey` 在 `AI桌面` 仓库内，直接在根目录提交并推送：

   ```bash
   # 在 AI桌面 根目录执行
   git add xingzhizhu-survey/
   git commit -m "add survey system"
   git push origin main
   ```

   > 如果没有 GitHub 远程仓库，先创建一个，然后 `git remote add origin https://github.com/你的用户名/你的仓库.git`

2. **登录 [render.com](https://render.com)**
   - 用GitHub账号登录
   - 点击 **New +** → **Web Service**
   - 选择刚才推送的GitHub仓库

3. **配置服务**

   | 字段 | 填写 |
   |------|------|
   | Name | `xingzhizhu-survey` |
   | Runtime | `Python 3` |
   | Build Command | `cd xingzhizhu-survey && pip install -r requirements.txt` |
   | Start Command | `cd xingzhizhu-survey && python main.py` |
   | Plan | Free |

4. **添加环境变量**
   - 点击 **Environment** → **Add Environment Variable**
   - Key: `FEISHU_WEBHOOK`
   - Value: 你刚才复制的飞书Webhook地址
   - 再添加一条：
     - Key: `BASE_URL`
     - Value: 你的 Render 域名，如 `https://xingzhizhu-survey.onrender.com`（**不带尾部斜杠**）
   - 如使用线上数据库，再添加：
     - Key: `DATABASE_URL`
     - Value: PostgreSQL 连接地址
   - 建议再添加后台密码：
     - Key: `ADMIN_PASSWORD`
     - Value: 自行设置一串不容易猜到的密码

本地调试可参考 `.env.example`，但真实 `FEISHU_WEBHOOK`、`DATABASE_URL` 和 `ADMIN_PASSWORD` 不要提交到仓库。

5. **点击 Create Web Service**
   - 等待3-5分钟部署完成
   - 获得一个类似 `https://xingzhizhu-survey.onrender.com` 的链接

6. **测试线上版本**
   - 打开链接 → 填问卷 → 提交
   - 检查飞书群是否收到通知
   - 访问 `https://你的链接/admin` 查看后台

---

## 五、家宝发送问卷链接

部署完成后，把链接给家宝：

```
https://xingzhizhu-survey.onrender.com
```

家宝在企业微信里按条件发送此链接给客户。

客户填完 → 自动推送报告到飞书群 → 设计师收到通知 → 点击链接查看完整报告。

---

## 六、管理后台

部署后有两个后台地址：

| 地址 | 用途 |
|------|------|
| `https://你的链接/admin` | 查看所有客户问卷列表 |
| `https://你的链接/api/surveys/export.csv` | 导出客户问卷 CSV 备份 |
| `https://你的链接/report/1` | 查看编号#1的完整报告（可打印） |

如果配置了 `ADMIN_PASSWORD`，访问 `/admin` 时会先进入后台登录页；CSV 导出和客户列表 API 也会被保护。

---

## 七、常见问题

**Q: Render免费版会休眠吗？**
A: 会。15分钟无访问会休眠，下次访问唤醒需要10-30秒。如果客户反应慢，解释"首次加载稍慢"即可。如需持续在线，升级到$7/月。

**Q: 数据存在哪？会丢吗？**
A: 程序会优先使用 `DATABASE_URL` 指向的 PostgreSQL。未配置 `DATABASE_URL` 时，才回退到本地 SQLite 文件（`survey.db`）。Render 环境不应长期依赖 SQLite，因为重部署或文件系统重置可能造成数据丢失。建议：
- 方案1：配置 PostgreSQL，并在 Render 环境变量中填写 `DATABASE_URL`
- 方案2：短期测试可使用 SQLite，但要定期导出 `/admin` 页面数据备份
- 方案3：如必须使用文件数据库，升级到支持持久磁盘的方案

**Q: 可以绑定自己的域名吗？**
A: 可以。Render支持自定义域名，在Dashboard → Settings → Custom Domains 里配置。

**Q: 飞书通知可以@指定人吗？**
A: 可以。在 `main.py` 的 `send_feishu` 函数里，把 `"tag": "a"` 改成 `"tag": "at"`，并加上 `"user_id": "用户的飞书ID"`。需要知道设计师的飞书user_id。

---

## 八、后续升级建议

当前是MVP（最小可行产品）。跑通后建议按顺序升级：

1. **数据库持久化**：确认线上已配置 PostgreSQL，并把 `DATABASE_URL` 写入 Render 环境变量
2. **客户身份识别**：链接带参数 `?client=张三`，后台知道是谁填的
3. **报告PDF生成**：用Python库自动生成PDF报告，比网页打印更专业
4. **企微直接集成**：客户不用点链接，在企微对话框里直接答题（需要开发企微小程序/网页授权）
5. **AI分析增强**：把报告传给Claude API，让AI自动生成设计方案建议
