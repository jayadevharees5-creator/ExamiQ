import time
from typing import List, Dict, Any, Optional
from core.groq_client import GroqClientWrapper
from core.rag_pipeline import RAGPipeline
from prompts.pdf_question_prompt import SYSTEM_PDF_PROMPT, build_pdf_user_prompt
from prompts.knowledge_question_prompt import SYSTEM_KNOWLEDGE_PROMPT, build_knowledge_user_prompt
from prompts.dsa_question_prompt import SYSTEM_DSA_PROMPT, build_dsa_user_prompt
from utils.validators import QuestionValidator

class QuestionGenerator:
    """
    Coordinates question generation across PDF RAG, Knowledge Studio, and DSA mode.
    Includes smart multi-batching to handle 30 to 100 questions cleanly without token truncation.
    """

    def __init__(self, groq_client: GroqClientWrapper):
        self.groq_client = groq_client

    def generate_from_pdf_rag(
        self,
        rag_pipeline: RAGPipeline,
        unit_info: str,
        topic: str,
        question_types: List[str],
        difficulty: str,
        count: int,
        include_answers: bool = True,
        include_explanations: bool = True,
        include_sources: bool = True,
        language: str = "English",
        additional_instructions: str = "",
        page_min: Optional[int] = None,
        page_max: Optional[int] = None,
        doc_name: Optional[str] = None,
        temperature: float = 0.3,
        existing_questions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Grounded generation pipeline:
        1. Formulates hybrid query from unit, topic, and question types.
        2. Retrieves dense + BM25 chunks and merges via RRF.
        3. Enforces strict factual grounding through Groq LLM.
        Automatically batches when count > 15 to ensure full token budget and zero truncation.
        """
        # Formulate query for RAG retrieval - strictly unit & topic to preserve precision
        query_parts = [unit_info, topic]
        query = " ".join([p for p in query_parts if p and p.strip()]).strip()
        if not query:
            query = "important concepts definitions and core theories"

        # Retrieve proportional chunks for larger question counts
        top_k = min(max(count // 2, 8), 24)
        retrieval_res = rag_pipeline.retrieve(
            query=query,
            page_min=page_min,
            page_max=page_max,
            doc_name=doc_name,
            top_k_fused=top_k
        )

        if retrieval_res.get("insufficient_context", False) or not retrieval_res.get("context_text"):
            return {
                "success": False,
                "error": "The retrieved PDF excerpts do not contain sufficient content for this topic/page range. Please broaden your topic or verify the page selection.",
                "retrieval_details": retrieval_res,
                "questions": []
            }

        context_text = retrieval_res["context_text"]

        # Single call when count <= 15
        if count <= 15:
            instr = additional_instructions
            if existing_questions:
                avoid_list = "; ".join(f'"{q[:80]}"' for q in existing_questions if q)
                if avoid_list:
                    instr += (
                        f"\n\nCRITICAL DIVERSITY REQUIREMENT: The following questions have ALREADY been generated. "
                        f"You MUST NOT repeat, rephrase, or paraphrase any of them: [{avoid_list}]"
                    )

            user_prompt = build_pdf_user_prompt(
                context_text=context_text,
                unit_info=unit_info,
                topic=topic,
                question_types=question_types,
                difficulty=difficulty,
                count=count,
                include_answers=include_answers,
                include_explanations=include_explanations,
                include_sources=include_sources,
                language=language,
                additional_instructions=instr
            )

            max_tokens = min(max(count * 550 + 1000, 4096), 8192)
            resp = self.groq_client.generate_json(
                system_prompt=SYSTEM_PDF_PROMPT,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )

            if not resp["success"]:
                return {
                    "success": False,
                    "error": resp.get("error", "Failed to generate questions."),
                    "retrieval_details": retrieval_res,
                    "questions": []
                }

            data = resp["data"]
            if data.get("insufficient_context", False):
                return {
                    "success": False,
                    "error": f"The document context was insufficient for this specific topic: {data.get('reason', 'Missing detailed material.')}",
                    "retrieval_details": retrieval_res,
                    "questions": []
                }

            questions = QuestionValidator.validate_and_normalize(data)
            if not questions:
                return {
                    "success": False,
                    "error": "The AI model did not produce valid question entries. Please regenerate or adjust options.",
                    "retrieval_details": retrieval_res,
                    "questions": []
                }

            for idx, q in enumerate(questions, start=1):
                q["id"] = idx

            return {
                "success": True,
                "questions": questions,
                "retrieval_details": retrieval_res,
                "error": None
            }

        # Multi-batch generation when count > 15 (e.g. 30, 50, 100 questions)
        all_questions = []
        batch_size = 12
        avoid_pool = list(existing_questions or [])
        max_iterations = (count // batch_size) + 4
        iteration = 0

        while len(all_questions) < count and iteration < max_iterations:
            iteration += 1
            batch_count = min(batch_size, count - len(all_questions))

            # Build anti-repetition instructions for this batch
            batch_instructions = additional_instructions
            current_avoid = avoid_pool + [q.get("question", "") for q in all_questions if q.get("question")]
            if current_avoid:
                unique_avoid = []
                for q_text in current_avoid:
                    if q_text and q_text not in unique_avoid:
                        unique_avoid.append(q_text)
                if unique_avoid:
                    avoid_str = "\n".join(f"- {q[:90]}" for q in unique_avoid[-20:])
                    batch_instructions += (
                        f"\n\nCRITICAL DIVERSITY REQUIREMENT (ZERO REPETITION):\n"
                        f"The following questions have ALREADY been generated from the text:\n{avoid_str}\n"
                        f"Generate {batch_count} COMPLETELY NEW and DIFFERENT questions covering different theorems, definitions, or sections."
                    )

            user_prompt = build_pdf_user_prompt(
                context_text=context_text,
                unit_info=unit_info,
                topic=topic,
                question_types=question_types,
                difficulty=difficulty,
                count=batch_count,
                include_answers=include_answers,
                include_explanations=include_explanations,
                include_sources=include_sources,
                language=language,
                additional_instructions=batch_instructions
            )

            max_tokens = min(max(batch_count * 550 + 1000, 4096), 8192)
            resp = self.groq_client.generate_json(
                system_prompt=SYSTEM_PDF_PROMPT,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )

            if not resp["success"]:
                if all_questions:
                    break
                return {
                    "success": False,
                    "error": resp.get("error", "Failed to generate questions."),
                    "retrieval_details": retrieval_res,
                    "questions": []
                }

            data = resp["data"]
            if data.get("insufficient_context", False):
                if all_questions:
                    break
                return {
                    "success": False,
                    "error": f"The document context was insufficient: {data.get('reason', 'Missing detailed material.')}",
                    "retrieval_details": retrieval_res,
                    "questions": []
                }

            new_questions = QuestionValidator.validate_and_normalize(data)
            if not new_questions:
                if all_questions:
                    break
                return {
                    "success": False,
                    "error": "The AI model did not produce valid question entries.",
                    "retrieval_details": retrieval_res,
                    "questions": []
                }

            all_questions.extend(new_questions)
            if len(all_questions) < count:
                time.sleep(0.4)

        if not all_questions:
            return {
                "success": False,
                "error": "No questions were successfully generated.",
                "retrieval_details": retrieval_res,
                "questions": []
            }

        # Renumber questions sequentially 1 to N
        for idx, q in enumerate(all_questions, start=1):
            q["id"] = idx

        return {
            "success": True,
            "questions": all_questions[:count],
            "retrieval_details": retrieval_res,
            "error": None
        }

    def generate_from_knowledge(
        self,
        topic: str,
        target_audience: str,
        question_types: List[str],
        difficulty: str,
        count: int,
        include_answers: bool = True,
        include_explanations: bool = True,
        include_hints: bool = True,
        additional_instructions: str = "",
        temperature: float = 0.7,
        existing_questions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generates questions on any topic using general LLM capabilities.
        Automatically batches when count > 15 to ensure full token budget and zero truncation.
        """
        if count <= 15:
            user_prompt = build_knowledge_user_prompt(
                topic=topic,
                target_audience=target_audience,
                question_types=question_types,
                difficulty=difficulty,
                count=count,
                include_answers=include_answers,
                include_explanations=include_explanations,
                include_hints=include_hints,
                additional_instructions=additional_instructions
            )

            max_tokens = min(max(count * 550 + 1000, 4096), 8192)
            resp = self.groq_client.generate_json(
                system_prompt=SYSTEM_KNOWLEDGE_PROMPT,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )

            if not resp["success"]:
                return {"success": False, "error": resp.get("error", "Generation failed."), "questions": []}

            questions = QuestionValidator.validate_and_normalize(resp["data"])
            for idx, q in enumerate(questions, start=1):
                q["id"] = idx
            return {"success": True, "questions": questions, "error": None}

        # Multi-batch generation when count > 15 (e.g. 30, 50, 100 questions)
        all_questions = []
        batch_size = 12
        avoid_pool = list(existing_questions or [])
        max_iterations = (count // batch_size) + 4
        iteration = 0

        while len(all_questions) < count and iteration < max_iterations:
            iteration += 1
            batch_count = min(batch_size, count - len(all_questions))

            batch_instructions = additional_instructions
            current_avoid = avoid_pool + [q.get("question", "") for q in all_questions if q.get("question")]
            if current_avoid:
                unique_avoid = []
                for q_text in current_avoid:
                    if q_text and q_text not in unique_avoid:
                        unique_avoid.append(q_text)
                if unique_avoid:
                    avoid_str = "\n".join(f"- {q[:90]}" for q in unique_avoid[-20:])
                    batch_instructions += (
                        f"\n\nCRITICAL DIVERSITY REQUIREMENT (ZERO REPETITION):\n"
                        f"The following questions have ALREADY been generated in this session:\n{avoid_str}\n"
                        f"Generate {batch_count} COMPLETELY NEW and DIFFERENT questions covering different sub-topics, principles, or problems."
                    )

            user_prompt = build_knowledge_user_prompt(
                topic=topic,
                target_audience=target_audience,
                question_types=question_types,
                difficulty=difficulty,
                count=batch_count,
                include_answers=include_answers,
                include_explanations=include_explanations,
                include_hints=include_hints,
                additional_instructions=batch_instructions
            )

            max_tokens = min(max(batch_count * 550 + 1000, 4096), 8192)
            resp = self.groq_client.generate_json(
                system_prompt=SYSTEM_KNOWLEDGE_PROMPT,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )

            if not resp["success"]:
                if all_questions:
                    break
                return {"success": False, "error": resp.get("error", "Generation failed."), "questions": []}

            new_questions = QuestionValidator.validate_and_normalize(resp["data"])
            if not new_questions:
                if all_questions:
                    break
                return {"success": False, "error": "Model returned invalid question data.", "questions": []}

            all_questions.extend(new_questions)
            if len(all_questions) < count:
                time.sleep(0.4)

        if not all_questions:
            return {"success": False, "error": "No questions were successfully generated.", "questions": []}

        for idx, q in enumerate(all_questions, start=1):
            q["id"] = idx

        return {"success": True, "questions": all_questions[:count], "error": None}

    def generate_dsa_problems(
        self,
        dsa_topic: str,
        problem_style: str,
        language: str,
        difficulty: str,
        count: int,
        include_constraints: bool = True,
        include_hints: bool = True,
        include_solution: bool = True,
        include_complexity: bool = True,
        additional_instructions: str = "",
        temperature: float = 0.3,
        existing_questions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generates structured DSA coding problems with constraints, sample I/O, and solutions.
        Batches when count > 5 to prevent token limit cuts on large problem code outputs.
        """
        if count <= 5:
            instr = additional_instructions
            if existing_questions:
                avoid_list = "; ".join(f'"{q[:80]}"' for q in existing_questions if q)
                if avoid_list:
                    instr += (
                        f"\n\nCRITICAL DIVERSITY REQUIREMENT: The following problems have ALREADY been generated. "
                        f"You MUST NOT repeat, rephrase, or paraphrase any of them: [{avoid_list}]"
                    )

            user_prompt = build_dsa_user_prompt(
                dsa_topic=dsa_topic,
                problem_style=problem_style,
                language=language,
                difficulty=difficulty,
                count=count,
                include_constraints=include_constraints,
                include_hints=include_hints,
                include_solution=include_solution,
                include_complexity=include_complexity,
                additional_instructions=instr
            )

            max_tokens = min(count * 750 + 800, 8192)
            resp = self.groq_client.generate_json(
                system_prompt=SYSTEM_DSA_PROMPT,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )

            if not resp["success"]:
                return {"success": False, "error": resp.get("error", "DSA Generation failed."), "questions": []}

            questions = QuestionValidator.validate_and_normalize(resp["data"])
            for idx, q in enumerate(questions, start=1):
                q["id"] = idx
            return {"success": True, "questions": questions, "error": None}

        # Multi-batch generation when count > 5 for DSA problems
        all_problems = []
        batch_size = 4
        avoid_pool = list(existing_questions or [])
        max_iterations = (count // batch_size) + 4
        iteration = 0

        while len(all_problems) < count and iteration < max_iterations:
            iteration += 1
            batch_count = min(batch_size, count - len(all_problems))

            batch_instructions = additional_instructions
            current_avoid = avoid_pool + [
                (q.get("title") or q.get("question", "")) for q in all_problems if (q.get("title") or q.get("question"))
            ]
            if current_avoid:
                unique_avoid = []
                for q_text in current_avoid:
                    if q_text and q_text not in unique_avoid:
                        unique_avoid.append(q_text)
                if unique_avoid:
                    avoid_str = "\n".join(f"- {q[:90]}" for q in unique_avoid[-15:])
                    batch_instructions += (
                        f"\n\nCRITICAL DIVERSITY REQUIREMENT (ZERO REPETITION):\n"
                        f"The following problems have ALREADY been created:\n{avoid_str}\n"
                        f"Generate {batch_count} COMPLETELY NEW and DIFFERENT algorithmic problems covering different patterns, techniques, or data structures."
                    )

            user_prompt = build_dsa_user_prompt(
                dsa_topic=dsa_topic,
                problem_style=problem_style,
                language=language,
                difficulty=difficulty,
                count=batch_count,
                include_constraints=include_constraints,
                include_hints=include_hints,
                include_solution=include_solution,
                include_complexity=include_complexity,
                additional_instructions=batch_instructions
            )

            max_tokens = min(batch_count * 750 + 800, 8192)
            resp = self.groq_client.generate_json(
                system_prompt=SYSTEM_DSA_PROMPT,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )

            if not resp["success"]:
                if all_problems:
                    break
                return {"success": False, "error": resp.get("error", "DSA Generation failed."), "questions": []}

            new_problems = QuestionValidator.validate_and_normalize(resp["data"])
            if not new_problems:
                if all_problems:
                    break
                return {"success": False, "error": "Model returned invalid DSA problem entries.", "questions": []}

            all_problems.extend(new_problems)
            if len(all_problems) < count:
                time.sleep(0.5)

        if not all_problems:
            return {"success": False, "error": "No DSA problems were successfully generated.", "questions": []}

        for idx, q in enumerate(all_problems, start=1):
            q["id"] = idx

        return {"success": True, "questions": all_problems[:count], "error": None}

    def regenerate_single_question(
        self,
        existing_question: Dict[str, Any],
        context_text: Optional[str] = None,
        existing_questions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Regenerates a single specific question, either with document context or general knowledge.
        Uses higher temperature and explicit diversity instructions to avoid repetition.
        """
        q_type = existing_question.get("type", "Multiple Choice Questions (MCQ)")
        diff = existing_question.get("difficulty", "Medium")
        old_question = existing_question.get("question", "")

        exclusion_text = ""
        if existing_questions:
            avoid_list = "\n".join(f"- {q[:100]}" for q in existing_questions if q)
            if avoid_list:
                exclusion_text = (
                    f"\nSTRICT ZERO-DUPLICATION RULE:\n"
                    f"The replacement question MUST NOT test the same concept as the question being replaced (\"{old_question}\"), "
                    f"nor any of these other questions already on the paper:\n{avoid_list}\n"
                    f"Generate a question testing a completely DIFFERENT theorem, formula, definition, or concept."
                )

        answer_quality_instruction = ""
        if "Short Answer" in q_type:
            answer_quality_instruction = (
                "ANSWER QUALITY: For Short Answer Questions, provide a detailed, accurate answer of 3-5 sentences "
                "that directly addresses the question. Include key facts, definitions, and relevant explanations. "
                "The answer must be factually correct and comprehensive enough to earn full marks."
            )
        elif "Long Answer" in q_type:
            answer_quality_instruction = (
                "ANSWER QUALITY: For Long Answer Questions, provide a thorough, well-structured answer of 8-15 sentences "
                "organized with clear points. Include definitions, explanations, examples, and relevant details. "
                "The answer must be comprehensive, academically rigorous, and cover all aspects of the question."
            )
        else:
            answer_quality_instruction = (
                "ANSWER QUALITY: Ensure the correct_answer is precisely accurate. For MCQs, the correct option must "
                "be unambiguously right. Provide a clear explanation of why the answer is correct."
            )

        if context_text:
            sys_prompt = SYSTEM_PDF_PROMPT
            user_prompt = (
                f"DOCUMENT CONTEXT:\n{context_text}\n\n"
                f"TASK: Generate exactly ONE COMPLETELY NEW and DIFFERENT replacement question of type '{q_type}' with difficulty '{diff}'.\n"
                f"CRITICAL: The new question MUST be fundamentally different from this original question: \"{old_question}\"\n"
                f"- Use a DIFFERENT concept, fact, or angle from the document context.\n"
                f"- Do NOT rephrase or paraphrase the original question.\n"
                f"- Pick a completely different section or topic from the source material.\n"
                f"{exclusion_text}\n"
                f"{answer_quality_instruction}\n"
                f"Return JSON matching: {{'questions': [{{'id': {existing_question.get('id', 1)}, 'type': '{q_type}', 'difficulty': '{diff}', 'question': '...', 'options': [...], 'correct_answer': '...', 'explanation': '...', 'source_document': '...', 'page_number': 1}}]}}"
            )
        else:
            sys_prompt = SYSTEM_KNOWLEDGE_PROMPT
            topic_str = existing_question.get('topic') or existing_question.get('title') or existing_question.get('subject') or existing_question.get('question') or 'core curriculum concept'
            user_prompt = (
                f"TASK: Generate ONE COMPLETELY NEW and DIFFERENT replacement question of type '{q_type}' with difficulty '{diff}'.\n"
                f"Topic concept: {topic_str}\n"
                f"CRITICAL: The new question MUST be fundamentally different from this original: \"{old_question}\"\n"
                f"- Test a DIFFERENT concept, sub-topic, or angle within the same broad topic.\n"
                f"- Do NOT rephrase the original — create something entirely new.\n"
                f"{exclusion_text}\n"
                f"{answer_quality_instruction}\n"
                f"Return JSON matching: {{'questions': [{{'id': {existing_question.get('id', 1)}, 'type': '{q_type}', 'difficulty': '{diff}', 'question': '...', 'options': [...], 'correct_answer': '...', 'explanation': '...'}}]}}"
            )

        resp = self.groq_client.generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            temperature=0.75,
            max_tokens=1000
        )

        if resp["success"]:
            normalized = QuestionValidator.validate_and_normalize(resp["data"])
            if normalized:
                return {"success": True, "question": normalized[0]}
        return {"success": False, "error": resp.get("error", "Failed to regenerate question.")}
