# Leo demo video script

Target duration: **4 minutes 30 seconds**

Use live CrewAI mode for the recording. Preview mode is only for interface testing.

## Before recording

- Add the provider key to `.env`.
- Start the app with `streamlit run app.py`.
- Use a new learner name so the opening state is clean.
- Prepare the GitHub repository and README in another tab.
- Use the topic **Python recursion** at beginner level.
- Learning goal: **Trace recursive functions and explain the base case.**

## 0:00–0:25 — Problem and product

Say:

> Most AI tutors behave like one chatbot doing everything. Leo separates planning, teaching, assessment, and evaluation into four specialist agents with explicit handoffs.

Show the home screen and point to the four agent cards.

## 0:25–0:50 — Architecture

Open the README architecture diagram.

Say:

> Leo uses a sequential CrewAI process because teaching has a natural order. The Coordinator creates the plan, the Explainer teaches it, the Quiz Master assesses only taught material, and the Evaluator sends evidence back to the Coordinator.

Briefly point to `LearningPlan`, `LessonPackage`, `QuizPackage`, and `EvaluationReport`.

## 0:50–1:20 — Start a live session

In the sidebar:

- Enter the learner name.
- Choose Beginner.
- Enter Python recursion.
- Enter the prepared goal.
- Disable preview mode.
- Confirm the configured CrewAI model.
- Click **Build my learning path**.

Show the live status changing between Coordinator, Explainer, and Quiz Master.

## 1:20–2:00 — Lesson and handoffs

Scroll through:

- Learning objectives
- Explanation sections
- Analogy
- Worked example
- Misconceptions

Open **Agent activity** and show that the Coordinator handed a plan to the Explainer, then the lesson moved to the Quiz Master.

Say:

> The interface shows auditable handoff summaries, but it does not expose private chain-of-thought.

Click **I’m ready for the quiz** to demonstrate the human checkpoint.

## 2:00–2:40 — Structured quiz

Point out:

- Question IDs
- Concept labels
- Point values
- Mixed question types

Answer two questions well and intentionally answer the base-case question incorrectly. Submit.

## 2:40–3:25 — Evaluation and feedback loop

Show:

- Percentage score
- Total points
- Per-question feedback
- Ideal answers
- Weak concepts
- Coordinator’s routing message

Say:

> The final percentage is calculated in Python from validated question scores. The language model cannot invent the total.

Show the targeted lesson created from the weak concepts and the two-question follow-up quiz.

## 3:25–3:55 — Complete remediation

Answer both follow-up questions correctly and submit.

Show:

- First-attempt score
- Follow-up score
- Final evaluation
- Session saved to learner memory

## 3:55–4:20 — Memory and graceful handling

Start another session with the same learner name.

Show the remembered session in the sidebar. Explain that recent topics, scores, mastered concepts, and weak concepts are passed into the next Coordinator prompt.

Mention bounded retries and the one-cycle remediation limit.

## 4:20–4:30 — Close

Show the GitHub repository, tests, and CI badge.

Say:

> Leo demonstrates multi-agent collaboration, typed handoffs, persistent memory, human intervention, and adaptive re-teaching in one complete learning session.

