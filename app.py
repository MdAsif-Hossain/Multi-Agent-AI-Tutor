from __future__ import annotations

import html
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

from leo.engine import DEFAULT_MODEL, ClarificationRequired, TutorEngine  # noqa: E402
from leo.models import (  # noqa: E402
    AgentEvent,
    AssessmentBundle,
    LessonPackage,
    QuizPackage,
    RemediationBundle,
    StudentProfile,
    TeachingBundle,
)
from leo.storage import StudentMemory  # noqa: E402

st.set_page_config(
    page_title="Leo · Multi-Agent AI Tutor",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');

:root {
  --ink: #f7f8fc;
  --muted: #9aa6c1;
  --panel: rgba(18, 26, 47, .84);
  --line: rgba(255, 255, 255, .08);
  --violet: #8b7cff;
  --cyan: #33ddc4;
  --amber: #ffbd70;
}

html, body, [class*="css"] { font-family: "DM Sans", sans-serif; }
h1, h2, h3 { font-family: "Manrope", sans-serif !important; letter-spacing: -.035em; }

[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(circle at 12% 8%, rgba(95, 74, 255, .16), transparent 30%),
    radial-gradient(circle at 88% 6%, rgba(51, 221, 196, .10), transparent 26%),
    #070b18;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] {
  background: rgba(10, 15, 30, .94);
  border-right: 1px solid var(--line);
}
.block-container { max-width: 1260px; padding-top: 2rem; padding-bottom: 4rem; }

.leo-hero {
  position: relative;
  overflow: hidden;
  padding: 2.1rem 2.2rem;
  border: 1px solid rgba(139, 124, 255, .24);
  border-radius: 28px;
  background: linear-gradient(135deg, rgba(22, 28, 53, .96), rgba(12, 21, 38, .88));
  box-shadow: 0 28px 70px rgba(0, 0, 0, .28);
  margin-bottom: 1.25rem;
}
.leo-hero:after {
  content: "";
  position: absolute;
  width: 260px; height: 260px; right: -80px; top: -130px;
  background: radial-gradient(circle, rgba(51, 221, 196, .22), transparent 66%);
}
.leo-brand { display: flex; align-items: center; gap: 1rem; }
.leo-orb {
  width: 58px; height: 58px; display: grid; place-items: center;
  border-radius: 19px;
  background: linear-gradient(145deg, #a496ff, #6657e8);
  color: white; font-family: "Manrope"; font-weight: 800; font-size: 1.7rem;
  box-shadow: 0 12px 35px rgba(112, 91, 255, .36), inset 0 1px rgba(255,255,255,.3);
}
.leo-eyebrow {
  color: var(--cyan); font-size: .76rem; font-weight: 700;
  letter-spacing: .14em; text-transform: uppercase; margin-bottom: .3rem;
}
.leo-title { font-size: clamp(2rem, 5vw, 3.4rem); line-height: 1; margin: 0; }
.leo-subtitle { color: #b4bed3; max-width: 720px; font-size: 1.04rem; margin: .9rem 0 0; }
.hero-badges { display: flex; flex-wrap: wrap; gap: .55rem; margin-top: 1.25rem; }
.hero-badge {
  padding: .42rem .72rem; border-radius: 999px; color: #cad2e5;
  background: rgba(255,255,255,.045); border: 1px solid var(--line); font-size: .78rem;
}
.hero-badge.live { color: #bcfff3; border-color: rgba(51,221,196,.25); background: rgba(51,221,196,.08); }

.section-label {
  margin: 1.6rem 0 .7rem; color: #71809f; font-size: .73rem;
  font-weight: 800; letter-spacing: .14em; text-transform: uppercase;
}
.agent-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: .75rem; }
.agent-card {
  padding: 1.15rem; min-height: 150px; border-radius: 20px;
  background: var(--panel); border: 1px solid var(--line);
  transition: transform .2s, border-color .2s;
}
.agent-card:hover { transform: translateY(-3px); border-color: rgba(139,124,255,.36); }
.agent-icon {
  width: 38px; height: 38px; display: grid; place-items: center;
  border-radius: 12px; color: white; background: rgba(139,124,255,.16);
  margin-bottom: .85rem; font-weight: 800;
}
.agent-card:nth-child(2) .agent-icon { background: rgba(51,221,196,.13); color: var(--cyan); }
.agent-card:nth-child(3) .agent-icon { background: rgba(255,189,112,.14); color: var(--amber); }
.agent-card:nth-child(4) .agent-icon { background: rgba(255,112,157,.13); color: #ff93b7; }
.agent-name { font-family: "Manrope"; font-weight: 700; font-size: .98rem; }
.agent-copy { color: var(--muted); font-size: .82rem; line-height: 1.5; margin-top: .35rem; }

.flow-line {
  display: flex; align-items: center; gap: .45rem; overflow-x: auto;
  padding: .8rem 0 .2rem;
}
.flow-node {
  white-space: nowrap; padding: .6rem .82rem; border-radius: 12px;
  background: rgba(255,255,255,.04); border: 1px solid var(--line);
  color: #c7d0e3; font-size: .78rem;
}
.flow-arrow { color: #53617d; font-size: 1rem; }

.progress-shell {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: .55rem;
  margin: 1rem 0 1.4rem;
}
.progress-step {
  padding: .7rem .8rem; border-radius: 13px; border: 1px solid var(--line);
  color: #64708c; background: rgba(255,255,255,.025); font-size: .78rem;
}
.progress-step.done { color: #bff9ef; border-color: rgba(51,221,196,.23); background: rgba(51,221,196,.06); }
.progress-step.active { color: white; border-color: rgba(139,124,255,.42); background: rgba(139,124,255,.12); }
.progress-num { font-family: "Manrope"; font-weight: 800; margin-right: .35rem; }

.memory-note, .callout {
  padding: 1rem 1.1rem; border-radius: 16px; border: 1px solid var(--line);
  background: rgba(255,255,255,.035); color: #c6cee0; line-height: 1.55;
}
.memory-note { border-left: 3px solid var(--cyan); }
.callout { border-left: 3px solid var(--violet); margin: .8rem 0 1rem; }
.callout strong { color: white; }

.lesson-hook {
  padding: 1.2rem 1.25rem; border-radius: 18px;
  background: linear-gradient(135deg, rgba(139,124,255,.13), rgba(51,221,196,.06));
  border: 1px solid rgba(139,124,255,.18); color: #dfe3ef;
  font-size: 1.02rem; line-height: 1.65; margin-bottom: 1rem;
}
.objective {
  display: flex; gap: .65rem; align-items: flex-start; color: #c6cee0;
  padding: .42rem 0; font-size: .9rem;
}
.objective-check { color: var(--cyan); font-weight: 800; }
.lesson-section {
  border-left: 1px solid rgba(139,124,255,.32); padding: .2rem 0 .2rem 1.1rem;
  margin: 1rem 0 1.4rem;
}
.lesson-section h3 { font-size: 1.08rem; margin: 0 0 .45rem; }
.lesson-section p { color: #b7c0d4; line-height: 1.7; margin: 0; }
.example {
  margin-top: .7rem; color: #d5dcec; background: rgba(255,255,255,.03);
  border-radius: 12px; padding: .75rem .85rem; font-size: .87rem;
}

.score-ring {
  width: 150px; height: 150px; border-radius: 50%; display: grid; place-items: center;
  background: conic-gradient(var(--cyan) calc(var(--score) * 1%), rgba(255,255,255,.07) 0);
  margin: .35rem auto; position: relative;
}
.score-ring:before {
  content: ""; position: absolute; width: 120px; height: 120px;
  border-radius: 50%; background: #0d1426;
}
.score-value { position: relative; font-family: "Manrope"; font-size: 2rem; font-weight: 800; }
.score-label { position: relative; color: var(--muted); font-size: .68rem; text-transform: uppercase; letter-spacing: .1em; }

.event {
  display: grid; grid-template-columns: 34px 1fr; gap: .7rem;
  padding: .65rem 0; border-bottom: 1px solid rgba(255,255,255,.055);
}
.event:last-child { border-bottom: 0; }
.event-dot {
  width: 30px; height: 30px; border-radius: 10px; display: grid; place-items: center;
  background: rgba(139,124,255,.12); color: #b9afff; font-size: .75rem; font-weight: 800;
}
.event-agent { font-weight: 700; color: #e9ecf4; font-size: .84rem; }
.event-message { color: #8e9ab5; font-size: .77rem; margin-top: .12rem; }
.preview-flag {
  color: #ffd5a2; background: rgba(255,189,112,.09); border: 1px solid rgba(255,189,112,.2);
  padding: .65rem .8rem; border-radius: 12px; font-size: .75rem; line-height: 1.45;
}

div[data-testid="stForm"] {
  border: 1px solid var(--line); border-radius: 20px; padding: 1.15rem;
  background: rgba(16, 23, 42, .58);
}
div[data-testid="stTextArea"] textarea {
  min-height: 7.5rem;
  padding-bottom: 2.25rem;
}
.stButton > button, .stFormSubmitButton > button {
  border-radius: 12px; min-height: 2.75rem; font-weight: 700;
  border: 1px solid rgba(139,124,255,.35);
}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background: linear-gradient(135deg, #8b7cff, #6b5be7); border: 0;
  box-shadow: 0 10px 25px rgba(108,88,230,.25);
}
div[data-testid="stMetric"] {
  background: rgba(255,255,255,.032); border: 1px solid var(--line);
  border-radius: 16px; padding: .85rem 1rem;
}
div[data-testid="stExpander"] { border: 1px solid var(--line); border-radius: 15px; background: rgba(255,255,255,.025); }
hr { border-color: var(--line) !important; }

@media (max-width: 900px) {
  .agent-grid { grid-template-columns: repeat(2, 1fr); }
  .leo-hero { padding: 1.5rem; }
}
@media (max-width: 600px) {
  .agent-grid { grid-template-columns: 1fr; }
  .progress-shell { grid-template-columns: repeat(2, 1fr); }
  .leo-title { font-size: 2rem; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def initialize_state() -> None:
    defaults = {
        "stage": "setup",
        "events": [],
        "teaching": None,
        "assessment": None,
        "remediation": None,
        "final_assessment": None,
        "profile": None,
        "topic": "",
        "history": [],
        "preview_mode": True,
        "model_name": os.getenv("LEO_MODEL", DEFAULT_MODEL),
        "saved": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_session() -> None:
    for key in list(st.session_state):
        del st.session_state[key]
    st.rerun()


def provider_api_key_available(model_name: str) -> bool:
    provider = model_name.partition("/")[0].lower()
    key_name = {
        "gemini": "GEMINI_API_KEY",
        "google": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
    }.get(provider)
    return bool(key_name and os.getenv(key_name))


def event_handler(status_box):
    def handle(event: AgentEvent) -> None:
        st.session_state.events.append(event.model_dump())
        icon = "✓" if event.status == "completed" else "✦"
        status_box.update(label=f"{icon} {event.agent} · {event.message}", state="running")

    return handle


def engine_for(status_box) -> TutorEngine:
    return TutorEngine(
        model=st.session_state.model_name,
        preview_mode=st.session_state.preview_mode,
        on_event=event_handler(status_box),
    )


def hero() -> None:
    mode = "Preview mode" if st.session_state.preview_mode else "Live CrewAI"
    mode_class = "" if st.session_state.preview_mode else " live"
    st.markdown(
        f"""
        <section class="leo-hero">
          <div class="leo-brand">
            <div class="leo-orb">L</div>
            <div>
              <div class="leo-eyebrow">Adaptive multi-agent learning</div>
              <h1 class="leo-title">Meet Leo.</h1>
            </div>
          </div>
          <p class="leo-subtitle">
            One learning goal. Four specialist agents. A lesson that adapts
            when your answers show where you need help.
          </p>
          <div class="hero-badges">
            <span class="hero-badge{mode_class}">● {mode}</span>
            <span class="hero-badge">4 specialist agents</span>
            <span class="hero-badge">Structured handoffs</span>
            <span class="hero-badge">Adaptive feedback loop</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def progress() -> None:
    stage = st.session_state.stage
    active_map = {
        "setup": 0,
        "lesson": 1,
        "quiz": 2,
        "remediation_lesson": 3,
        "remediation_quiz": 2,
        "complete": 3,
    }
    active = active_map.get(stage, 0)
    labels = ["Plan", "Learn", "Practice", "Feedback"]
    blocks = []
    for index, label in enumerate(labels):
        css = "done" if index < active else "active" if index == active else ""
        blocks.append(
            f'<div class="progress-step {css}"><span class="progress-num">0{index + 1}</span>{label}</div>'
        )
    st.markdown(f'<div class="progress-shell">{"".join(blocks)}</div>', unsafe_allow_html=True)


AGENTS = [
    ("CO", "Coordinator", "Plans the learning path, delegates work, and manages recovery."),
    ("EX", "Explainer", "Teaches at your level with examples, analogies, and misconception checks."),
    ("QM", "Quiz Master", "Builds structured questions from only the material you were taught."),
    ("EV", "Evaluator", "Grades with a rubric, gives feedback, and identifies weak concepts."),
]


def welcome_panel() -> None:
    st.markdown('<div class="section-label">Your AI teaching team</div>', unsafe_allow_html=True)
    cards = "".join(
        f'<div class="agent-card">'
        f'<div class="agent-icon">{code}</div>'
        f'<div class="agent-name">{name}</div>'
        f'<div class="agent-copy">{copy}</div>'
        f"</div>"
        for code, name, copy in AGENTS
    )
    st.markdown(f'<div class="agent-grid">{cards}</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-label">How work moves</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="flow-line">
          <span class="flow-node">Student request</span><span class="flow-arrow">→</span>
          <span class="flow-node">LearningPlan</span><span class="flow-arrow">→</span>
          <span class="flow-node">LessonPackage</span><span class="flow-arrow">→</span>
          <span class="flow-node">QuizPackage</span><span class="flow-arrow">→</span>
          <span class="flow-node">EvaluationReport</span><span class="flow-arrow">→</span>
          <span class="flow-node">Re-teach or complete</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="section-label">Try a learning goal</div>', unsafe_allow_html=True)
    cols = st.columns(3)
    examples = [
        ("Python recursion", "Understand recursion well enough to trace a function by hand."),
        ("SQL joins", "Learn how to choose the correct join for a data problem."),
        ("Photosynthesis", "Explain the process clearly for an upcoming exam."),
    ]
    for column, (topic, goal) in zip(cols, examples):
        with column:
            st.markdown(
                f"""
                <div class="callout">
                  <strong>{topic}</strong><br>
                  <span style="color:#8f9bb5;font-size:.82rem">{goal}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )


def sidebar(memory: StudentMemory) -> None:
    with st.sidebar:
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:.7rem;margin:.35rem 0 1.4rem">
              <div class="leo-orb" style="width:42px;height:42px;border-radius:14px;font-size:1.2rem">L</div>
              <div><strong style="font-family:Manrope">Leo Tutor</strong><br>
              <span style="color:#71809f;font-size:.72rem">Learning workspace</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.session_state.stage == "setup":
            with st.form("student_setup"):
                st.markdown("#### Start a learning session")
                name = st.text_input("Your name", placeholder="e.g. Asif", max_chars=60)
                level = st.select_slider(
                    "Current level",
                    options=["Beginner", "Intermediate", "Advanced"],
                    value="Beginner",
                )
                topic = st.text_input(
                    "What do you want to learn?",
                    placeholder="e.g. Python recursion",
                    max_chars=160,
                )
                goal = st.text_area(
                    "Your goal",
                    placeholder="What should you be able to do after this session?",
                    max_chars=240,
                    height=125,
                )
                preview = st.toggle(
                    "Preview without an API key",
                    value=not provider_api_key_available(st.session_state.model_name),
                    help="Uses deterministic sample content to test the full interface. Turn off for the graded CrewAI run.",
                )
                model_name = st.text_input(
                    "CrewAI model",
                    value=st.session_state.model_name,
                    disabled=preview,
                    help="Any CrewAI/LiteLLM-compatible model identifier.",
                )
                submitted = st.form_submit_button(
                    "Build my learning path →",
                    type="primary",
                    use_container_width=True,
                )

            if preview:
                st.markdown(
                    """
                    <div class="preview-flag">
                      <strong>Preview is clearly separated.</strong><br>
                      It exercises the UI and handoff contracts without claiming an LLM run.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            if submitted:
                try:
                    profile = StudentProfile(name=name, level=level, goal=goal)
                    clean_topic = " ".join(topic.split())
                    if len(clean_topic) < 3:
                        raise ValueError("Please enter a clear topic of at least 3 characters.")
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.session_state.preview_mode = preview
                    st.session_state.model_name = model_name
                    st.session_state.profile = profile.model_dump()
                    st.session_state.topic = clean_topic
                    st.session_state.history = memory.recent(profile.name)
                    with st.status("Coordinator is reading your request…", expanded=True) as status:
                        try:
                            teaching = engine_for(status).create_lesson(
                                profile,
                                clean_topic,
                                memory.prompt_context(profile.name),
                            )
                        except ClarificationRequired as error:
                            status.update(label="Clarification needed", state="error")
                            st.error(str(error))
                        except Exception as error:
                            status.update(label="The session could not start", state="error")
                            st.error(
                                "Leo preserved your request, but an agent could not complete its turn. "
                                f"Check the model/API configuration and retry. Details: {error}"
                            )
                        else:
                            st.session_state.teaching = teaching.model_dump()
                            st.session_state.stage = "lesson"
                            status.update(label="Your learning path is ready", state="complete")
                            st.rerun()
        else:
            profile = StudentProfile.model_validate(st.session_state.profile)
            st.markdown("##### Current learner")
            st.markdown(f"**{html.escape(profile.name)}** · {profile.level}")
            st.caption(profile.goal)
            st.markdown("##### Current topic")
            st.markdown(f"**{html.escape(st.session_state.topic)}**")
            if st.button("Start a new session", use_container_width=True):
                reset_session()

        history = st.session_state.get("history", [])
        if history:
            st.divider()
            st.markdown("##### Remembered sessions")
            for item in history[:3]:
                st.markdown(
                    f"**{html.escape(item['topic'])}**  \n"
                    f"<span style='color:#7f8ba5;font-size:.75rem'>{item['score']:.0f}% · {item['level']}</span>",
                    unsafe_allow_html=True,
                )


def render_events() -> None:
    events = st.session_state.events
    if not events:
        return
    st.markdown('<div class="section-label">Agent activity</div>', unsafe_allow_html=True)
    with st.expander(f"Inspect {len(events)} orchestration events", expanded=False):
        for event in events:
            code = next((code for code, name, _ in AGENTS if name == event["agent"]), "AI")
            st.markdown(
                f"""
                <div class="event">
                  <div class="event-dot">{code}</div>
                  <div>
                    <div class="event-agent">{html.escape(event["agent"])}</div>
                    <div class="event-message">{html.escape(event["message"])}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_lesson(lesson: LessonPackage, *, remediation: bool = False) -> None:
    eyebrow = "Targeted re-teaching" if remediation else "Explainer's lesson"
    st.markdown(f'<div class="section-label">{eyebrow}</div>', unsafe_allow_html=True)
    st.header(lesson.title)
    st.markdown(f'<div class="lesson-hook">{html.escape(lesson.hook)}</div>', unsafe_allow_html=True)

    left, right = st.columns([1.65, 1], gap="large")
    with left:
        for section in lesson.sections:
            example = (
                f'<div class="example"><strong>Example</strong><br>{html.escape(section.example)}</div>'
                if section.example
                else ""
            )
            st.markdown(
                f"""
                <div class="lesson-section">
                  <h3>{html.escape(section.heading)}</h3>
                  <p>{html.escape(section.explanation)}</p>
                  {example}
                </div>
                """,
                unsafe_allow_html=True,
            )
    with right:
        st.markdown("#### Learning objectives")
        for objective in lesson.objectives:
            st.markdown(
                f'<div class="objective"><span class="objective-check">✓</span>{html.escape(objective)}</div>',
                unsafe_allow_html=True,
            )
        st.markdown("#### A useful analogy")
        st.info(lesson.analogy)
        with st.expander("Worked example", expanded=True):
            st.write(lesson.worked_example)
        with st.expander("Common misconceptions"):
            for misconception in lesson.misconceptions:
                st.markdown(f"- {misconception}")

    st.markdown("#### Key takeaways")
    takeaways = st.columns(min(len(lesson.key_takeaways), 3))
    for index, takeaway in enumerate(lesson.key_takeaways):
        with takeaways[index % len(takeaways)]:
            st.markdown(f'<div class="callout">{html.escape(takeaway)}</div>', unsafe_allow_html=True)


def quiz_form(quiz: QuizPackage, *, attempt: int) -> None:
    st.markdown('<div class="section-label">Quiz Master · structured practice</div>', unsafe_allow_html=True)
    st.header(quiz.title)
    st.caption(quiz.instructions)
    with st.form(f"quiz_attempt_{attempt}"):
        answers: dict[str, str] = {}
        for index, question in enumerate(quiz.questions, start=1):
            st.markdown(f"### {index}. {question.prompt}")
            st.caption(f"{question.concept} · {question.max_points} points")
            key = f"answer_{attempt}_{question.question_id}"
            if question.options:
                answers[question.question_id] = st.radio(
                    "Choose one answer",
                    question.options,
                    index=None,
                    key=key,
                    label_visibility="collapsed",
                ) or ""
            else:
                answers[question.question_id] = st.text_area(
                    "Your answer",
                    key=key,
                    placeholder="Explain your reasoning…",
                    height=95,
                )
            st.divider()
        submitted = st.form_submit_button(
            "Submit answers for evaluation →",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not all(answer.strip() for answer in answers.values()):
            st.warning("Please answer every question before submitting.")
            return
        profile = StudentProfile.model_validate(st.session_state.profile)
        teaching = TeachingBundle.model_validate(st.session_state.teaching)
        lesson = (
            RemediationBundle.model_validate(st.session_state.remediation).lesson
            if attempt == 2
            else teaching.lesson
        )
        with st.status("Evaluator is grading with the quiz rubric…", expanded=True) as status:
            try:
                assessment = engine_for(status).evaluate(
                    profile,
                    lesson,
                    quiz,
                    answers,
                    attempt=attempt,
                )
                if assessment.decision.action == "reteach":
                    remediation = engine_for(status).create_remediation(lesson, assessment)
                    st.session_state.assessment = assessment.model_dump()
                    st.session_state.remediation = remediation.model_dump()
                    st.session_state.stage = "remediation_lesson"
                else:
                    st.session_state.final_assessment = assessment.model_dump()
                    if attempt == 1:
                        st.session_state.assessment = assessment.model_dump()
                    st.session_state.stage = "complete"
                status.update(label="Feedback is ready", state="complete")
            except Exception as error:
                status.update(label="Evaluation could not finish", state="error")
                st.error(
                    "Your answers are still on this page. Retry after checking the model/API settings. "
                    f"Details: {error}"
                )
            else:
                st.rerun()


def render_report(assessment: AssessmentBundle, title: str = "Your learning review") -> None:
    report = assessment.report
    st.markdown('<div class="section-label">Evaluator · evidence-based feedback</div>', unsafe_allow_html=True)
    st.header(title)
    left, right = st.columns([1, 2], gap="large")
    with left:
        st.markdown(
            f"""
            <div class="score-ring" style="--score:{report.score_percent}">
              <div style="text-align:center;position:relative">
                <div class="score-value">{report.score_percent:.0f}%</div>
                <div class="score-label">score</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(f'<div class="callout"><strong>Coordinator:</strong><br>{html.escape(assessment.decision.student_message)}</div>', unsafe_allow_html=True)
        metric_cols = st.columns(3)
        metric_cols[0].metric("Points", f"{report.total_earned:g}/{report.total_possible:g}")
        metric_cols[1].metric("Mastered", len(report.mastered_concepts))
        metric_cols[2].metric("To review", len(report.weak_concepts))
        st.write(report.overall_feedback)

    st.markdown("#### Question-by-question feedback")
    for result in report.question_results:
        icon = "✓" if result.verdict == "correct" else "◐" if result.verdict == "partially_correct" else "→"
        with st.expander(
            f"{icon} {result.question_id} · {result.earned_points:g}/{result.max_points:g} points"
        ):
            st.write(result.feedback)
            st.markdown(f"**Ideal answer:** {result.ideal_answer}")

    if report.weak_concepts:
        st.markdown("#### Concepts selected for re-teaching")
        st.write(" · ".join(report.weak_concepts))


def save_final(memory: StudentMemory, assessment: AssessmentBundle) -> None:
    if st.session_state.saved:
        return
    profile = StudentProfile.model_validate(st.session_state.profile)
    memory.save(profile, st.session_state.topic, assessment.report)
    st.session_state.saved = True


initialize_state()
memory = StudentMemory(os.getenv("LEO_DB_PATH", "data/leo.db"))
sidebar(memory)
hero()
progress()

stage = st.session_state.stage
if stage == "setup":
    welcome_panel()
elif stage == "lesson":
    teaching = TeachingBundle.model_validate(st.session_state.teaching)
    render_lesson(teaching.lesson)
    st.markdown(
        """
        <div class="memory-note">
          <strong>Human checkpoint</strong><br>
          You control the pace. Review the lesson before allowing the Quiz Master to continue.
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("I’m ready for the quiz →", type="primary", use_container_width=True):
        st.session_state.stage = "quiz"
        st.rerun()
elif stage == "quiz":
    teaching = TeachingBundle.model_validate(st.session_state.teaching)
    quiz_form(teaching.quiz, attempt=1)
elif stage == "remediation_lesson":
    first_assessment = AssessmentBundle.model_validate(st.session_state.assessment)
    remediation = RemediationBundle.model_validate(st.session_state.remediation)
    render_report(first_assessment, "Your first learning review")
    st.divider()
    render_lesson(remediation.lesson, remediation=True)
    if st.button("Try the targeted follow-up →", type="primary", use_container_width=True):
        st.session_state.stage = "remediation_quiz"
        st.rerun()
elif stage == "remediation_quiz":
    remediation = RemediationBundle.model_validate(st.session_state.remediation)
    quiz_form(remediation.quiz, attempt=2)
elif stage == "complete":
    final_data = st.session_state.final_assessment or st.session_state.assessment
    final_assessment = AssessmentBundle.model_validate(final_data)
    save_final(memory, final_assessment)
    if st.session_state.final_assessment and st.session_state.assessment:
        first = AssessmentBundle.model_validate(st.session_state.assessment)
        first_score = first.report.score_percent
        final_score = final_assessment.report.score_percent
        st.markdown(
            f"""
            <div class="memory-note">
              <strong>Adaptive loop completed</strong><br>
              First attempt: {first_score:.0f}% &nbsp;→&nbsp; Follow-up: {final_score:.0f}%.
              Leo has stored this session for your next visit.
            </div>
            """,
            unsafe_allow_html=True,
        )
    render_report(final_assessment)
    st.success("Session complete. Your topic, score, and concept feedback are now in learner memory.")
    if st.button("Start another topic", type="primary"):
        reset_session()

render_events()
st.markdown(
    """
    <div style="text-align:center;color:#53617d;font-size:.72rem;margin-top:3rem">
      Leo teaches with AI-generated content. Verify important academic information with trusted sources.
    </div>
    """,
    unsafe_allow_html=True,
)
