from typing import Dict, Any, List

class QuestionValidator:
    """
    Validates and normalizes questions from LLM generation.
    Ensures safe rendering across UI components.
    """

    @staticmethod
    def sanitize_question(q: Dict[str, Any], idx: int) -> Dict[str, Any]:
        """
        Ensures all standard fields exist with proper fallbacks.
        """
        return {
            "id": q.get("id", idx),
            "type": q.get("type", "Multiple Choice Questions (MCQ)"),
            "difficulty": q.get("difficulty", "Medium"),
            "title": q.get("title", ""),
            "question": q.get("question", "No question text provided."),
            "options": q.get("options", []),
            "correct_answer": q.get("correct_answer", ""),
            "explanation": q.get("explanation", ""),
            "hint": q.get("hint", ""),
            "hints": q.get("hints", []),
            "source_document": q.get("source_document", ""),
            "page_number": q.get("page_number", None),
            "marks": q.get("marks", 2 if "MCQ" in q.get("type", "") else 5),
            "blooms_level": q.get("blooms_level", "Apply"),
            # Coding question fields
            "input_format": q.get("input_format", ""),
            "output_format": q.get("output_format", ""),
            "constraints": q.get("constraints", []),
            "sample_input": q.get("sample_input", ""),
            "sample_output": q.get("sample_output", ""),
            "solution_code": q.get("solution_code", ""),
            "time_complexity": q.get("time_complexity", ""),
            "space_complexity": q.get("space_complexity", "")
        }

    @classmethod
    def validate_and_normalize(cls, raw_data: Any) -> List[Dict[str, Any]]:
        """
        Extracts questions array and normalizes each item.
        """
        if isinstance(raw_data, list):
            questions_list = raw_data
        elif isinstance(raw_data, dict):
            questions_list = (
                raw_data.get("questions")
                or raw_data.get("items")
                or raw_data.get("data")
                or raw_data.get("question_paper")
                or raw_data.get("exam_paper")
                or []
            )
        else:
            return []

        if not isinstance(questions_list, list):
            return []

        normalized = []
        for i, q in enumerate(questions_list, start=1):
            if isinstance(q, dict):
                normalized.append(cls.sanitize_question(q, i))

        return normalized
