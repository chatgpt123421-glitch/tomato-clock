"""
会议统筹智能体 - 命令行交互界面
"""
import os
import sys
from meeting_agent import MeetingCoordinator, Participant


def print_header():
    print("=" * 60)
    print("     🤖 会议统筹智能体 - 让会议更高效")
    print("=" * 60)


def print_menu():
    print("\n📋 功能菜单:")
    print("-" * 40)
    print("  1. 创建新会议")
    print("  2. 添加参会人员")
    print("  3. 查看会议信息")
    print("  4. 生成会议议程")
    print("  5. 分析最佳会议时间")
    print("  6. 整理会议纪要")
    print("  7. 列出所有会议")
    print("  0. 退出")
    print("-" * 40)


def main():
    print_header()

    # 获取API密钥
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n⚠️  请设置环境变量 ANTHROPIC_API_KEY")
        print("   示例: export ANTHROPIC_API_KEY='your-api-key'")
        print("\n   您现在可以输入API密钥 (或直接回车使用演示模式):")
        api_key = input("   > ").strip()
        if not api_key:
            print("\n📝 进入演示模式...")

    try:
        coordinator = MeetingCoordinator(api_key=api_key) if api_key else None
    except Exception as e:
        print(f"初始化失败: {e}")
        coordinator = None

    current_meeting = None

    while True:
        print_menu()
        choice = input("\n请选择功能 (0-7): ").strip()

        if choice == "0":
            print("\n👋 再见！")
            break

        elif choice == "1":
            print("\n📅 创建新会议")
            print("-" * 40)
            title = input("会议标题: ").strip()
            description = input("会议描述: ").strip()

            if coordinator:
                meeting = coordinator.create_meeting(title, description)
                current_meeting = title
                print(f"\n✅ 会议 '{title}' 创建成功！")
            else:
                print(f"\n📝 演示模式: 会议 '{title}' 已记录")
                current_meeting = title

        elif choice == "2":
            if not current_meeting:
                current_meeting = input("请输入会议标题: ").strip()

            print(f"\n👥 为 '{current_meeting}' 添加参会人员")
            print("-" * 40)
            name = input("姓名: ").strip()
            role = input("职位/角色: ").strip()
            email = input("邮箱: ").strip()

            if coordinator:
                coordinator.add_participant(current_meeting, name, role, email)
            print(f"\n✅ 已添加参会人员: {name}")

        elif choice == "3":
            title = input("请输入会议标题: ").strip()
            if coordinator and title in coordinator.meetings:
                info = coordinator.get_meeting_info(title)
                print(f"\n📊 会议信息: {info['title']}")
                print(f"描述: {info['description']}")
                print(f"参会人员 ({len(info['participants'])}人):")
                for p in info['participants']:
                    print(f"  • {p['name']} ({p['role']}) - {p['email']}")
                if info['agenda']:
                    print("\n议程:")
                    for item in info['agenda']:
                        print(f"  • {item}")
            else:
                print("会议不存在或处于演示模式")

        elif choice == "4":
            title = input("请输入会议标题: ").strip()
            if coordinator and title in coordinator.meetings:
                print("\n🤖 AI正在生成议程...")
                agenda = coordinator.generate_agenda(title)
                print("\n📋 生成的议程:")
                for item in agenda:
                    print(f"  • {item}")
            else:
                print("\n📝 演示模式 - 示例议程:")
                print("  1. 开场介绍 (5分钟)")
                print("  2. 议题讨论 (30分钟)")
                print("  3. 决策制定 (15分钟)")
                print("  4. 行动项确认 (10分钟)")

        elif choice == "5":
            title = input("请输入会议标题: ").strip()
            if coordinator and title in coordinator.meetings:
                print("\n🤖 AI正在分析最佳会议时间...")
                result = coordinator.analyze_schedule(title)
                print("\n⏰ 推荐时间:")
                for time in result.get('recommended_times', []):
                    print(f"  • {time}")
                print(f"\n推荐理由: {result.get('rationale', 'N/A')}")
            else:
                print("\n📝 演示模式 - 请配置API密钥以使用AI功能")

        elif choice == "6":
            title = input("请输入会议标题: ").strip()
            print("\n请输入会议记录内容 (输入 'END' 结束):")
            lines = []
            while True:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            transcript = "\n".join(lines)

            if coordinator and title in coordinator.meetings:
                print("\n🤖 AI正在整理会议纪要...")
                summary = coordinator.summarize_meeting(title, transcript)
                print("\n📝 会议纪要:")
                print(json.dumps(summary, ensure_ascii=False, indent=2))
            else:
                print("\n📝 演示模式 - 已记录会议内容")
                print(f"内容长度: {len(transcript)} 字符")

        elif choice == "7":
            if coordinator:
                meetings = coordinator.list_meetings()
                if meetings:
                    print("\n📚 所有会议:")
                    for m in meetings:
                        print(f"  • {m}")
                else:
                    print("\n暂无会议记录")
            else:
                print("\n演示模式 - 暂无会议记录")

        else:
            print("\n⚠️ 无效选项，请重新选择")

        input("\n按回车继续...")


if __name__ == "__main__":
    main()
