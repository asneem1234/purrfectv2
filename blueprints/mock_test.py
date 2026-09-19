"""Mock Test generator.

Builds a practice exam from the materials a student uploaded for one exam,
written in the style of a professor persona they describe. Replaces the older
Clawdia past-paper analyser.
"""

from flask import Blueprint, render_template, request, flash
from flask_login import login_required, current_user
import json
import re
import traceback

import google.generativeai as genai

from models import ClassMaterial, StudyClass

mock_test_bp = Blueprint('mock_test_bp', __name__)

# Materials are sent whole; this caps a runaway prompt
MAX_MATERIAL_CHARS = 200000

DIFFICULTIES = ['easier than usual', 'typical', 'harder than usual']
DURATIONS = [30, 60, 90, 120, 180]


def _strip_code_fences(text):
    """Gemini often wraps JSON in ```json ... ``` despite being asked not to."""
    cleaned = text.strip()
    fence = re.match(r'^```(?:json)?\s*(.*?)\s*```$', cleaned, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return cleaned


def _repair_truncated_json(text):
    """Best-effort close of a JSON object that was cut off mid-generation.

    A long paper can hit the output token limit partway through a question.
    Rather than discard the whole thing, rewind to the last complete element
    inside an array and close whatever is still open.
    """
    stack = []
    in_string = False
    escaped = False
    last_safe = None

    for i, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char in '{[':
            stack.append(char)
        elif char in '}]':
            if stack:
                stack.pop()
            # A complete object sitting directly in an array is a clean cut point
            if char == '}' and stack and stack[-1] == '[':
                last_safe = i + 1

    if last_safe is None:
        return None

    prefix = text[:last_safe]

    # Recompute what's still open in the kept prefix, then close it
    open_stack = []
    in_string = False
    escaped = False
    for char in prefix:
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in '{[':
            open_stack.append(char)
        elif char in '}]' and open_stack:
            open_stack.pop()

    closers = ''.join(']' if opener == '[' else '}' for opener in reversed(open_stack))
    return prefix + closers


def _parse_paper(raw):
    """Parse the model's JSON. Returns None if it isn't usable."""
    candidate = _strip_code_fences(raw)

    # Fall back to the outermost braces if the model added a preamble
    if not candidate.startswith('{'):
        start, end = candidate.find('{'), candidate.rfind('}')
        if start == -1 or end <= start:
            return None
        candidate = candidate[start:end + 1]

    paper = None
    try:
        paper = json.loads(candidate)
    except ValueError as e:
        print(f"Mock test JSON parse failed ({e}); attempting truncation repair")
        print(f"  raw length: {len(raw)}, tail: {raw[-200:]!r}")
        repaired = _repair_truncated_json(candidate)
        if repaired:
            try:
                paper = json.loads(repaired)
                print("  repair succeeded - paper may be missing its final questions")
            except ValueError as e2:
                print(f"  repair failed too: {e2}")
                return None
        else:
            return None

    if not isinstance(paper, dict) or not isinstance(paper.get('sections'), list):
        print("Mock test JSON missing a sections list")
        return None

    # Drop any question the repair left half-written
    for section in paper['sections']:
        questions = section.get('questions')
        if isinstance(questions, list):
            section['questions'] = [
                q for q in questions
                if isinstance(q, dict) and str(q.get('text') or '').strip()
            ]
    paper['sections'] = [
        s for s in paper['sections']
        if isinstance(s, dict) and s.get('questions')
    ]
    if not paper['sections']:
        print("Mock test JSON had no usable questions after cleanup")
        return None

    return paper


# Whether this SDK build accepts response_mime_type. None until we've tried
# once; set to False permanently on the first rejection so we don't keep
# burning a failed call on every generation. requirements.txt pins
# google-generativeai 0.3.1, which predates JSON mode.
_json_mode_supported = None


def _generate_paper_json(prompt):
    """Ask Gemini for the paper, preferring native JSON mode where available.

    A whole paper with model answers is long, and the default output cap is the
    most likely reason a generation comes back as unparseable half-JSON - so ask
    for plenty of room regardless of which path we take.
    """
    global _json_mode_supported

    base_config = {
        'max_output_tokens': 16384,
        'temperature': 0.8,
    }

    def run(config):
        model = genai.GenerativeModel('gemini-2.5-flash', generation_config=config)
        response = model.generate_content(prompt)

        finish = _finish_reason(response)
        if finish and not any(token in finish.upper() for token in ('STOP', 'FINISH_REASON_1')):
            print(f"Mock test generation finished early: {finish}")

        return (getattr(response, 'text', '') or '').strip()

    if _json_mode_supported is not False:
        try:
            text = run({**base_config, 'response_mime_type': 'application/json'})
            _json_mode_supported = True
            return text
        except Exception as e:
            # Old SDKs reject the field outright, and they don't agree on the
            # exception type - so fall back on anything and remember it.
            if _json_mode_supported is None:
                _json_mode_supported = False
                print(f"JSON mode unavailable on this SDK, falling back: {e}")
            else:
                raise

    return run(base_config)


def _finish_reason(response):
    """Pull the finish reason out of a response, tolerating SDK differences."""
    try:
        return str(response.candidates[0].finish_reason)
    except Exception:
        return None


def build_mock_test(user_id, class_id, exam_name, persona, difficulty, duration, question_count):
    """Generate a mock paper. Returns (paper_dict, material_list).

    Raises ValueError with a student-facing message when it can't proceed.
    """
    from blueprints.study_plan import extract_text_from_paths

    # Scope to the caller so a forged key can't reach another student's files
    study_class = StudyClass.query.filter_by(id=class_id, user_id=user_id).first()
    if not study_class:
        raise ValueError("That exam couldn't be found.")

    materials = ClassMaterial.query.filter_by(
        class_id=class_id, exam_name=exam_name
    ).order_by(ClassMaterial.uploaded_at).all()
    if not materials:
        raise ValueError("There are no materials uploaded for this exam yet.")

    contents, _ = extract_text_from_paths([m.file_path for m in materials])
    contents = (contents or '').strip()
    if len(contents) < 100:
        raise ValueError(
            "Couldn't read enough text from this exam's materials to write a test. "
            "Scanned PDFs without selectable text won't work."
        )
    contents = contents[:MAX_MATERIAL_CHARS]

    exam_label = f"{study_class.label} - {exam_name or 'Unassigned'}"
    persona_block = persona.strip() or (
        "No persona given. Write in the style of a fair, conventional university exam."
    )

    prompt = f"""You are setting a mock exam for a student revising for "{exam_label}".

Write the paper the way THIS professor would write it:

PROFESSOR PERSONA
{persona_block}

Rules:
- Base every question on the study material below. Do not test material that
  isn't in it.
- Aim for about {question_count} questions total, grouped into sensible sections.
- Difficulty: {difficulty}. Duration: {duration} minutes.
- Mark allocations across all sections must add up to the total you report.
- Let the persona shape question style, phrasing, emphasis and mark weighting.
- Write a full model answer for every question.

Respond with ONLY a JSON object in exactly this shape, and no other text:

{{
  "title": "string",
  "duration_minutes": {duration},
  "total_marks": 0,
  "instructions": "string, one or two lines",
  "sections": [
    {{
      "name": "Section A - Short answer",
      "marks": 0,
      "questions": [
        {{"number": 1, "text": "string", "marks": 0, "answer": "string"}}
      ]
    }}
  ]
}}

STUDY MATERIAL:
{contents}
"""

    raw = _generate_paper_json(prompt)
    if not raw:
        raise ValueError("The AI returned an empty paper. Please try again.")

    paper = _parse_paper(raw)
    if paper is None:
        raise ValueError(
            "The AI's response wasn't in a readable format. Try again, or ask for "
            "fewer questions — long papers can get cut off mid-sentence."
        )

    paper.setdefault('title', f'Mock Test - {exam_label}')
    paper.setdefault('duration_minutes', duration)
    paper.setdefault('instructions', '')

    # Trust our own arithmetic over the model's for the headline total
    counted = 0
    for section in paper['sections']:
        for question in section.get('questions', []) or []:
            try:
                counted += int(question.get('marks') or 0)
            except (TypeError, ValueError):
                pass
    if counted:
        paper['total_marks'] = counted
    else:
        paper.setdefault('total_marks', 0)

    return paper, materials


@mock_test_bp.route('/mock-test', methods=['GET', 'POST'])
@login_required
def mock_test():
    """Pick an exam, describe the professor, get a practice paper."""
    from blueprints.study_plan import get_exams_with_materials

    exams = get_exams_with_materials(current_user.id)
    paper = None
    materials = []
    selected_key = None
    persona = ''
    difficulty = 'typical'
    duration = 90
    question_count = 8

    if request.method == 'POST':
        selected_key = (request.form.get('examKey') or '').strip()
        persona = (request.form.get('persona') or '').strip()

        # Same (class_id, exam_name) key the other tools use. class_id is an
        # integer, so the first colon is always the separator.
        raw_class_id, _, exam_name = selected_key.partition(':')
        exam_name = exam_name or None

        difficulty = request.form.get('difficulty', 'typical')
        if difficulty not in DIFFICULTIES:
            difficulty = 'typical'

        try:
            duration = int(request.form.get('duration', 90))
        except (TypeError, ValueError):
            duration = 90
        if duration not in DURATIONS:
            duration = 90

        try:
            question_count = max(3, min(30, int(request.form.get('questionCount', 8))))
        except (TypeError, ValueError):
            question_count = 8

        try:
            class_id = int(raw_class_id)
        except (TypeError, ValueError):
            class_id = None

        if class_id is None:
            flash('Please choose an exam to generate a test for.')
        else:
            try:
                paper, materials = build_mock_test(
                    current_user.id, class_id, exam_name, persona,
                    difficulty, duration, question_count
                )
            except ValueError as e:
                flash(str(e))
            except Exception as e:
                print(f"Error generating mock test for class {class_id} / {exam_name}: {e}")
                traceback.print_exc()
                flash("Couldn't generate the mock test. Please try again.")

    return render_template(
        'mock_test.html',
        exams=exams,
        paper=paper,
        materials=materials,
        selected_key=selected_key,
        persona=persona,
        difficulty=difficulty,
        duration=duration,
        question_count=question_count,
        difficulties=DIFFICULTIES,
        durations=DURATIONS
    )
