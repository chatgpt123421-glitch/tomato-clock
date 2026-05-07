# 🤖 会议统筹智能体

一个基于 Claude API 的智能会议管理系统，帮助您高效组织会议全流程。

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 📅 **会议创建** | 快速创建会议，设置主题、描述、时长 |
| 👥 **人员管理** | 添加参会人员，记录角色和联系方式 |
| 📋 **议程生成** | AI 自动生成结构化会议议程 |
| ⏰ **时间协调** | 智能分析推荐最佳会议时间 |
| 📝 **纪要整理** | 自动提取要点、决策和行动项 |

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API 密钥

```bash
# Windows
set ANTHROPIC_API_KEY=your-api-key

# Linux/Mac
export ANTHROPIC_API_KEY=your-api-key
```

### 3. 运行方式

#### 命令行交互
```bash
python cli.py
```

#### Web 界面
```bash
streamlit run app.py
```

#### 代码调用
```python
from meeting_agent import MeetingCoordinator

# 初始化
coordinator = MeetingCoordinator(api_key="your-api-key")

# 创建会议
meeting = coordinator.create_meeting(
    title="产品评审会",
    description="讨论Q2新功能规划"
)

# 添加参会人
coordinator.add_participant(
    meeting_title="产品评审会",
    name="张三",
    role="产品经理",
    email="zhangsan@company.com"
)

# 生成议程
agenda = coordinator.generate_agenda("产品评审会")

# 整理会议纪要
summary = coordinator.summarize_meeting(
    meeting_title="产品评审会",
    transcript="会议记录内容..."
)
```

## 📁 项目结构

```
meeting-agent/
├── meeting_agent.py   # 核心智能体类
├── cli.py             # 命令行交互界面
├── app.py             # Web 界面 (Streamlit)
├── requirements.txt   # 依赖配置
└── README.md          # 说明文档
```

## 💡 使用示例

### 场景：组织一次产品规划会议

```python
# 1. 创建会议
coordinator.create_meeting(
    title="Q2产品规划会",
    description="讨论Q2季度产品路线图"
)

# 2. 添加团队成员
coordinator.add_participant("Q2产品规划会", "张经理", "产品总监", "zhang@company.com")
coordinator.add_participant("Q2产品规划会", "李工程师", "技术负责人", "li@company.com")
coordinator.add_participant("Q2产品规划会", "王设计师", "UX设计师", "wang@company.com")

# 3. AI生成议程
agenda = coordinator.generate_agenda("Q2产品规划会")
# 输出：
# 1. 开场介绍 (5分钟)
# 2. Q1回顾 (10分钟)
# 3. Q2目标讨论 (20分钟)
# 4. 功能优先级 (15分钟)
# 5. 行动计划 (10分钟)

# 4. 智能推荐时间
schedule = coordinator.analyze_schedule("Q2产品规划会")
# 输出：周二上午10:00（所有人空闲时间）

# 5. 会后整理纪要
notes = coordinator.summarize_meeting("Q2产品规划会", meeting_transcript)
# 输出：结构化纪要，包含要点、决策、行动项
```

## 🔧 配置说明

### 环境变量

| 变量名 | 说明 | 必需 |
|--------|------|------|
| `ANTHROPIC_API_KEY` | Claude API 密钥 | 是 |

### 获取 API 密钥

1. 访问 [Anthropic Console](https://console.anthropic.com/)
2. 注册/登录账号
3. 在 Settings -> API Keys 中创建新密钥

## 📝 注意事项

- API 调用会产生费用，请合理控制使用频率
- 建议为不同会议创建独立的智能体实例
- 会议记录内容会被发送到 Claude API 处理，请勿包含敏感信息

## 🔒 隐私说明

- 会议数据存储在内存中，程序结束后不保留
- 如需持久化存储，可自行扩展数据保存逻辑
