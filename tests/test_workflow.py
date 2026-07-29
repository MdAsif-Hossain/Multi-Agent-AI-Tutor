from __future__ import annotations

from unittest.mock import patch

import pytest
from crewai import Crew, Process, Task
from crewai.llms.providers.gemini.completion import GeminiCompletion
from pydantic import ValidationError

from leo.engine import DEFAULT_MODEL, GROQ_MODEL, TutorEngine
from leo.models import (
    EvaluationReport,
    LearningPlan,
    LessonPackage,
    QuestionEvaluation,
    QuizPackage,
    QuizQuestion,
    StudentProfile,
    finalize_evaluation,
    required_route,
)
from leo.storage import StudentMemory


def make_quiz() -> QuizPackage:
    return QuizPackage(
        title="Test quiz",
        instructions="Answer both.",
        questions=[
            QuizQuestion(
                question_id="Q1",
                concept="Concept A",
                question_type="true_false",
                prompt="A?",
                options=["True", "False"],
                correct_answer="True",
                explanation="Because A.",
                scoring_guide="10 for True.",
            ),
            QuizQuestion(
                question_id="Q2",
                concept="Concept B",
                question_type="short_answer",
                prompt="Explain B.",
                correct_answer="B is explained.",
                explanation="Because B.",
                scoring_guide="Up to 10.",
            ),
        ],
    )


def test_quiz_rejects_duplicate_question_ids() -> None:
    question = make_quiz().questions[0]
    with pytest.raises(ValidationError):
        QuizPackage(
            title="Invalid",
            instructions="Duplicate IDs",
            questions=[question, question],
        )


def test_evaluation_totals_come_from_source_quiz() -> None:
    quiz = make_quiz()
    report = EvaluationReport(
        question_results=[
            QuestionEvaluation(
                question_id="Q1",
                earned_points=999,
                max_points=999,
                verdict="correct",
                feedback="Good",
                ideal_answer="True",
            )
        ],
        overall_feedback="Test",
    )

    normalized = finalize_evaluation(report, quiz)

    assert normalized.total_earned == 10
    assert normalized.total_possible == 20
    assert normalized.score_percent == 50
    assert normalized.question_results[1].verdict == "unanswered"


def test_feedback_route_is_bounded() -> None:
    report = EvaluationReport(
        question_results=[
            QuestionEvaluation(
                question_id="Q1",
                earned_points=2,
                max_points=10,
                verdict="incorrect",
                feedback="Review",
                ideal_answer="Answer",
            )
        ],
        weak_concepts=["Concept A"],
        overall_feedback="Review",
        score_percent=20,
    )

    assert required_route(report, attempt=1) == "reteach"
    assert required_route(report, attempt=2) == "complete"


def test_collected_level_resolves_redundant_clarification() -> None:
    profile = StudentProfile(
        name="Asif",
        level="Beginner",
        goal="Become an AI engineer within six months",
    )
    plan = LearningPlan(
        topic="AI Engineering",
        learner_level="Beginner",
        goal_summary=profile.goal,
        objectives=["Understand AI", "Learn Python", "Build a project"],
        teaching_strategy="Start with foundations.",
        quiz_focus=["AI foundations", "Python"],
        clarification_needed=True,
        clarification_question=(
            "Do you have prior programming experience, or should we start from absolute zero?"
        ),
    )

    assert TutorEngine._clarification_answered_by_profile(plan, profile)


def test_preview_mode_runs_all_agent_handoffs() -> None:
    events = []
    engine = TutorEngine(preview_mode=True, on_event=events.append)
    profile = StudentProfile(
        name="Asif",
        level="Beginner",
        goal="Understand recursion for an exam",
    )

    teaching = engine.create_lesson(profile, "Python recursion", "No prior sessions")
    answers = {question.question_id: "wrong" for question in teaching.quiz.questions}
    assessment = engine.evaluate(
        profile,
        teaching.lesson,
        teaching.quiz,
        answers,
        attempt=1,
    )
    remediation = engine.create_remediation(teaching.lesson, assessment)

    assert len(teaching.quiz.questions) == 4
    assert assessment.decision.action == "reteach"
    assert len(remediation.quiz.questions) == 2
    assert {"Coordinator", "Explainer", "Quiz Master", "Evaluator"} <= {
        event.agent for event in events
    }


def test_live_crewai_wiring_matches_installed_framework_api() -> None:
    engine = TutorEngine(model=DEFAULT_MODEL, preview_mode=False)
    coordinator = engine._agent("coordinator")
    explainer = engine._agent("explainer")
    plan = Task(
        config=engine.tasks_config["planning_task"],
        agent=coordinator,
        output_pydantic=LearningPlan,
    )
    lesson = Task(
        config=engine.tasks_config["explanation_task"],
        agent=explainer,
        context=[plan],
        output_pydantic=LessonPackage,
    )

    crew = Crew(
        agents=[coordinator, explainer],
        tasks=[plan, lesson],
        process=Process.sequential,
        verbose=False,
    )

    assert crew.process == Process.sequential
    assert coordinator.role != explainer.role
    assert lesson.context == [plan]


def test_groq_free_tier_fallback_initializes() -> None:
    engine = TutorEngine(model=GROQ_MODEL, preview_mode=False)

    assert engine.llm is not None
    assert engine.model_name == "groq/openai/gpt-oss-120b"


def test_real_crewai_sequential_kickoff_uses_typed_handoffs_without_network() -> None:
    profile = StudentProfile(
        name="Asif",
        level="Beginner",
        goal="Understand recursion for an exam",
    )
    fixture = TutorEngine(preview_mode=True).create_lesson(
        profile,
        "Python recursion",
        "No prior sessions",
    )
    wrong_answers = {question.question_id: "wrong" for question in fixture.quiz.questions}
    preview_engine = TutorEngine(preview_mode=True)
    assessment_fixture = preview_engine.evaluate(
        profile,
        fixture.lesson,
        fixture.quiz,
        wrong_answers,
        attempt=1,
    )
    remediation_fixture = preview_engine.create_remediation(
        fixture.lesson,
        assessment_fixture,
    )

    with patch.object(
        GeminiCompletion,
        "call",
        side_effect=[
            fixture.plan.model_dump_json(),
            fixture.lesson.model_dump_json(),
            fixture.quiz.model_dump_json(),
            assessment_fixture.report.model_dump_json(),
            assessment_fixture.decision.model_dump_json(),
            remediation_fixture.lesson.model_dump_json(),
            remediation_fixture.quiz.model_dump_json(),
        ],
    ):
        engine = TutorEngine(model=DEFAULT_MODEL, preview_mode=False)
        result = engine.create_lesson(
            profile,
            "Python recursion",
            "No prior sessions",
        )
        assessment = engine.evaluate(
            profile,
            result.lesson,
            result.quiz,
            wrong_answers,
            attempt=1,
        )
        remediation = engine.create_remediation(result.lesson, assessment)

    assert result.plan.topic == "Python recursion"
    assert len(result.quiz.questions) == 4
    assert [question.question_id for question in result.quiz.questions] == [
        "Q1",
        "Q2",
        "Q3",
        "Q4",
    ]
    assert assessment.decision.action == "reteach"
    assert [question.question_id for question in remediation.quiz.questions] == ["R1", "R2"]


def test_student_memory_is_case_insensitive_and_persistent(tmp_path) -> None:
    memory = StudentMemory(tmp_path / "leo.db")
    profile = StudentProfile(name="Asif", level="Beginner", goal="Learn SQL joins")
    report = EvaluationReport(
        question_results=[
            QuestionEvaluation(
                question_id="Q1",
                earned_points=10,
                max_points=10,
                verdict="correct",
                feedback="Strong",
                ideal_answer="Inner join",
            )
        ],
        mastered_concepts=["inner joins"],
        overall_feedback="Good",
        total_earned=10,
        total_possible=10,
        score_percent=100,
    )

    memory.save(profile, "SQL joins", report)

    history = memory.recent("asif")
    assert history[0]["topic"] == "SQL joins"
    assert "inner joins" in memory.prompt_context("ASIF")
