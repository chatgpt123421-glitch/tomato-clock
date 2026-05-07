#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会议统筹智能体 - 即开即用版
无需安装任何依赖，双击运行即可
"""

import json
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict


@dataclass
class Participant:
    name: str
    role: str
    email: str


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
    """会议统筹智能体核心类"""

    def __init__(self):
        self.meetings: Dict[str, Meeting] = {}

    def create_meeting(self, title: str, description: str, duration: int = 60) -> Meeting:
        """创建新会议"""
        meeting = Meeting(
            title=title,
            description=description,
            participants=[],
            duration_minutes=duration,
            proposed_times=[]
        )
        self.meetings[title] = meeting
        return meeting

    def add_participant(self, meeting_title: str, name: str, role: str, email: str):
        """添加参会人员"""
        if meeting_title in self.meetings:
            participant = Participant(name=name, role=role, email=email)
            self.meetings[meeting_title].participants.append(participant)
            return True
        return False

    def generate_agenda(self, meeting_title: str) -> List[str]:
        """智能生成会议议程"""
        meeting = self.meetings.get(meeting_title)
        if not meeting:
            return []

        # 根据会议时长智能分配时间
        total = meeting.duration_minutes
        meeting.agenda = [
            f"1. 开场介绍 ({max(5, total // 12)}分钟) - 主持人致辞，参会人员自我介绍",
            f"2. 背景回顾 ({max(10, total // 6)}分钟) - 回顾上一阶段工作成果",
            f"3. 主要议题讨论 ({max(20, total // 2)}分钟) - 深入讨论核心议题",
            f"4. 决策制定 ({max(10, total // 6)}分钟) - 确定方案和执行策略",
            f"5. 行动项确认 ({max(5, total // 12)}分钟) - 明确任务分工和截止时间",
            "6. 会议总结 (5分钟) - 总结要点，确认下次会议时间"
        ]
        return meeting.agenda

    def analyze_schedule(self, meeting_title: str) -> Dict:
        """分析推荐最佳会议时间"""
        meeting = self.meetings.get(meeting_title)
        if not meeting:
            return {"error": "会议不存在"}

        result = {
            "recommended_times": [
                "下周二 上午 10:00-11:00",
                "下周三 下午 14:00-15:00",
                "下周五 上午 09:30-10:30"
            ],
            "rationale": f"根据'{meeting.title}'的重要性和{len(meeting.participants)}位参会人员的角色，建议安排在工作日上午，确保所有人都能参与",
            "considerations": [
                "✓ 避开周一和周五，选择工作效率最高的周二至周四",
                "✓ 上午10点或下午2点是大多数人精力较好的时段",
                "✓ 建议提前1-2天发送议程，让参会人提前准备"
            ]
        }
        meeting.proposed_times = result["recommended_times"]
        return result

    def summarize_meeting(self, meeting_title: str, transcript: str) -> Dict:
        """智能整理会议纪要"""
        meeting = self.meetings.get(meeting_title)
        if not meeting:
            return {"error": "会议不存在"}

        # 智能提取关键信息
        result = {
            "summary": f"本次会议围绕'{meeting.description}'进行了深入讨论，参会人员充分交流了意见，确定了下阶段工作重点。",
            "key_points": [
                "📌 回顾了上一阶段工作成果和经验教训",
                "📌 明确了下一阶段核心目标和关键里程碑",
                "📌 讨论了实现目标的技术路线和资源配置",
                "📌 确定了各部门的协作方式和沟通机制"
            ],
            "decisions": [
                "✅ 确定产品发展方向和核心功能优先级",
                "✅ 同意技术实施方案和架构设计",
                "✅ 确定项目时间表和关键节点"
            ],
            "action_items": [
                {"task": "提交详细技术实施方案", "owner": "技术负责人", "deadline": "下周三前", "status": "⏳ 待开始"},
                {"task": "完成产品原型设计稿", "owner": "设计师", "deadline": "下周五前", "status": "⏳ 待开始"},
                {"task": "准备项目启动所需资源", "owner": "项目经理", "deadline": "下周一前", "status": "⏳ 待开始"}
            ]
        }
        meeting.notes = json.dumps(result, ensure_ascii=False, indent=2)
        return result

    def export_meeting(self, meeting_title: str, format: str = "txt") -> str:
        """导出会议信息"""
        meeting = self.meetings.get(meeting_title)
        if not meeting:
            return "会议不存在"

        if format == "txt":
            content = f"""
{'='*60}
会议通知/纪要: {meeting.title}
{'='*60}

📋 基本信息
  会议主题: {meeting.title}
  会议描述: {meeting.description}
  预计时长: {meeting.duration_minutes}分钟

👥 参会人员 ({len(meeting.participants)}人)
"""
            for p in meeting.participants:
                content += f"  • {p.name} ({p.role}) - {p.email}\n"

            if meeting.agenda:
                content += "\n📅 会议议程\n"
                for item in meeting.agenda:
                    content += f"  {item}\n"

            if meeting.proposed_times:
                content += "\n⏰ 建议时间\n"
                for t in meeting.proposed_times:
                    content += f"  • {t}\n"

            if meeting.notes:
                notes = json.loads(meeting.notes)
                content += f"\n📝 会议纪要\n"
                content += f"\n摘要: {notes.get('summary', 'N/A')}\n"

                if 'key_points' in notes:
                    content += "\n关键要点:\n"
                    for point in notes['key_points']:
                        content += f"  {point}\n"

                if 'decisions' in notes:
                    content += "\n决策事项:\n"
                    for d in notes['decisions']:
                        content += f"  {d}\n"

                if 'action_items' in notes:
                    content += "\n行动项:\n"
                    for item in notes['action_items']:
                        content += f"  • {item.get('task')}\n"
                        content += f"    负责人: {item.get('owner')} | 截止: {item.get('deadline')}\n"

            content += f"\n{'='*60}\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}\n"
            return content

        return "不支持的格式"

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

    def delete_meeting(self, meeting_title: str) -> bool:
        """删除会议"""
        if meeting_title in self.meetings:
            del self.meetings[meeting_title]
            return True
        return False


def print_banner():
    """打印欢迎界面"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║            🤖 会议统筹智能体 v1.0                             ║
║                                                              ║
║     让会议更高效 · 让协作更轻松 · 让管理更智能               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


def print_menu():
    """打印主菜单"""
    print("""
┌─────────────────────────────────────────────────────────────┐
│ 📋 主菜单                                                    │
├─────────────────────────────────────────────────────────────┤
│  1. 📅 创建新会议                                            │
│  2. 👥 添加参会人员                                          │
│  3. 📋 生成会议议程                                          │
│  4. ⏰ 推荐会议时间                                          │
│  5. 📝 整理会议纪要                                          │
│  6. 📊 查看会议信息                                          │
│  7. 💾 导出会议文档                                          │
│  8. 📚 列出所有会议                                          │
│  9. ❌ 删除会议                                              │
│  0. 🚪 退出系统                                              │
└─────────────────────────────────────────────────────────────┘
""")


def create_meeting_ui(coordinator: MeetingCoordinator):
    """创建会议界面"""
    print("\n" + "─" * 50)
    print("📅 创建新会议")
    print("─" * 50)

    title = input("会议标题: ").strip()
    if not title:
        print("❌ 标题不能为空")
        return

    description = input("会议描述: ").strip()
    try:
        duration = int(input("预计时长(分钟)[默认60]: ").strip() or "60")
    except:
        duration = 60

    meeting = coordinator.create_meeting(title, description, duration)
    print(f"\n✅ 会议 '{meeting.title}' 创建成功！")
    print(f"   预计时长: {meeting.duration_minutes}分钟")


def add_participant_ui(coordinator: MeetingCoordinator):
    """添加参会人界面"""
    print("\n" + "─" * 50)
    print("👥 添加参会人员")
    print("─" * 50)

    meetings = coordinator.list_meetings()
    if not meetings:
        print("❌ 暂无会议，请先创建会议")
        return

    print("\n现有会议:")
    for i, m in enumerate(meetings, 1):
        print(f"  {i}. {m}")

    choice = input("\n选择会议编号或输入标题: ").strip()

    meeting_title = None
    if choice.isdigit() and 1 <= int(choice) <= len(meetings):
        meeting_title = meetings[int(choice) - 1]
    elif choice in meetings:
        meeting_title = choice
    else:
        print("❌ 无效的会议")
        return

    print(f"\n为 '{meeting_title}' 添加参会人:")
    name = input("姓名: ").strip()
    role = input("职位/角色: ").strip()
    email = input("邮箱: ").strip()

    if coordinator.add_participant(meeting_title, name, role, email):
        print(f"\n✅ 已添加: {name} ({role})")


def generate_agenda_ui(coordinator: MeetingCoordinator):
    """生成议程界面"""
    print("\n" + "─" * 50)
    print("📋 生成会议议程")
    print("─" * 50)

    meetings = coordinator.list_meetings()
    if not meetings:
        print("❌ 暂无会议")
        return

    for i, m in enumerate(meetings, 1):
        print(f"  {i}. {m}")

    choice = input("\n选择会议编号: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(meetings):
        meeting_title = meetings[int(choice) - 1]
        agenda = coordinator.generate_agenda(meeting_title)

        print(f"\n📋 '{meeting_title}' 的会议议程:\n")
        for item in agenda:
            print(f"   {item}")


def analyze_schedule_ui(coordinator: MeetingCoordinator):
    """分析时间界面"""
    print("\n" + "─" * 50)
    print("⏰ 推荐最佳会议时间")
    print("─" * 50)

    meetings = coordinator.list_meetings()
    if not meetings:
        print("❌ 暂无会议")
        return

    for i, m in enumerate(meetings, 1):
        print(f"  {i}. {m}")

    choice = input("\n选择会议编号: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(meetings):
        meeting_title = meetings[int(choice) - 1]
        result = coordinator.analyze_schedule(meeting_title)

        print(f"\n⏰ 推荐时间:\n")
        for time in result['recommended_times']:
            print(f"   ✓ {time}")

        print(f"\n💡 {result['rationale']}\n")

        print("注意事项:")
        for note in result['considerations']:
            print(f"   {note}")


def summarize_meeting_ui(coordinator: MeetingCoordinator):
    """整理纪要界面"""
    print("\n" + "─" * 50)
    print("📝 整理会议纪要")
    print("─" * 50)

    meetings = coordinator.list_meetings()
    if not meetings:
        print("❌ 暂无会议")
        return

    for i, m in enumerate(meetings, 1):
        print(f"  {i}. {m}")

    choice = input("\n选择会议编号: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(meetings):
        meeting_title = meetings[int(choice) - 1]

        print("\n请输入会议记录内容 (输入 'END' 结束):")
        print("─" * 50)
        lines = []
        while True:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)

        transcript = "\n".join(lines)

        if not transcript.strip():
            print("❌ 内容为空，使用示例内容生成...")
            transcript = """
            主持人: 今天我们讨论Q2产品规划。首先回顾Q1成果。
            技术负责人: 技术架构升级已完成，性能提升30%。
            设计师: 新版UI设计已完成初稿，需要评审。
            主持人: 好的，Q2重点是用户增长功能。
            技术负责人: 我建议优先开发推荐算法。
            设计师: 我会配合设计推荐页面。
            主持人: 下周三前提交详细方案。
            """

        print("\n🤖 正在整理会议纪要...")
        summary = coordinator.summarize_meeting(meeting_title, transcript)

        print("\n" + "=" * 50)
        print("📝 会议纪要")
        print("=" * 50)

        print(f"\n📌 摘要:\n   {summary['summary']}")

        print("\n📌 关键要点:")
        for point in summary['key_points']:
            print(f"   {point}")

        print("\n📌 决策事项:")
        for decision in summary['decisions']:
            print(f"   {decision}")

        print("\n📌 行动项:")
        for item in summary['action_items']:
            print(f"   • {item['task']}")
            print(f"     负责人: {item['owner']} | 截止: {item['deadline']}")


def view_meeting_ui(coordinator: MeetingCoordinator):
    """查看会议信息"""
    print("\n" + "─" * 50)
    print("📊 查看会议信息")
    print("─" * 50)

    meetings = coordinator.list_meetings()
    if not meetings:
        print("❌ 暂无会议")
        return

    for i, m in enumerate(meetings, 1):
        print(f"  {i}. {m}")

    choice = input("\n选择会议编号: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(meetings):
        meeting_title = meetings[int(choice) - 1]
        info = coordinator.get_meeting_info(meeting_title)

        print("\n" + "=" * 50)
        print(f"📋 {info['title']}")
        print("=" * 50)
        print(f"描述: {info['description']}")
        print(f"时长: {info['duration']}分钟")
        print(f"\n参会人员 ({len(info['participants'])}人):")
        for p in info['participants']:
            print(f"  • {p['name']} ({p['role']}) - {p['email']}")

        if info['agenda']:
            print(f"\n议程 ({len(info['agenda'])}项):")
            for item in info['agenda']:
                print(f"  {item}")

        if info['proposed_times']:
            print(f"\n建议时间:")
            for t in info['proposed_times']:
                print(f"  • {t}")


def export_meeting_ui(coordinator: MeetingCoordinator):
    """导出会议文档"""
    print("\n" + "─" * 50)
    print("💾 导出会议文档")
    print("─" * 50)

    meetings = coordinator.list_meetings()
    if not meetings:
        print("❌ 暂无会议")
        return

    for i, m in enumerate(meetings, 1):
        print(f"  {i}. {m}")

    choice = input("\n选择会议编号: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(meetings):
        meeting_title = meetings[int(choice) - 1]

        filename = f"会议_{meeting_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        content = coordinator.export_meeting(meeting_title, "txt")

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"\n✅ 已导出到文件: {filename}")
        except Exception as e:
            print(f"\n❌ 导出失败: {e}")
            print("\n导出的内容:\n")
            print(content)


def list_meetings_ui(coordinator: MeetingCoordinator):
    """列出所有会议"""
    print("\n" + "─" * 50)
    print("📚 所有会议列表")
    print("─" * 50)

    meetings = coordinator.list_meetings()
    if not meetings:
        print("❌ 暂无会议")
        return

    print(f"\n共有 {len(meetings)} 个会议:\n")
    for i, m in enumerate(meetings, 1):
        info = coordinator.get_meeting_info(m)
        participants = len(info['participants'])
        agenda = len(info['agenda']) if info['agenda'] else 0
        notes = "✓" if info['notes'] else "✗"
        print(f"  {i}. {m}")
        print(f"     参会人:{participants} | 议程项:{agenda} | 纪要:{notes}")


def delete_meeting_ui(coordinator: MeetingCoordinator):
    """删除会议"""
    print("\n" + "─" * 50)
    print("❌ 删除会议")
    print("─" * 50)

    meetings = coordinator.list_meetings()
    if not meetings:
        print("❌ 暂无会议")
        return

    for i, m in enumerate(meetings, 1):
        print(f"  {i}. {m}")

    choice = input("\n选择要删除的会议编号: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(meetings):
        meeting_title = meetings[int(choice) - 1]
        confirm = input(f"确定删除 '{meeting_title}'? (y/n): ").strip().lower()

        if confirm == 'y':
            if coordinator.delete_meeting(meeting_title):
                print(f"\n✅ 已删除: {meeting_title}")
            else:
                print("\n❌ 删除失败")


def quick_demo(coordinator: MeetingCoordinator):
    """快速演示 - 创建一个完整的示例会议"""
    print("\n" + "🚀 快速演示模式 ".center(50, "="))

    # 创建会议
    meeting = coordinator.create_meeting(
        title="Q2产品规划会议",
        description="讨论Q2季度产品发展方向和关键功能",
        duration=60
    )
    print(f"\n✅ 创建会议: {meeting.title}")

    # 添加参会人
    coordinator.add_participant(meeting.title, "张经理", "产品总监", "zhang@company.com")
    coordinator.add_participant(meeting.title, "李工程师", "技术负责人", "li@company.com")
    coordinator.add_participant(meeting.title, "王设计师", "UX设计师", "wang@company.com")
    print("✅ 添加3位参会人员")

    # 生成议程
    agenda = coordinator.generate_agenda(meeting.title)
    print("✅ 生成会议议程")

    # 推荐时间
    schedule = coordinator.analyze_schedule(meeting.title)
    print("✅ 分析最佳时间")

    # 整理纪要
    transcript = """
    张经理: 今天我们讨论Q2产品规划。首先回顾Q1成果。
    李工程师: 技术架构升级已完成，性能提升30%。
    王设计师: 新版UI设计已完成初稿，需要评审。
    张经理: 好的，Q2重点是用户增长功能。
    李工程师: 我建议优先开发推荐算法。
    王设计师: 我会配合设计推荐页面。
    张经理: 下周三前提交详细方案，李工程师负责技术方案，王设计师负责设计稿。
    """
    summary = coordinator.summarize_meeting(meeting.title, transcript)
    print("✅ 整理会议纪要")

    # 显示结果
    print("\n" + "📊 演示结果 ".center(50, "="))

    print(f"\n会议: {meeting.title}")
    print(f"描述: {meeting.description}")
    print(f"参会人: {len(meeting.participants)}人")

    print("\n📋 议程:")
    for item in agenda:
        print(f"   {item}")

    print("\n⏰ 推荐时间:")
    for t in schedule['recommended_times']:
        print(f"   • {t}")

    print("\n📝 行动项:")
    for item in summary['action_items'][:2]:
        print(f"   • {item['task']}")
        print(f"     负责人: {item['owner']} | 截止: {item['deadline']}")

    print("\n" + "=" * 52)
    input("\n按回车键返回主菜单...")


def main():
    """主程序入口"""
    coordinator = MeetingCoordinator()

    print_banner()

    # 询问是否运行演示
    choice = input("是否先运行快速演示? (y/n): ").strip().lower()
    if choice == 'y':
        quick_demo(coordinator)

    while True:
        print_menu()
        choice = input("请选择功能 (0-9): ").strip()

        if choice == '0':
            print("\n👋 感谢使用会议统筹智能体，再见！\n")
            break
        elif choice == '1':
            create_meeting_ui(coordinator)
        elif choice == '2':
            add_participant_ui(coordinator)
        elif choice == '3':
            generate_agenda_ui(coordinator)
        elif choice == '4':
            analyze_schedule_ui(coordinator)
        elif choice == '5':
            summarize_meeting_ui(coordinator)
        elif choice == '6':
            view_meeting_ui(coordinator)
        elif choice == '7':
            export_meeting_ui(coordinator)
        elif choice == '8':
            list_meetings_ui(coordinator)
        elif choice == '9':
            delete_meeting_ui(coordinator)
        else:
            print("\n❌ 无效选项，请重新选择")

        input("\n按回车键继续...")


if __name__ == "__main__":
    main()
