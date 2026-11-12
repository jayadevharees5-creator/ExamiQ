import io
import csv
from datetime import datetime
from typing import List, Dict, Any
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

class QuestionExporter:
    """
    Exports generated questions to TXT, CSV, and cleanly styled PDF test papers.
    """

    @staticmethod
    def to_txt(questions: List[Dict[str, Any]], title: str = "QuizForge Assessment") -> str:
        """Converts questions into clean, human-readable text."""
        lines = [
            f"===========================================================",
            f"          {title.upper()}          ",
            f"===========================================================\n",
        ]

        for i, q in enumerate(questions, start=1):
            q_type = q.get("type", "Question")
            diff = q.get("difficulty", "Standard")
            lines.append(f"Q{i}. [{q_type} | {diff}]")
            if q.get("title"):
                lines.append(f"Title: {q['title']}")
            lines.append(f"{q['question']}\n")

            if q.get("options"):
                for opt in q["options"]:
                    lines.append(f"   {opt}")
                lines.append("")

            if q.get("constraints"):
                lines.append("Constraints: " + ", ".join(q["constraints"]))
            if q.get("sample_input"):
                lines.append(f"Sample Input: {q['sample_input']}")
            if q.get("sample_output"):
                lines.append(f"Sample Output: {q['sample_output']}")

            if q.get("source_document"):
                p_info = f" (Page {q['page_number']})" if q.get("page_number") else ""
                lines.append(f"Grounded Source: {q['source_document']}{p_info}")

            if q.get("correct_answer"):
                lines.append(f"Answer: {q['correct_answer']}")
            if q.get("explanation"):
                lines.append(f"Explanation: {q['explanation']}")
            if q.get("solution_code"):
                lines.append(f"\nSolution Code:\n{q['solution_code']}")

            lines.append("-" * 55 + "\n")

        return "\n".join(lines)

    @staticmethod
    def to_csv(questions: List[Dict[str, Any]]) -> str:
        """Converts questions into a standard CSV string."""
        output = io.StringIO()
        fieldnames = [
            "ID", "Type", "Difficulty", "Title", "Question",
            "Options", "Correct Answer", "Explanation", "Hint",
            "Source Document", "Page Number"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for q in questions:
            options_str = " | ".join(q.get("options", [])) if q.get("options") else ""
            writer.writerow({
                "ID": q.get("id", ""),
                "Type": q.get("type", ""),
                "Difficulty": q.get("difficulty", ""),
                "Title": q.get("title", ""),
                "Question": q.get("question", ""),
                "Options": options_str,
                "Correct Answer": q.get("correct_answer", ""),
                "Explanation": q.get("explanation", ""),
                "Hint": q.get("hint", ""),
                "Source Document": q.get("source_document", ""),
                "Page Number": q.get("page_number", "")
            })

        return output.getvalue()

    @staticmethod
    def to_pdf(
        questions: List[Dict[str, Any]],
        title: str = "Examination Question Paper",
        department: str = "",
        max_marks: str = "150",
        time_allowed: str = "1 Hour",
        blooms_level: str = ""
    ) -> bytes:
        """
        Generates a clean, prestigious, university examination paper with neat typography,
        clear question layout, optional source footnotes (for grounded PDFs), and an evaluator answer key.
        """
        import re
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=45,
            leftMargin=45,
            topMargin=40,
            bottomMargin=40
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=15,
            leading=19,
            textColor=colors.HexColor('#0F172A'),
            alignment=TA_CENTER
        )
        subtitle_style = ParagraphStyle(
            'DocSubTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#475569'),
            alignment=TA_CENTER
        )
        meta_bar_style = ParagraphStyle(
            'MetaBar',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#334155'),
            alignment=TA_CENTER
        )
        instructions_style = ParagraphStyle(
            'InstrStyle',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor('#475569')
        )
        q_text_style = ParagraphStyle(
            'QText',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=14.5,
            textColor=colors.HexColor('#0F172A')
        )
        opt_style = ParagraphStyle(
            'OptText',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor('#1E293B'),
            leftIndent=16
        )
        meta_note_style = ParagraphStyle(
            'MetaNote',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor('#475569'),
            leftIndent=16
        )
        source_note_style = ParagraphStyle(
            'SourceNote',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=8,
            leading=11,
            textColor=colors.HexColor('#64748B'),
            leftIndent=16
        )
        ans_heading_style = ParagraphStyle(
            'AnsHeading',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=13,
            leading=17,
            textColor=colors.HexColor('#0F172A'),
            alignment=TA_CENTER
        )
        ans_sub_style = ParagraphStyle(
            'AnsSub',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor('#64748B'),
            alignment=TA_CENTER
        )
        ans_text_style = ParagraphStyle(
            'AnsText',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=13.5,
            textColor=colors.HexColor('#0F172A')
        )

        elements = []

        # -------------------------------------------------------------
        # Clean Institutional Examination Header
        # -------------------------------------------------------------
        subject_clean = title.strip() if title and title.strip() else "EXAMINATION QUESTION PAPER"
        marks_clean = max_marks.strip() if max_marks and max_marks.strip() else f"{len(questions) * 2} Marks"
        time_clean = time_allowed.strip() if time_allowed and time_allowed.strip() else "1.5 Hours"

        elements.append(Paragraph(subject_clean.upper(), title_style))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph("EXAMINATION QUESTION PAPER", subtitle_style))
        elements.append(Spacer(1, 6))

        meta_line = f"<b>Time Allowed:</b> {time_clean} &nbsp;&nbsp;&bull;&nbsp;&nbsp; <b>Maximum Marks:</b> {marks_clean} &nbsp;&nbsp;&bull;&nbsp;&nbsp; <b>Total Questions:</b> {len(questions)}"
        elements.append(Paragraph(meta_line, meta_bar_style))
        elements.append(Spacer(1, 8))
        elements.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor('#0F172A'), spaceAfter=10))

        elements.append(Paragraph("<b>Instructions:</b> Answer all questions carefully. Choose or provide the most precise answer for each item.", instructions_style))
        elements.append(Spacer(1, 12))

        # -------------------------------------------------------------
        # Clean Questions
        # -------------------------------------------------------------
        for i, q in enumerate(questions, start=1):
            q_elements = []

            # Clean Question text without duplicate labels
            raw_q = q.get('question', '').strip()
            cleaned_q = re.sub(r'^(?:Q\d+[:\.]?|\d+[\.:\)])\s*', '', raw_q)
            q_text = f"<b>{i}.</b> &nbsp; {cleaned_q}"
            q_elements.append(Paragraph(q_text, q_text_style))
            q_elements.append(Spacer(1, 4))

            # Options (for MCQs)
            if q.get("options"):
                for opt in q["options"]:
                    q_elements.append(Paragraph(str(opt).strip(), opt_style))
                    q_elements.append(Spacer(1, 2))
                q_elements.append(Spacer(1, 2))

            # Constraints or Sample I/O (for DSA coding questions)
            if q.get("constraints"):
                c_text = "<b>Constraints:</b> " + ", ".join(q["constraints"])
                q_elements.append(Paragraph(c_text, meta_note_style))
                q_elements.append(Spacer(1, 2))
            if q.get("sample_input"):
                q_elements.append(Paragraph(f"<b>Sample Input:</b> {q['sample_input']}", meta_note_style))
                q_elements.append(Spacer(1, 2))
            if q.get("sample_output"):
                q_elements.append(Paragraph(f"<b>Sample Output:</b> {q['sample_output']}", meta_note_style))
                q_elements.append(Spacer(1, 2))

            # Grounded Source: Only display if genuine source document exists (e.g. from uploaded PDF)
            doc_source = q.get("source_document")
            page_num = q.get("page_number")
            is_generic_source = not doc_source or doc_source in [
                "AI Curriculum Knowledge",
                "Algorithmic Problem Studio",
                "Course Material"
            ]
            if doc_source and not is_generic_source:
                p_text = f" (Page {page_num})" if page_num else ""
                q_elements.append(Paragraph(f"<i>Source: {doc_source}{p_text}</i>", source_note_style))
                q_elements.append(Spacer(1, 2))

            q_elements.append(Spacer(1, 6))
            elements.append(KeepTogether(q_elements))

        # -------------------------------------------------------------
        # Answer Key & Solutions on a Separate Page
        # -------------------------------------------------------------
        elements.append(PageBreak())
        elements.append(Paragraph("ANSWER KEY & DETAILED SOLUTIONS", ans_heading_style))
        elements.append(Spacer(1, 3))
        elements.append(Paragraph("Confidential &bull; Evaluator & Faculty Assessment Reference", ans_sub_style))
        elements.append(Spacer(1, 8))
        elements.append(HRFlowable(width="100%", thickness=1.0, color=colors.HexColor('#0F172A'), spaceAfter=12))

        for i, q in enumerate(questions, start=1):
            ans_elements = []
            ans = q.get("correct_answer") or "Not provided"
            exp = q.get("explanation") or ""
            doc_source = q.get("source_document")
            page_num = q.get("page_number")
            is_generic_source = not doc_source or doc_source in [
                "AI Curriculum Knowledge",
                "Algorithmic Problem Studio",
                "Course Material"
            ]

            ans_block = f"<b>Q{i}. Correct Answer:</b> <font color='#166534'><b>{ans}</b></font>"
            if exp:
                ans_block += f"<br/><b>Explanation:</b> {exp}"
            if doc_source and not is_generic_source:
                p_text = f" (Page {page_num})" if page_num else ""
                ans_block += f"<br/><b>Reference:</b> <i>{doc_source}{p_text}</i>"

            ans_elements.append(Paragraph(ans_block, ans_text_style))
            ans_elements.append(Spacer(1, 8))
            elements.append(KeepTogether(ans_elements))

        doc.build(elements)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes
