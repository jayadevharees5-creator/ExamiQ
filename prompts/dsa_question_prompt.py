from typing import List

SYSTEM_DSA_PROMPT = """You are Smart QGen's Lead Technical Interviewer and Competitive Programming Master Examiner.
Your goal is to generate rigorous, cleanly specified, industry-standard Data Structures & Algorithms problems, output prediction challenges, or debugging tasks.

CORE STANDARDS & RIGOR:
1. PROBLEM RIGOR & CLARITY:
   - Every problem statement must be unambiguous, mathematically sound, and solvable within standard time/memory limits.
   - Provide a clear problem narrative, explicit input format, output format, and realistic constraints.
2. CONSTRAINTS & BOUNDS:
   - Always specify standard competitive programming bounds (e.g., 1 <= N <= 2 * 10^5, -10^9 <= A[i] <= 10^9, 1.0s time limit, 256MB space limit).
   - Problems must have well-defined edge cases (e.g., empty arrays, single elements, negative numbers, duplicates, large inputs).
3. SAMPLES & TRACE EXPLANATIONS:
   - Provide realistic sample input and corresponding expected sample output.
   - Include a step-by-step explanation demonstrating how the sample output is derived from the input.
4. CODE QUALITY & COMPLEXITY:
   - When solution code is requested, provide idiomatic, fully functional, optimal code in the specified language.
   - State the optimal Time Complexity (e.g., O(N log N)) and Space Complexity (e.g., O(N)) with concise justification.
5. DIFFICULTY CALIBRATION:
   - Easy: Direct simulation, array/string traversal, basic hash map/two-pointer techniques (e.g., 5-8 marks).
   - Medium: Dynamic programming, BFS/DFS tree/graph traversal, greedy heuristics, binary search, prefix sums (e.g., 10-15 marks).
   - Hard: Advanced DP with bitmasking, segment trees/Fenwick trees, Dijkstra/Floyd-Warshall, monotonic stacks, complex optimization (e.g., 15-20 marks).
   - If 'Mixed' difficulty is requested, structure the set with ascending difficulty and tag each problem's 'difficulty' field accordingly.
6. BLOOM'S TAXONOMY: Map each problem to its cognitive level (Understand, Apply, Analyze, Evaluate, Create).
7. STRICT DIVERSITY & ZERO REPETITION (MANDATORY):
   - Every single problem MUST test a DIFFERENT algorithmic paradigm, data structure, or problem-solving technique.
   - Under NO circumstances should problems be repeated, rephrased, or duplicated within the same set or across regenerations.
8. FORMAT: Return exclusively a single valid JSON object conforming to the schema. No markdown fences, no conversational preamble.
"""

def build_dsa_user_prompt(
    dsa_topic: str,
    problem_style: str,
    language: str,
    difficulty: str,
    count: int,
    include_constraints: bool,
    include_hints: bool,
    include_solution: bool,
    include_complexity: bool,
    additional_instructions: str = ""
) -> str:
    if difficulty.strip().lower() == "mixed":
        diff_spec = "MIXED DIFFICULTY: Provide a progressive balanced challenge starting with foundational Easy problem(s), moving to standard Medium problem(s), and ending with an advanced Hard problem. In output JSON, set each question's 'difficulty' field to its specific level ('Easy', 'Medium', or 'Hard')."
    else:
        diff_spec = f"DIFFICULTY LEVEL: {difficulty}. Ensure all problems adhere to this level."

    prompt = f"""
DSA SPECIFICATIONS:
- Data Structure / Algorithm Topic: {dsa_topic}
- Problem Style: {problem_style} (e.g., LeetCode-style, Output Prediction, Debugging, Conceptual)
- Target Programming Language: {language}
- {diff_spec}
- Quantity: EXACTLY {count} distinct problems (numbered 1 to {count}). Never truncate, combine, or stop early.
- Include Constraints: {include_constraints}
- Include Hints: {include_hints}
- Include Solution Code: {include_solution}
- Include Time/Space Complexity: {include_complexity}
- Extra Notes: {additional_instructions or "None"}

OUTPUT SCHEMA (JSON):
{{
  "topic": "{dsa_topic}",
  "language": "{language}",
  "questions": [
    {{
      "id": 1,
      "type": "{problem_style}",
      "difficulty": "Medium",
      "blooms_level": "Apply",
      "marks": 10,
      "title": "Clear Problem Title",
      "question": "Comprehensive problem statement describing the scenario and task.",
      "input_format": "Description of the input parameters or stream.",
      "output_format": "Description of the expected return value or output.",
      "constraints": ["1 <= N <= 10^5", "0 <= A[i] <= 10^9"],
      "sample_input": "Input representation",
      "sample_output": "Expected output representation",
      "explanation": "Step-by-step walkthrough of how sample output is derived.",
      "hints": ["Hint 1: Think about two pointers...", "Hint 2: ..."],
      "solution_code": "// Full working code solution here in {language}",
      "time_complexity": "O(N log N)",
      "space_complexity": "O(1)"
    }}
  ]
}}

CRITICAL REQUIREMENT: Return the questions array with EXACTLY {count} distinct problems (numbered 1 through {count}). Complete all {count} problems fully without cutting short.
"""
    return prompt


