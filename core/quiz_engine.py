from typing import List, Dict, Any, Optional

class QuizEngine:
    """
    Manages quiz progression, user responses, score tracking,
    and retry state for interactive quiz mode.
    """

    def __init__(self, questions: List[Dict[str, Any]]):
        self.questions = questions
        self.current_index: int = 0
        self.user_answers: Dict[int, str] = {}  # {q_index: user_choice_or_text}
        self.submitted: Dict[int, bool] = {}    # {q_index: True}
        self.is_completed: bool = False

    def get_current_question(self) -> Optional[Dict[str, Any]]:
        if 0 <= self.current_index < len(self.questions):
            return self.questions[self.current_index]
        return None

    def record_answer(self, index: int, answer: str) -> None:
        self.user_answers[index] = answer
        self.submitted[index] = True

    def next_question(self) -> None:
        if self.current_index < len(self.questions) - 1:
            self.current_index += 1
        else:
            self.is_completed = True

    def prev_question(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1

    def is_answer_correct(self, index: int) -> bool:
        if index not in self.user_answers or index >= len(self.questions):
            return False
        user_ans = str(self.user_answers[index]).strip().lower()
        correct_ans = str(self.questions[index].get("correct_answer", "")).strip().lower()

        # Handle MCQ letter match (e.g. user selected "B) Binary Search" and correct is "B) Binary Search" or "B")
        if user_ans == correct_ans:
            return True
        if len(user_ans) >= 2 and user_ans[:2] == correct_ans[:2]:
            return True
        # Check if first character (A, B, C, D) matches
        if len(user_ans) > 0 and len(correct_ans) > 0 and user_ans[0] == correct_ans[0] and user_ans[0] in ['a', 'b', 'c', 'd']:
            return True
        return False

    def calculate_score(self) -> Dict[str, Any]:
        total = len(self.questions)
        correct = sum(1 for i in range(total) if self.is_answer_correct(i))
        percentage = round((correct / total * 100), 1) if total > 0 else 0
        return {
            "total": total,
            "correct": correct,
            "incorrect": total - correct,
            "percentage": percentage
        }

    def get_incorrect_questions(self) -> List[Dict[str, Any]]:
        incorrect = []
        for i, q in enumerate(self.questions):
            if not self.is_answer_correct(i):
                incorrect.append(q)
        return incorrect

    def reset_for_retry(self, questions_to_retry: Optional[List[Dict[str, Any]]] = None) -> None:
        """Reset state, optionally filtering to only incorrect questions."""
        if questions_to_retry is not None:
            self.questions = questions_to_retry
        self.current_index = 0
        self.user_answers.clear()
        self.submitted.clear()
        self.is_completed = False
