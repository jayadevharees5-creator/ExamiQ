from typing import List

SYSTEM_KNOWLEDGE_PROMPT = """You are a master academic examiner and curriculum specialist. Generate rigorous, precise, curriculum-grounded assessment questions based on domain knowledge.

RULES & STANDARDS:
1. ACCURACY: Every question must be unambiguous, factually true, and aligned with standard university/industry benchmarks.
2. DIFFICULTY CALIBRATION:
   - Easy: Foundational knowledge, definitions, core syntax/formulas.
   - Medium: Applied understanding, scenario analysis, multi-step deduction.
   - Hard: Advanced edge cases, system design implications, nuanced architectural trade-offs.
   - If 'Mixed' difficulty is requested, produce an intentional academic distribution (~30% Easy, ~50% Medium, ~20% Hard) and tag each question's 'difficulty' field accordingly.
3. BLOOM'S TAXONOMY: Map each question to its appropriate cognitive level (Remember, Understand, Apply, Analyze, Evaluate, Create).
4. MARKS ALLOCATION: Include realistic academic marks (e.g. 1-2 marks for MCQ/True-False/Fill-in-blanks, 5 marks for Short Answer, 10-15 marks for Long Answer).
5. OPTIONS QUALITY: For MCQs, distractors must be plausible, academically sensible, and grammatically parallel. Exactly one correct answer.
6. ANSWER QUALITY (CRITICAL):
   - For MCQs: correct_answer must exactly match one of the options. Explanation must justify why.
   - For Short Answer Questions: correct_answer MUST be a detailed 3-5 sentence response with key facts, definitions, and relevant explanations. NOT just a single word.
   - For Long Answer Questions: correct_answer MUST be a comprehensive 8-15 sentence structured response with definitions, explanations, examples, and academic depth. Use numbered points where appropriate.
   - For True/False: correct_answer must be "True" or "False" with clear justification.
   - For Fill in the Blanks: correct_answer must be the exact word(s) that fill the blank.
7. STRICT DIVERSITY & ZERO REPETITION (MANDATORY):
   - Every single question MUST test a DIFFERENT concept, sub-topic, formula, or principle.
   - Under NO circumstances should questions be repeated, rephrased, or duplicated across regenerations or within the same set.
   - Explore fresh and unasked aspects of the curriculum on every generation.
8. Return exclusively a valid JSON object matching the schema. No markdown fences, no conversational preamble.
"""

def build_knowledge_user_prompt(
    topic: str,
    target_audience: str,
    question_types: List[str],
    difficulty: str,
    count: int,
    include_answers: bool,
    include_explanations: bool,
    include_hints: bool,
    additional_instructions: str = ""
) -> str:
    types_str = ", ".join(question_types)
    ans_instr = "Include the correct answer and a concise 1-2 sentence explanation." if include_answers else "Omit answer and explanation."
    hint_instr = "Provide a concise 1-sentence conceptual hint for each question." if include_hints else "Omit hints."

    if difficulty.strip().lower() == "mixed":
        diff_spec = "MIXED DIFFICULTY: Provide a balanced academic blend of ~30% Easy, ~50% Medium, and ~20% Hard questions. In the output JSON, set each question's 'difficulty' field to its specific level ('Easy', 'Medium', or 'Hard')."
    else:
        diff_spec = f"DIFFICULTY LEVEL: {difficulty}. Ensure all questions strictly maintain this difficulty standard."

    prompt = f"""
TOPIC: {topic}
TARGET AUDIENCE: {target_audience}
QUESTION TYPES: {types_str}
{diff_spec}
QUANTITY: EXACTLY {count} distinct questions (CRITICAL: You must generate all {count} questions numbered 1 through {count}. Never truncate, combine, or stop early).
ANSWER POLICY: {ans_instr}
HINT POLICY: {hint_instr}
ADDITIONAL INSTRUCTIONS: {additional_instructions or "None"}

OUTPUT SCHEMA (JSON):
{{
  "topic": "{topic}",
  "questions": [
    {{
      "id": 1,
      "type": "Multiple Choice Questions (MCQ)",
      "difficulty": "Easy",
      "blooms_level": "Understand",
      "marks": 2,
      "question": "Question text here?",
      "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
      "correct_answer": "A) Option 1",
      "explanation": "Concise 1-2 sentence explanation of why this answer is correct.",
      "hint": "Brief conceptual hint."
    }}
  ]
}}

CRITICAL REQUIREMENT: Return the questions array with EXACTLY {count} distinct questions (numbered 1 through {count}). Complete all {count} questions fully without cutting short.
"""
    return prompt

