from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

LearnerLevel = Literal["Beginner", "Intermediate", "Advanced"]
QuestionType = Literal["multiple_choice", "true_false", "short_answer", "application"]
Verdict = Literal["correct", "partially_correct", "incorrect", "unanswered"]
RouteAction = Literal["complete", "reteach", "clarify", "error"]


class StudentProfile(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    level: LearnerLevel
    goal: str = Field(min_length=3, max_length=240)

    @field_validator("name", "goal")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(value.split())


class LearningPlan(BaseModel):
    topic: str = Field(min_length=2, max_length=160)
    learner_level: LearnerLevel
    goal_summary: str = Field(min_length=3)
    objectives: list[str] = Field(min_length=3, max_length=5)
    teaching_strategy: str = Field(min_length=3)
    quiz_focus: list[str] = Field(min_length=2, max_length=5)
    clarification_needed: bool = False
    clarification_question: str | None = None

    @model_validator(mode="after")
    def require_clarification_question(self) -> LearningPlan:
        if self.clarification_needed and not self.clarification_question:
            raise ValueError("A clarification question is required")
        return self


class LessonSection(BaseModel):
    heading: str
    explanation: str
    example: str | None = None


class LessonPackage(BaseModel):
    title: str
    hook: str
    objectives: list[str] = Field(min_length=3, max_length=5)
    sections: list[LessonSection] = Field(min_length=2, max_length=6)
    analogy: str
    worked_example: str
    misconceptions: list[str] = Field(min_length=1, max_length=4)
    key_takeaways: list[str] = Field(min_length=2, max_length=6)


class QuizQuestion(BaseModel):
    question_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    concept: str
    question_type: QuestionType
    prompt: str
    options: list[str] = Field(default_factory=list, max_length=6)
    correct_answer: str
    explanation: str
    scoring_guide: str
    max_points: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def validate_options(self) -> QuizQuestion:
        if self.question_type in {"multiple_choice", "true_false"} and len(self.options) < 2:
            raise ValueError("Choice questions require at least two options")
        return self


class QuizPackage(BaseModel):
    title: str
    instructions: str
    questions: list[QuizQuestion] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def unique_question_ids(self) -> QuizPackage:
        ids = [question.question_id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Question IDs must be unique")
        return self

    def public_payload(self) -> dict:
        return {
            "title": self.title,
            "instructions": self.instructions,
            "questions": [
                question.model_dump(exclude={"correct_answer", "explanation", "scoring_guide"})
                for question in self.questions
            ],
        }


class QuestionEvaluation(BaseModel):
    question_id: str
    earned_points: float = Field(ge=0)
    max_points: float = Field(gt=0)
    verdict: Verdict
    feedback: str
    ideal_answer: str


class EvaluationReport(BaseModel):
    question_results: list[QuestionEvaluation] = Field(min_length=1)
    strengths: list[str] = Field(default_factory=list)
    mastered_concepts: list[str] = Field(default_factory=list)
    weak_concepts: list[str] = Field(default_factory=list)
    overall_feedback: str
    total_earned: float = Field(default=0, ge=0)
    total_possible: float = Field(default=0, ge=0)
    score_percent: float = Field(default=0, ge=0, le=100)


class RoutingDecision(BaseModel):
    action: RouteAction
    rationale: str
    weak_concepts: list[str] = Field(default_factory=list)
    student_message: str


class TeachingBundle(BaseModel):
    plan: LearningPlan
    lesson: LessonPackage
    quiz: QuizPackage


class AssessmentBundle(BaseModel):
    report: EvaluationReport
    decision: RoutingDecision


class RemediationBundle(BaseModel):
    lesson: LessonPackage
    quiz: QuizPackage


class AgentEvent(BaseModel):
    agent: str
    status: Literal["working", "completed", "failed"]
    message: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


def finalize_evaluation(report: EvaluationReport, quiz: QuizPackage) -> EvaluationReport:
    """Make grading totals deterministic and aligned with the source quiz."""
    submitted = {item.question_id: item for item in report.question_results}
    normalized: list[QuestionEvaluation] = []

    for question in quiz.questions:
        item = submitted.get(question.question_id)
        if item is None:
            item = QuestionEvaluation(
                question_id=question.question_id,
                earned_points=0,
                max_points=question.max_points,
                verdict="unanswered",
                feedback="No evaluation was returned for this answer.",
                ideal_answer=question.correct_answer,
            )
        normalized.append(
            item.model_copy(
                update={
                    "earned_points": min(max(item.earned_points, 0), question.max_points),
                    "max_points": question.max_points,
                }
            )
        )

    total_earned = sum(item.earned_points for item in normalized)
    total_possible = sum(item.max_points for item in normalized)
    score = round((total_earned / total_possible) * 100, 1) if total_possible else 0

    return report.model_copy(
        update={
            "question_results": normalized,
            "total_earned": total_earned,
            "total_possible": total_possible,
            "score_percent": score,
        }
    )


def required_route(report: EvaluationReport, attempt: int, max_attempts: int = 2) -> RouteAction:
    if attempt < max_attempts and (report.score_percent < 70 or report.weak_concepts):
        return "reteach"
    return "complete"

