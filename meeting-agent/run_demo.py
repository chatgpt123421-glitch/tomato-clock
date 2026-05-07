#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会议统筹智能体 - 自动演示脚本
直接运行看效果，无需任何输入
"""

from meeting_simple import MeetingCoordinator, print_banner
from datetime import datetime

def auto_demo():
    """全自动演示"""
    coordinator = MeetingCoordinator()

    print_banner()
    print("\n🎬 自动演示模式 - 展示所有功能\n")
    print("=" * 60)

    # 1. 创建会议
    print("\n【步骤1】创建会议...")
    meeting = coordinator.create_meeting(
        title="Q2产品规划会议",
        description="讨论Q2季度产品发展方向、关键功能和资源分配",
        duration=90
    )
    print(f"✅ 创建成功: {meeting.title}")
    print(f"   描述: {meeting.description}")
    print(f"   时长: {meeting.duration_minutes}分钟")

    # 2. 添加参会人
    print("\n【步骤2】添加参会人员...")
    participants = [
        ("张经理", "产品总监", "zhang@company.com"),
        ("李工程师", "技术负责人", "li@company.com"),
        ("王设计师", "UX设计师", "wang@company.com"),
        ("刘运营", "运营经理", "liu@company.com"),
        ("陈测试", "测试主管", "chen@company.com")
    ]
    for name, role, email in participants:
        coordinator.add_participant(meeting.title, name, role, email)
        print(f"   ✓ {name} ({role})")
    print(f"✅ 共添加 {len(participants)} 位参会人员")

    # 3. 生成议程
    print("\n【步骤3】生成会议议程...")
    agenda = coordinator.generate_agenda(meeting.title)
    print("✅ 议程生成完成:\n")
    for item in agenda:
        print(f"   {item}")

    # 4. 推荐时间
    print("\n【步骤4】分析最佳会议时间...")
    schedule = coordinator.analyze_schedule(meeting.title)
    print("✅ 时间分析完成:\n")
    print("   推荐时间:")
    for t in schedule['recommended_times']:
        print(f"      • {t}")
    print(f"\n   💡 {schedule['rationale']}")

    # 5. 整理纪要
    print("\n【步骤5】整理会议纪要...")
    sample_transcript = """
    张经理: 大家好，今天我们讨论Q2产品规划。首先请李工汇报Q1技术成果。
    李工程师: Q1我们完成了技术架构升级，系统性能提升30%，稳定性达到99.9%。
    王设计师: 我这边新版UI设计已完成初稿，采用了全新的交互流程，需要大家评审。
    刘运营: 根据用户反馈，用户增长是我们当前最大的痛点，建议Q2重点投入。
    张经理: 同意。Q2我们的核心目标是用户增长。李工，技术方面有什么建议？
    李工程师: 我建议优先开发个性化推荐算法，这个对提升用户留存很有帮助。
    王设计师: 我会配合设计推荐页面的交互，预计需要2周时间。
    陈测试: 测试资源方面，我建议引入自动化测试，提高迭代效率。
    张经理: 好，就这么定了。刘运营负责整理需求文档，李工负责技术方案，
           王设计师负责UI设计，下周三前我们过方案。陈测试开始准备测试计划。
    """
    summary = coordinator.summarize_meeting(meeting.title, sample_transcript)
    print("✅ 纪要整理完成:\n")
    print(f"   📌 摘要: {summary['summary']}")
    print("\n   📌 关键要点:")
    for point in summary['key_points'][:3]:
        print(f"      {point}")
    print("\n   📌 行动项:")
    for item in summary['action_items']:
        print(f"      • {item['task']}")
        print(f"        负责人:{item['owner']} | 截止:{item['deadline']}")

    # 6. 导出文档
    print("\n【步骤6】导出会议文档...")
    content = coordinator.export_meeting(meeting.title, "txt")
    filename = f"会议_{meeting.title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ 文档已导出: {filename}")
    except:
        print("⚠️  文件导出失败，以下是文档内容预览:")
        print("─" * 60)
        print(content[:1000] + "...")

    # 7. 会议列表
    print("\n【步骤7】会议列表...")
    meetings = coordinator.list_meetings()
    print(f"✅ 当前共有 {len(meetings)} 个会议:")
    for m in meetings:
        info = coordinator.get_meeting_info(m)
        print(f"   • {m} (参会人:{len(info['participants'])}, 议程:{len(info['agenda']) if info['agenda'] else 0})")

    print("\n" + "=" * 60)
    print("🎉 演示完成！")
    print("=" * 60)
    print("\n💡 提示:")
    print("   • 运行 meeting_simple.py 进入交互模式")
    print("   • 双击'启动会议智能体.bat'快速启动")
    print("   • 查看'使用说明.md'了解详细功能")
    print()

if __name__ == "__main__":
    auto_demo()
