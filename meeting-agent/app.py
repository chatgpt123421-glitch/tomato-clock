"""
会议统筹智能体 - Web界面 (Streamlit)
"""
import json
import streamlit as st
from meeting_agent import MeetingCoordinator


st.set_page_config(
    page_title="会议统筹智能体",
    page_icon="🤖",
    layout="wide"
)

st.title("🤖 会议统筹智能体")
st.markdown("让AI帮你高效管理会议全流程")

# 侧边栏 - API配置
with st.sidebar:
    st.header("⚙️ 配置")
    api_key = st.text_input("Anthropic API Key", type="password", help="输入你的Claude API密钥")

    if api_key:
        if "coordinator" not in st.session_state:
            st.session_state.coordinator = MeetingCoordinator(api_key=api_key)
        st.success("✅ API密钥已配置")
    else:
        st.info("💡 输入API密钥以启用AI功能")

    st.divider()
    st.markdown("### 功能说明")
    st.markdown("""
    - 📅 创建会议
    - 👥 管理参会人
    - 📋 AI生成议程
    - ⏰ 智能时间推荐
    - 📝 自动整理纪要
    """)

# 初始化会话状态
if "coordinator" not in st.session_state:
    st.session_state.coordinator = None
if "current_meeting" not in st.session_state:
    st.session_state.current_meeting = None

# 主界面标签页
tab1, tab2, tab3, tab4 = st.tabs(["📅 会议管理", "📋 议程生成", "⏰ 时间协调", "📝 会议纪要"])

# Tab 1: 会议管理
with tab1:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("创建新会议")
        with st.form("create_meeting"):
            title = st.text_input("会议标题")
            description = st.text_area("会议描述")
            duration = st.slider("预计时长(分钟)", 15, 180, 60, 15)
            submitted = st.form_submit_button("创建会议", use_container_width=True)

            if submitted and title:
                if st.session_state.coordinator:
                    meeting = st.session_state.coordinator.create_meeting(title, description)
                    meeting.duration_minutes = duration
                st.session_state.current_meeting = title
                st.success(f"✅ 会议 '{title}' 创建成功！")

    with col2:
        st.subheader("添加参会人员")
        if st.session_state.current_meeting:
            st.info(f"当前会议: {st.session_state.current_meeting}")
            with st.form("add_participant"):
                name = st.text_input("姓名")
                role = st.text_input("职位/角色")
                email = st.text_input("邮箱")
                add_btn = st.form_submit_button("添加参会人", use_container_width=True)

                if add_btn and name and st.session_state.coordinator:
                    st.session_state.coordinator.add_participant(
                        st.session_state.current_meeting, name, role, email
                    )
                    st.success(f"✅ 已添加: {name}")
        else:
            st.info("👆 请先创建会议")

    # 显示当前会议信息
    if st.session_state.current_meeting and st.session_state.coordinator:
        st.divider()
        st.subheader("📊 当前会议概览")
        info = st.session_state.coordinator.get_meeting_info(st.session_state.current_meeting)

        cols = st.columns(4)
        with cols[0]:
            st.metric("参会人数", len(info['participants']))
        with cols[1]:
            st.metric("预计时长", f"{info['duration']}分钟")
        with cols[2]:
            st.metric("议程项数", len(info['agenda']) if info['agenda'] else 0)
        with cols[3]:
            has_notes = "是" if info['notes'] else "否"
            st.metric("已整理纪要", has_notes)

        if info['participants']:
            st.markdown("**参会人员:**")
            for p in info['participants']:
                st.markdown(f"- {p['name']} ({p['role']})")

# Tab 2: 议程生成
with tab2:
    st.subheader("📋 AI生成会议议程")

    if st.session_state.current_meeting and st.session_state.coordinator:
        if st.button("🤖 生成议程", use_container_width=True):
            with st.spinner("AI正在生成议程..."):
                agenda = st.session_state.coordinator.generate_agenda(
                    st.session_state.current_meeting
                )
            st.success("✅ 议程生成完成！")

        info = st.session_state.coordinator.get_meeting_info(st.session_state.current_meeting)
        if info['agenda']:
            st.markdown("### 会议议程")
            for i, item in enumerate(info['agenda'], 1):
                st.markdown(f"**{i}.** {item}")
    else:
        st.info("请先创建会议并配置API密钥")

# Tab 3: 时间协调
with tab3:
    st.subheader("⏰ 智能时间推荐")

    if st.session_state.current_meeting and st.session_state.coordinator:
        if st.button("🤖 分析最佳时间", use_container_width=True):
            with st.spinner("AI正在分析..."):
                result = st.session_state.coordinator.analyze_schedule(
                    st.session_state.current_meeting
                )

            if "recommended_times" in result:
                st.markdown("### 推荐时间")
                for time in result['recommended_times']:
                    st.success(f"⏰ {time}")

                if 'rationale' in result:
                    st.markdown("### 推荐理由")
                    st.info(result['rationale'])

                if 'considerations' in result:
                    st.markdown("### 注意事项")
                    for note in result['considerations']:
                        st.warning(f"⚠️ {note}")
    else:
        st.info("请先创建会议并配置API密钥")

# Tab 4: 会议纪要
with tab4:
    st.subheader("📝 AI整理会议纪要")

    if st.session_state.current_meeting and st.session_state.coordinator:
        transcript = st.text_area(
            "会议记录 (支持语音转文字或手动输入)",
            height=200,
            placeholder="粘贴会议记录内容，AI将自动整理为结构化纪要..."
        )

        if st.button("🤖 整理纪要", use_container_width=True) and transcript:
            with st.spinner("AI正在整理..."):
                summary = st.session_state.coordinator.summarize_meeting(
                    st.session_state.current_meeting, transcript
                )

            st.markdown("### 会议纪要")

            if 'summary' in summary:
                st.markdown("**摘要**")
                st.info(summary['summary'])

            if 'key_points' in summary:
                st.markdown("**关键要点**")
                for point in summary['key_points']:
                    st.markdown(f"- {point}")

            if 'decisions' in summary:
                st.markdown("**决策事项**")
                for decision in summary['decisions']:
                    st.success(f"✅ {decision}")

            if 'action_items' in summary:
                st.markdown("**行动项**")
                for item in summary['action_items']:
                    st.markdown(f"- [ ] **{item.get('task')}** | 负责人: {item.get('owner')} | 截止: {item.get('deadline')}")
    else:
        st.info("请先创建会议并配置API密钥")

# 页脚
st.divider()
st.caption("🤖 会议统筹智能体 | Powered by Claude API")
