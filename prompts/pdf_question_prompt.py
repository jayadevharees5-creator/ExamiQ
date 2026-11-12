from typing import List

SYSTEM_PDF_PROMPT = """You are a premier university examination paper generator. Generate rigorous, precise, curriculum-grounded assessment questions based strictly on the provided context.

CORE STANDARDS:
1. GROUNDING: Use facts, concepts, definitions, and theorems from the document context.
2. DIFFICULTY CALIBRATION:
   - Easy: Direct recall, definition, core formula, fundamental terminology.
   - Medium: Conceptual understanding, calculation, application, scenario diagnosis.
   - Hard: In-depth analysis, synthesis of multiple sections, edge-case evaluation.
   - If 'Mixed' difficulty is requested, produce an intentional academic distribution (~30% Easy, ~50% Medium, ~20% Hard) and tag each question's 'difficulty' field accordingly.
3. BLOOM'S TAXONOMY: Map each question to its appropriate cognitive level (Remember, Understand, Apply, Analyze, Evaluate, Create).
4. MARKS ALLOCATION: Include realistic academic marks (e.g. 1-2 marks for MCQ/True-False/Fill-in-blanks, 5 marks for Short Answer, 10-15 marks for Long Answer).
5. OPTIONS QUALITY: For MCQs, distractors must be plausible, academically sensible, and grammatically parallel. Exactly one correct answer.
6. ANSWER QUALITY (CRITICAL):
   - For MCQs: correct_answer must exactly match one of the options. Explanation must justify why.
   - For Short Answer Questions: correct_answer MUST be a detailed 3-5 sentence response that fully answers the question with key facts, definitions, and relevant context from the document. NOT just a single word or phrase.
   - For Long Answer Questions: correct_answer MUST be a comprehensive 8-15 sentence structured response with definitions, explanations, examples, and proper academic depth. Organize with numbered points where appropriate.
   - For True/False: correct_answer must be "True" or "False" with a clear justification in the explanation.
   - For Fill in the Blanks: correct_answer must be the exact word(s) that fill the blank.
7. STRICT DIVERSITY & ZERO REPETITION (MANDATORY):
   - Every single question MUST test a DIFFERENT concept, section, formula, theorem, or equation from the document.
   - Under NO circumstances should questions be repeated, rephrased, or duplicated across regenerations or within the same set.
   - Ground every question deeply in distinct portions of the retrieved context.
8. Return exclusively a valid JSON object matching the schema. No markdown fences, no conversational preamble.
"""

def build_pdf_user_prompt(
    context_text: str,
    unit_info: str,
    topic: str,
    question_types: List[str],
    difficulty: str,
    count: int,
    include_answers: bool,
    include_explanations: bool,
    include_sources: bool,
    language: str,
    additional_instructions: str = ""
) -> str:
    types_str = ", ".join(question_types)
    ans_instr = "Include the correct answer and a step-by-step grounded explanation referencing the text." if include_answers else "Omit the answer and explanation."
    lang_instr = "Generate in Tamil-English (Tunglish - English academic terms mixed with conversational Tamil in English script)." if "Tamil" in language else "Generate in professional, grammatically clear academic English."

    if difficulty.strip().lower() == "mixed":
        diff_spec = "MIXED DIFFICULTY: Provide a balanced academic blend of ~30% Easy, ~50% Medium, and ~20% Hard questions. In the output JSON, set each question's 'difficulty' field to its specific level ('Easy', 'Medium', or 'Hard')."
    else:
        diff_spec = f"DIFFICULTY LEVEL: {difficulty}. Ensure all questions strictly maintain this difficulty standard."

    scope_spec = f"Target Scope / Unit: '{unit_info}'" if unit_info and unit_info.strip() else "Target Scope: Entire uploaded study material (no specific chapter restriction)."

    prompt = f"""
RETRIEVED DOCUMENT CONTEXT:
========================================
{context_text}
========================================

EXAM SPECIFICATION:
- {scope_spec}
- Target Topic / Focus: {topic or "Key concepts and principles across the material"}
- Question Formats: {types_str}
- {diff_spec}
- Question Count: EXACTLY {count} distinct questions (numbered 1 through {count}). Never truncate, combine, or stop early.
- Language: {lang_instr}
- Answer & Explanation Policy: {ans_instr}
- Include Citation (Source document & page): {include_sources}
- Examiner Notes: {additional_instructions or "None"}

OUTPUT SCHEMA (JSON):
{{
  "insufficient_context": false,
  "reason": "",
  "questions": [
    {{
      "id": 1,
      "type": "Multiple Choice Questions (MCQ)",
      "difficulty": "Easy",
      "blooms_level": "Understand",
      "marks": 2,
      "question": "Clear, grammatically correct question text?",
      "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
      "correct_answer": "A) Option 1",
      "explanation": "Detailed explanation showing why A is correct based on the text.",
      "source_document": "DocumentName.pdf",
      "page_number": 1
    }}
  ]
}}

CRITICAL REQUIREMENT: Return the questions array with EXACTLY {count} distinct questions (numbered 1 through {count}). Complete all {count} questions fully without cutting short.
"""
    return prompt

