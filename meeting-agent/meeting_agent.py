"""
会议统筹智能体 - 帮助管理会议全流程
"""
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from anthropic import Anthropic


@dataclass
class Participant:
    name: str
    role: str
    email: str
    time_preferences: List[str] = None


@dataclass
class Meeting:
    title: str
    description: str
    participants: List[Participant]
    duration_minutes: int
    proposed_times: List[str]
    agenda: List[str] = None
    confirmed_time: str = None
    notes: str = None


class MeetingCoordinator:
    def __init__(self, api_key: str = None):
        self.client = Anthropic(api_key=api_key) if api_key else None
        self.meetings: Dict[str, Meeting] = {}

    def create_meeting(self, title: str, description: str) -> Meeting:
        """创建新会议"""
        meeting = Meeting(
            title=title,
            description=description,
            participants=[],
            duration_minutes=60,
            proposed_times=[]
        )
        self.meetings[title] = meeting
        return meeting

    def add_participant(self, meeting_title: str, name: str, role: str, email: str):
        """添加参会人员"""
        if meeting_title in self.meetings:
            participant = Participant(name=name, role=role, email=email)
            self.meetings[meeting_title].participants.append(participant)

    def analyze_schedule(self, meeting_title: str) -> Dict:
        """AI分析最佳会议时间"""
        meeting = self.meetings.get(meeting_title)
        if not meeting:
            return {"error": "会议不存在"}

        # 模拟模式
        if not self.client:
            result = {
                "recommended_times": [
                    "下周二 上午 10:00",
                    "下周三 下午 14:00",
                    "下周五 上午 09:30"
                ],
                "rationale": "根据参会人员的职位和会议重要性，建议安排在工作日上午，确保所有人都能参与",
                "considerations": ["避免周一和周五的会议", "技术负责人下午有例会", "建议提前一天发送议程"]
            }
            meeting.proposed_times = result["recommended_times"]
            return result

        prompt = f"""作为会议统筹专家，请分析以下会议信息并推荐最佳会议时间：

会议标题: {meeting.title}
会议描述: {meeting.description}
预计时长: {meeting.duration_minutes}分钟
参会人员:
"""
        for p in meeting.participants:
            prompt += f"- {p.name} ({p.role})\n"

        prompt += """
请提供以下建议（以JSON格式返回）：
{
    "recommended_times": ["推荐时间1", "推荐时间2", "推荐时间3"],
    "rationale": "推荐理由",
    "considerations": ["需要考虑的因素1", "因素2"]
}
"""
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            result = json.loads(response.content[0].text)
            meeting.proposed_times = result.get("recommended_times", [])
            return result
        except:
            return {"suggestion": response.content[0].text}

    def generate_agenda(self, meeting_title: str) -> List[str]:
        """AI生成会议议程"""
        meeting = self.meetings.get(meeting_title)
        if not meeting:
            return []

        # 模拟模式
        if not self.client:
            meeting.agenda = [
                f"1. 开场介绍 ({max(5, meeting.duration_minutes // 12)}分钟)",
                f"2. 背景回顾 ({max(10, meeting.duration_minutes // 6)}分钟)",
                f"3. 主要议题讨论 ({max(20, meeting.duration_minutes // 2)}分钟)",
                f"4. 决策制定 ({max(10, meeting.duration_minutes // 6)}分钟)",
                f"5. 行动项确认 ({max(5, meeting.duration_minutes // 12)}分钟)",
                "6. 会议总结 (5分钟)"
            ]
            return meeting.agenda

        prompt = f"""请为以下会议生成详细的议程安排：

会议标题: {meeting.title}
会议描述: {meeting.description}
预计时长: {meeting.duration_minutes}分钟
参会人员:
"""
        for p in meeting.participants:
            prompt += f"- {p.name} ({p.role})\n"

        prompt += """
请生成结构化的议程（每项包含预计时间），以JSON格式返回：
{
    "agenda": [
        "1. 开场介绍 (5分钟)",
        "2. 议题讨论 (30分钟)",
        ...
    ]
}
"""
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            result = json.loads(response.content[0].text)
            meeting.agenda = result.get("agenda", [])
            return meeting.agenda
        except:
            meeting.agenda = ["议程生成中..."]
            return meeting.agenda

    def summarize_meeting(self, meeting_title: str, transcript: str) -> Dict:
        """AI整理会议纪要"""
        meeting = self.meetings.get(meeting_title)
        if not meeting:
            return {"error": "会议不存在"}

        # 模拟模式
        if not self.client:
            result = {
                "summary": f"本次会议围绕{meeting.description}进行了深入讨论，确定了下阶段工作重点。",
                "key_points": [
                    "回顾了上一阶段工作成果",
                    "明确了下一阶段核心目标",
                    "讨论了关键技术和设计问题"
                ],
                "decisions": [
                    "确定产品发展方向",
                    "同意技术实施方案"
                ],
                "action_items": [
                    {"task": "提交详细技术方案", "owner": "技术负责人", "deadline": "下周三前"},
                    {"task": "完成设计初稿", "owner": "设计师", "deadline": "下周五前"}
                ]
            }
            meeting.notes = json.dumps(result, ensure_ascii=False, indent=2)
            return result

        prompt = f"""请整理以下会议记录，生成结构化的会议纪要：

会议标题: {meeting.title}
会议记录:
{transcript}

请以JSON格式返回：
{{
    "summary": "会议摘要",
    "key_points": ["要点1", "要点2", ...],
    "action_items": [
        {{"task": "任务描述", "owner": "负责人", "deadline": "截止日期"}}
    ],
    "decisions": ["决策1", "决策2", ...]
}}
"""
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            result = json.loads(response.content[0].text)
            meeting.notes = json.dumps(result, ensure_ascii=False, indent=2)
            return result
        except:
            meeting.notes = response.content[0].text
            return {"notes": response.content[0].text}

    def get_meeting_info(self, meeting_title: str) -> Dict:
        """获取会议信息"""
        meeting = self.meetings.get(meeting_title)
        if not meeting:
            return {"error": "会议不存在"}

        return {
            "title": meeting.title,
            "description": meeting.description,
            "participants": [asdict(p) for p in meeting.participants],
            "duration": meeting.duration_minutes,
            "agenda": meeting.agenda,
            "proposed_times": meeting.proposed_times,
            "confirmed_time": meeting.confirmed_time,
            "notes": meeting.notes
        }

    def list_meetings(self) -> List[str]:
        """列出所有会议"""
        return list(self.meetings.keys())


def demo():
    """演示会议统筹智能体的功能"""
    print("=" * 50)
    print("🤖 会议统筹智能体演示")
    print("=" * 50)

    # 创建会议统筹实例 (使用模拟模式)
    coordinator = MeetingCoordinator(api_key=None)
    print("\n💡 提示: 配置 ANTHROPIC_API_KEY 可启用AI功能")

    # 1. 创建会议
    print("\n📅 创建会议...")
    meeting = coordinator.create_meeting(
        title="Q2产品规划会议",
        description="讨论Q2季度产品发展方向和关键功能"
    )
    print(f"✅ 会议创建成功: {meeting.title}")

    # 2. 添加参会人员
    print("\n👥 添加参会人员...")
    coordinator.add_participant(
        meeting_title="Q2产品规划会议",
        name="张经理",
        role="产品总监",
        email="zhang@company.com"
    )
    coordinator.add_participant(
        meeting_title="Q2产品规划会议",
        name="李工程师",
        role="技术负责人",
        email="li@company.com"
    )
    coordinator.add_participant(
        meeting_title="Q2产品规划会议",
        name="王设计师",
        role="UX设计师",
        email="wang@company.com"
    )
    print("✅ 已添加3位参会人员")

    # 3. 生成议程
    print("\n📋 生成会议议程...")
    agenda = coordinator.generate_agenda("Q2产品规划会议")
    print("会议议程:")
    for item in agenda:
        print(f"  • {item}")

    # 4. 会议信息概览
    print("\n📊 会议信息概览:")
    info = coordinator.get_meeting_info("Q2产品规划会议")
    print(f"  标题: {info['title']}")
    print(f"  描述: {info['description']}")
    print(f"  参会人数: {len(info['participants'])}")
    print(f"  预计时长: {info['duration']}分钟")

    # 5. 模拟会议纪要整理
    print("\n📝 演示会议纪要整理...")
    sample_transcript = """
    张经理: 今天我们讨论Q2产品规划。首先回顾Q1成果。
    李工程师: 技术架构升级已完成，性能提升30%。
    王设计师: 新版UI设计已完成初稿，需要评审。
    张经理: 好的，Q2重点是用户增长功能。
    李工程师: 我建议优先开发推荐算法。
    王设计师: 我会配合设计推荐页面。
    张经理: 下周三前提交详细方案，李工程师负责技术方案，王设计师负责设计稿。
    """

    summary = coordinator.summarize_meeting("Q2产品规划会议", sample_transcript)
    print("\n会议纪要:")
    print(f"摘要: {summary.get('summary', 'N/A')}")
    print("\n关键要点:")
    for point in summary.get('key_points', []):
        print(f"  • {point}")
    print("\n行动项:")
    for item in summary.get('action_items', []):
        print(f"  • {item.get('task')} - 负责人: {item.get('owner')} - 截止: {item.get('deadline')}")

    print("\n" + "=" * 50)
    print("✅ 演示完成！")
    print("=" * 50)


if __name__ == "__main__":
    demo()
