from __future__ import annotations

import json
import os
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path
from typing import TypeVar

import yaml
from crewai import Agent, Crew, LLM, Process, Task
from dotenv import load_dotenv
from pydantic import BaseModel

from .models import (
    AgentEvent,
    AssessmentBundle,
    EvaluationReport,
    LearningPlan,
    LessonPackage,
    LessonSection,
    QuestionEvaluation,
    QuizPackage,
    QuizQuestion,
    RemediationBundle,
    RoutingDecision,
    StudentProfile,
    TeachingBundle,
    finalize_evaluation,
    required_route,
)

load_dotenv()

EventCallback = Callable[[AgentEvent], None]
ModelT = TypeVar("ModelT", bound=BaseModel)
DEFAULT_MODEL = "gemini/gemini-3.1-flash-lite"
GROQ_MODEL = "groq/openai/gpt-oss-120b"


def quiz_shape_guardrail(expected_count: int, prefix: str):
    """Return a CrewAI guardrail for the two quiz shapes used by Leo."""

    def validate(output):
        try:
            quiz = (
                QuizPackage.model_validate(output.pydantic)
                if output.pydantic is not None
                else QuizPackage.model_validate_json(output.raw)
            )
        except Exception as error:
            return False, f"Quiz output did not match QuizPackage: {error}"

        expected_ids = {f"{prefix}{index}" for index in range(1, expected_count + 1)}
        actual_ids = {question.question_id for question in quiz.questions}
        if len(quiz.questions) != expected_count or actual_ids != expected_ids:
            return (
                False,
                f"Return exactly {expected_count} questions with IDs "
                f"{', '.join(sorted(expected_ids))}.",
            )
        return True, output

    return validate


def evaluation_coverage_guardrail(quiz: QuizPackage):
    """Require one and only one evaluation for every source question."""

    def validate(output):
        try:
            report = (
                EvaluationReport.model_validate(output.pydantic)
                if output.pydantic is not None
                else EvaluationReport.model_validate_json(output.raw)
            )
        except Exception as error:
            return False, f"Evaluation output did not match EvaluationReport: {error}"

        expected_ids = {question.question_id for question in quiz.questions}
        actual_ids = {item.question_id for item in report.question_results}
        if len(report.question_results) != len(expected_ids) or actual_ids != expected_ids:
            return False, "Evaluate every quiz question exactly once using its original question_id."
        return True, output

    return validate


class ClarificationRequired(ValueError):
    pass


class TutorEngine:
    """Runs the real CrewAI tutor workflow or a deterministic UI preview."""

    def __init__(
        self,
        model: str | None = None,
        *,
        preview_mode: bool = False,
        on_event: EventCallback | None = None,
    ) -> None:
        self.model_name = model or os.getenv("LEO_MODEL", DEFAULT_MODEL)
        self.preview_mode = preview_mode
        self.on_event = on_event
        config_dir = Path(__file__).parent / "config"
        self.agents_config = self._load_yaml(config_dir / "agents.yaml")
        self.tasks_config = self._load_yaml(config_dir / "tasks.yaml")
        self.llm = None if preview_mode else LLM(model=self.model_name, temperature=0.2)

    @staticmethod
    def _load_yaml(path: Path) -> dict:
        with path.open(encoding="utf-8") as file:
            return yaml.safe_load(file)

    def _emit(self, agent: str, status: str, message: str) -> None:
        if self.on_event:
            self.on_event(AgentEvent(agent=agent, status=status, message=message))

    def _agent(self, name: str, temperature: float = 0.2) -> Agent:
        llm = self.llm
        if temperature != 0.2:
            llm = LLM(model=self.model_name, temperature=temperature)
        return Agent(
            config=self.agents_config[name],
            llm=llm,
            max_iter=4,
            max_execution_time=120,
        )

    def _callback(self, agent: str, message: str, next_agent: str | None = None):
        def complete(_output) -> None:
            self._emit(agent, "completed", message)
            if next_agent:
                self._emit(next_agent, "working", f"{next_agent} received the handoff.")

        return complete

    @staticmethod
    def _task_output(task: Task, model: type[ModelT]) -> ModelT:
        output = task.output
        if output is None:
            raise RuntimeError(f"No output returned for {task.description[:40]}")
        if output.pydantic is not None:
            return model.model_validate(output.pydantic)
        if output.json_dict is not None:
            return model.model_validate(output.json_dict)
        return model.model_validate_json(output.raw)

    @staticmethod
    def _clarification_answered_by_profile(
        plan: LearningPlan,
        profile: StudentProfile,
    ) -> bool:
        """Return whether the Coordinator asked for information already collected."""

        if not plan.clarification_needed or not plan.clarification_question:
            return False
        question = plan.clarification_question.casefold()
        known_level = (
            "experience",
            "prior knowledge",
            "skill level",
            "start from",
            "absolute zero",
            "beginner",
            "intermediate",
            "advanced",
        )
        known_goal = ("your goal", "hope to achieve", "want to achieve")
        return any(term in question for term in known_level) or (
            bool(profile.goal) and any(term in question for term in known_goal)
        )

    def create_lesson(
        self,
        profile: StudentProfile,
        topic: str,
        memory_context: str,
    ) -> TeachingBundle:
        if self.preview_mode:
            return self._preview_lesson(profile, topic, memory_context)

        coordinator = self._agent("coordinator", temperature=0.1)
        explainer = self._agent("explainer", temperature=0.3)
        quiz_master = self._agent("quiz_master", temperature=0.2)

        plan_task = Task(
            config=self.tasks_config["planning_task"],
            agent=coordinator,
            output_pydantic=LearningPlan,
            callback=self._callback(
                "Coordinator",
                "Learning plan validated and delegated.",
                "Explainer",
            ),
            guardrail_max_retries=2,
        )
        lesson_task = Task(
            config=self.tasks_config["explanation_task"],
            agent=explainer,
            context=[plan_task],
            output_pydantic=LessonPackage,
            callback=self._callback(
                "Explainer",
                "Adaptive lesson completed and handed to assessment.",
                "Quiz Master",
            ),
            guardrail_max_retries=2,
        )
        quiz_task = Task(
            config=self.tasks_config["quiz_task"],
            agent=quiz_master,
            context=[plan_task, lesson_task],
            output_pydantic=QuizPackage,
            guardrail=quiz_shape_guardrail(4, "Q"),
            callback=self._callback(
                "Quiz Master",
                "Structured quiz created from the taught material.",
            ),
            guardrail_max_retries=2,
        )

        self._emit("Coordinator", "working", "Analyzing the request and student memory.")
        Crew(
            agents=[coordinator, explainer, quiz_master],
            tasks=[plan_task, lesson_task, quiz_task],
            process=Process.sequential,
            verbose=False,
            tracing=False,
        ).kickoff(
            inputs={
                "student_name": profile.name,
                "level": profile.level,
                "goal": profile.goal,
                "topic": topic,
                "memory_context": memory_context,
            }
        )

        plan = self._task_output(plan_task, LearningPlan)
        if self._clarification_answered_by_profile(plan, profile):
            plan = plan.model_copy(
                update={
                    "clarification_needed": False,
                    "clarification_question": None,
                }
            )
            self._emit(
                "Coordinator",
                "completed",
                "The selected level and learning goal resolved the requested context.",
            )
        if plan.clarification_needed:
            raise ClarificationRequired(
                plan.clarification_question or "Please clarify the topic before continuing."
            )
        return TeachingBundle(
            plan=plan,
            lesson=self._task_output(lesson_task, LessonPackage),
            quiz=self._task_output(quiz_task, QuizPackage),
        )

    def evaluate(
        self,
        profile: StudentProfile,
        lesson: LessonPackage,
        quiz: QuizPackage,
        answers: dict[str, str],
        *,
        attempt: int,
    ) -> AssessmentBundle:
        if self.preview_mode:
            return self._preview_evaluation(quiz, answers, attempt)

        evaluator = self._agent("evaluator", temperature=0.1)
        coordinator = self._agent("coordinator", temperature=0.1)
        evaluation_task = Task(
            config=self.tasks_config["evaluation_task"],
            agent=evaluator,
            output_pydantic=EvaluationReport,
            guardrail=evaluation_coverage_guardrail(quiz),
            callback=self._callback(
                "Evaluator",
                "Answers graded and learning gaps identified.",
                "Coordinator",
            ),
            guardrail_max_retries=2,
        )
        routing_task = Task(
            config=self.tasks_config["routing_task"],
            agent=coordinator,
            context=[evaluation_task],
            output_pydantic=RoutingDecision,
            callback=self._callback(
                "Coordinator",
                "Evaluation reviewed and the next learning step selected.",
            ),
            guardrail_max_retries=2,
        )

        self._emit("Evaluator", "working", "Comparing each answer with its scoring guide.")
        Crew(
            agents=[evaluator, coordinator],
            tasks=[evaluation_task, routing_task],
            process=Process.sequential,
            verbose=False,
            tracing=False,
        ).kickoff(
            inputs={
                "student_name": profile.name,
                "lesson_json": lesson.model_dump_json(indent=2),
                "quiz_json": quiz.model_dump_json(indent=2),
                "answers_json": json.dumps(answers, indent=2),
                "attempt": attempt,
            }
        )

        report = finalize_evaluation(
            self._task_output(evaluation_task, EvaluationReport),
            quiz,
        )
        decision = self._task_output(routing_task, RoutingDecision)
        enforced_action = required_route(report, attempt)
        route_changed = decision.action != enforced_action
        decision = decision.model_copy(
            update={
                "action": enforced_action,
                "weak_concepts": report.weak_concepts,
                "rationale": (
                    "The deterministic learning threshold selected this route."
                    if route_changed
                    else decision.rationale
                ),
                "student_message": (
                    "Let’s strengthen the flagged concepts with a shorter targeted review."
                    if route_changed and enforced_action == "reteach"
                    else "You completed this learning path. Your session summary is ready."
                    if route_changed
                    else decision.student_message
                ),
            }
        )
        return AssessmentBundle(report=report, decision=decision)

    def create_remediation(
        self,
        lesson: LessonPackage,
        assessment: AssessmentBundle,
    ) -> RemediationBundle:
        if self.preview_mode:
            return self._preview_remediation(lesson, assessment)

        explainer = self._agent("explainer", temperature=0.25)
        quiz_master = self._agent("quiz_master", temperature=0.15)
        lesson_task = Task(
            config=self.tasks_config["remediation_lesson_task"],
            agent=explainer,
            output_pydantic=LessonPackage,
            callback=self._callback(
                "Explainer",
                "Targeted re-teaching completed.",
                "Quiz Master",
            ),
            guardrail_max_retries=2,
        )
        quiz_task = Task(
            config=self.tasks_config["remediation_quiz_task"],
            agent=quiz_master,
            context=[lesson_task],
            output_pydantic=QuizPackage,
            guardrail=quiz_shape_guardrail(2, "R"),
            callback=self._callback(
                "Quiz Master",
                "Follow-up quiz created for the weak concepts.",
            ),
            guardrail_max_retries=2,
        )

        self._emit(
            "Explainer",
            "working",
            "Received the Evaluator's weak-concept handoff.",
        )
        Crew(
            agents=[explainer, quiz_master],
            tasks=[lesson_task, quiz_task],
            process=Process.sequential,
            verbose=False,
            tracing=False,
        ).kickoff(
            inputs={
                "weak_concepts": ", ".join(assessment.report.weak_concepts),
                "evaluation_json": assessment.report.model_dump_json(indent=2),
                "lesson_json": lesson.model_dump_json(indent=2),
            }
        )
        return RemediationBundle(
            lesson=self._task_output(lesson_task, LessonPackage),
            quiz=self._task_output(quiz_task, QuizPackage),
        )

    # Preview mode keeps the public UI testable without pretending to be an LLM run.
    def _preview_lesson(
        self,
        profile: StudentProfile,
        topic: str,
        memory_context: str,
    ) -> TeachingBundle:
        self._emit("Coordinator", "working", "Reviewing the learner request.")
        objectives = [
            f"Explain the central idea behind {topic}",
            f"Recognize when {topic} is useful",
            f"Apply {topic} in a simple example",
            f"Avoid a common mistake related to {topic}",
        ]
        plan = LearningPlan(
            topic=topic,
            learner_level=profile.level,
            goal_summary=profile.goal,
            objectives=objectives,
            teaching_strategy="Build intuition first, then apply it in a worked example.",
            quiz_focus=[objectives[0], objectives[2], objectives[3]],
        )
        self._emit("Coordinator", "completed", "Created a four-objective learning plan.")
        self._emit("Explainer", "working", "Received the Coordinator's LearningPlan.")

        lesson = self._preview_lesson_content(topic, objectives)
        self._emit("Explainer", "completed", "Prepared an adaptive lesson with examples.")
        self._emit("Quiz Master", "working", "Received the lesson and learning objectives.")
        quiz = QuizPackage(
            title=f"{topic}: knowledge check",
            instructions="Answer all four questions. Thoughtful partial answers can earn credit.",
            questions=[
                QuizQuestion(
                    question_id="Q1",
                    concept=f"{topic} fundamentals",
                    question_type="multiple_choice",
                    prompt=f"Which statement best describes the purpose of {topic}?",
                    options=[
                        "It provides a structured way to solve a specific kind of problem",
                        "It removes the need to understand the problem",
                        "It guarantees every solution is correct",
                        "It is only useful for experts",
                    ],
                    correct_answer="It provides a structured way to solve a specific kind of problem",
                    explanation="A technique is useful because it gives structure, not guarantees.",
                    scoring_guide="10 points for the correct option; otherwise 0.",
                ),
                QuizQuestion(
                    question_id="Q2",
                    concept=f"{topic} application",
                    question_type="short_answer",
                    prompt=f"In one or two sentences, explain when you would use {topic}.",
                    correct_answer=f"Use {topic} when the problem matches its core purpose and constraints.",
                    explanation="A good answer connects the technique to an appropriate problem.",
                    scoring_guide="Award credit for a relevant situation and a clear reason.",
                ),
                QuizQuestion(
                    question_id="Q3",
                    concept=f"{topic} reasoning",
                    question_type="application",
                    prompt=f"Describe one practical example of {topic} and the result you expect.",
                    correct_answer=f"A valid example applies {topic} and clearly states the expected result.",
                    explanation="Application requires both a situation and an expected outcome.",
                    scoring_guide="5 points for a relevant example and 5 for the expected result.",
                ),
                QuizQuestion(
                    question_id="Q4",
                    concept=f"{topic} misconceptions",
                    question_type="true_false",
                    prompt=f"True or false: using {topic} removes the need to check assumptions.",
                    options=["True", "False"],
                    correct_answer="False",
                    explanation="Every technique depends on assumptions and should be checked.",
                    scoring_guide="10 points for False; otherwise 0.",
                ),
            ],
        )
        self._emit("Quiz Master", "completed", "Created four structured questions.")
        return TeachingBundle(plan=plan, lesson=lesson, quiz=quiz)

    @staticmethod
    def _preview_lesson_content(topic: str, objectives: list[str]) -> LessonPackage:
        return LessonPackage(
            title=f"Build a strong intuition for {topic}",
            hook=(
                f"Think of {topic} as a tool in a toolbox: its value comes from "
                "knowing what it does, when it fits, and where it can fail."
            ),
            objectives=objectives,
            sections=[
                LessonSection(
                    heading="The core idea",
                    explanation=(
                        f"{topic} is best understood as a structured approach to a "
                        "particular kind of problem. Start by identifying its inputs, "
                        "its process, and the result it is meant to produce."
                    ),
                    example=f"Describe a small problem, then map each step of {topic} to it.",
                ),
                LessonSection(
                    heading="When to use it",
                    explanation=(
                        "Check that the problem matches the technique's assumptions. "
                        "A strong solution explains why the technique fits instead of "
                        "using it only because it is familiar."
                    ),
                    example="Compare one situation where it fits with one where it does not.",
                ),
                LessonSection(
                    heading="How to reason about it",
                    explanation=(
                        "Work from a simple case, observe the result, and then consider "
                        "edge cases. This turns memorized steps into transferable understanding."
                    ),
                    example="Change one condition in the example and predict what changes.",
                ),
            ],
            analogy=(
                f"Using {topic} is like choosing a map: the map is powerful only when "
                "it represents the place you are actually trying to navigate."
            ),
            worked_example=(
                f"1. Define the problem. 2. Check whether {topic} fits. "
                "3. Apply its steps. 4. Inspect the result. 5. Test an edge case."
            ),
            misconceptions=[
                "Knowing the definition is the same as knowing when to apply it.",
                "The technique works without checking its assumptions.",
            ],
            key_takeaways=[
                f"Understand the purpose of {topic}, not only its definition.",
                "Match the technique to the problem.",
                "Check assumptions and edge cases.",
            ],
        )

    def _preview_evaluation(
        self,
        quiz: QuizPackage,
        answers: dict[str, str],
        attempt: int,
    ) -> AssessmentBundle:
        self._emit("Evaluator", "working", "Checking answers against the private rubric.")
        results: list[QuestionEvaluation] = []
        mastered: list[str] = []
        weak: list[str] = []

        for question in quiz.questions:
            answer = answers.get(question.question_id, "").strip()
            if not answer:
                points, verdict = 0.0, "unanswered"
            elif question.question_type in {"multiple_choice", "true_false"}:
                correct = answer.casefold() == question.correct_answer.casefold()
                points, verdict = (question.max_points, "correct") if correct else (0.0, "incorrect")
            else:
                similarity = SequenceMatcher(
                    None,
                    answer.casefold(),
                    question.correct_answer.casefold(),
                ).ratio()
                if similarity >= 0.62 or len(answer.split()) >= 9:
                    points, verdict = question.max_points, "correct"
                elif similarity >= 0.25 or len(answer.split()) >= 4:
                    points, verdict = question.max_points / 2, "partially_correct"
                else:
                    points, verdict = 0.0, "incorrect"

            if points >= question.max_points * 0.7:
                mastered.append(question.concept)
            else:
                weak.append(question.concept)
            results.append(
                QuestionEvaluation(
                    question_id=question.question_id,
                    earned_points=points,
                    max_points=question.max_points,
                    verdict=verdict,
                    feedback=(
                        "Strong answer—you connected the idea to the question."
                        if points >= question.max_points * 0.7
                        else f"Review this concept. A useful answer is: {question.correct_answer}"
                    ),
                    ideal_answer=question.correct_answer,
                )
            )

        report = finalize_evaluation(
            EvaluationReport(
                question_results=results,
                strengths=list(dict.fromkeys(mastered)),
                mastered_concepts=list(dict.fromkeys(mastered)),
                weak_concepts=list(dict.fromkeys(weak)),
                overall_feedback=(
                    "You showed a useful foundation. Focus on the flagged concepts, "
                    "then try the shorter follow-up."
                    if weak
                    else "Excellent work. You explained and applied the main ideas clearly."
                ),
            ),
            quiz,
        )
        self._emit("Evaluator", "completed", "Grading complete with concept-level feedback.")
        self._emit("Coordinator", "working", "Reviewing the EvaluationReport.")
        action = required_route(report, attempt)
        decision = RoutingDecision(
            action=action,
            rationale=(
                "A targeted review is recommended before completing the session."
                if action == "reteach"
                else "The learning objectives are complete for this session."
            ),
            weak_concepts=report.weak_concepts,
            student_message=(
                "Let’s strengthen the concepts that gave you trouble with a shorter explanation."
                if action == "reteach"
                else "You completed the learning path. Your summary is ready."
            ),
        )
        self._emit("Coordinator", "completed", "Selected the next learning step.")
        return AssessmentBundle(report=report, decision=decision)

    def _preview_remediation(
        self,
        original_lesson: LessonPackage,
        assessment: AssessmentBundle,
    ) -> RemediationBundle:
        weak = assessment.report.weak_concepts or ["the central idea"]
        topic = original_lesson.title.removeprefix("Build a strong intuition for ")
        self._emit("Explainer", "working", "Received weak concepts from the Evaluator.")
        objectives = [
            f"Restate {weak[0]} in simple language",
            f"Apply {weak[0]} to a new situation",
            f"Check the assumptions behind {weak[0]}",
        ]
        lesson = LessonPackage(
            title=f"Targeted review: {topic}",
            hook="A mistake is useful evidence—it tells us exactly where to focus next.",
            objectives=objectives,
            sections=[
                LessonSection(
                    heading="Rebuild the idea",
                    explanation=(
                        f"Focus on {weak[0]}. First identify the problem, then explain why "
                        "the technique fits before describing its steps."
                    ),
                    example="Use the pattern: situation → reason → action → expected result.",
                ),
                LessonSection(
                    heading="Check your reasoning",
                    explanation=(
                        "Ask what assumption your answer relies on and what would happen "
                        "if that assumption changed."
                    ),
                    example="Name one edge case before accepting the result.",
                ),
            ],
            analogy="Treat the feedback like a GPS correction: adjust the route, not the destination.",
            worked_example=(
                "Situation: a matching problem. Reason: the assumptions fit. "
                "Action: apply the method. Result: verify the expected outcome."
            ),
            misconceptions=["Repeating the original wording proves understanding."],
            key_takeaways=[
                "Explain why the method fits.",
                "Connect the action to an expected result.",
                "Check one assumption.",
            ],
        )
        self._emit("Explainer", "completed", "Completed focused re-teaching.")
        self._emit("Quiz Master", "working", "Creating a fresh follow-up check.")
        quiz = QuizPackage(
            title="Targeted follow-up",
            instructions="Use the shorter review to answer both questions.",
            questions=[
                QuizQuestion(
                    question_id="R1",
                    concept=weak[0],
                    question_type="short_answer",
                    prompt="Explain the weak concept in your own words and say why it matters.",
                    correct_answer="A strong answer states the idea clearly and explains why it matters.",
                    explanation="Understanding combines meaning and purpose.",
                    scoring_guide="5 points for meaning and 5 for purpose.",
                ),
                QuizQuestion(
                    question_id="R2",
                    concept=weak[-1],
                    question_type="application",
                    prompt="Give a new example and identify one assumption you would check.",
                    correct_answer="A strong answer gives a relevant example and checks a meaningful assumption.",
                    explanation="Transfer and assumption checking show deeper understanding.",
                    scoring_guide="5 points for the example and 5 for the assumption.",
                ),
            ],
        )
        self._emit("Quiz Master", "completed", "Created two targeted follow-up questions.")
        return RemediationBundle(lesson=lesson, quiz=quiz)
