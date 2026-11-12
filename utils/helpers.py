from typing import Dict, Any, List

def format_question_for_clipboard(q: Dict[str, Any], idx: int = 1) -> str:
    """Formats a single question dictionary into clean text for copying."""
    lines = [f"Q{idx}: {q.get('question', '')}"]
    if q.get("options"):
        for opt in q["options"]:
            lines.append(f"  {opt}")
    if q.get("correct_answer"):
        lines.append(f"Answer: {q['correct_answer']}")
    if q.get("explanation"):
        lines.append(f"Explanation: {q['explanation']}")
    if q.get("source_document"):
        p = f" (Page {q['page_number']})" if q.get("page_number") else ""
        lines.append(f"Source: {q['source_document']}{p}")
    return "\n".join(lines)

def format_all_questions_for_clipboard(questions: List[Dict[str, Any]]) -> str:
    """Formats all questions into clean text."""
    blocks = []
    for i, q in enumerate(questions, start=1):
        blocks.append(format_question_for_clipboard(q, i))
    return "\n\n" + ("=" * 40) + "\n\n".join(blocks)
