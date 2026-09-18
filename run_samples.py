"""Run the data pack through the live pipeline and compare each draft with data/datapack/expected.json.

    python run_samples.py                  # every case once, drafts written to results/
    python run_samples.py --case case_03   # one case (repeatable)
    python run_samples.py --runs 5         # repeat transcript cases and report per-field agreement
"""

import argparse
import json

from collections import Counter
from pathlib import Path

from voice_capture.constants import NARRATIVE_FIELDS
from voice_capture.drafting import create_draft


DATASET_DIR = Path(__file__).parent / "data" / "datapack"
RESULTS_DIR = Path(__file__).parent / "results"


def run_case(case):
    input_path = DATASET_DIR / case["input"]["file"]
    is_audio = case["input"]["type"] == "audio"

    return create_draft(audio=input_path.read_bytes(), audio_filename=input_path.name) if is_audio else create_draft(input_path.read_text("utf-8"))


def find_mismatches(draft, expected):
    mismatches = []
    if "verdict" in expected and draft.verdict != expected["verdict"]:
        mismatches.append(f"verdict: expected {expected['verdict']}, got {draft.verdict} {draft.rejection_message or ''}".strip())

    if "detected_language" in expected and (draft.detected_language or "").lower() != expected["detected_language"]:
        mismatches.append(f"detected_language: expected {expected['detected_language']}, got {draft.detected_language}")

    for field_name, expected_field in expected.get("fields", {}).items():
        result = draft.fields.get(field_name)
        status, value, codes = (result.status, result.value, result.flag_codes) if result else (None, None, set())
        checks = {
            "status": status == expected_field.get("status"),
            "value": value == expected_field.get("value"),
            "flags_include": set(expected_field.get("flags_include", [])) <= codes,
            "flags_exclude": not set(expected_field.get("flags_exclude", [])) & codes,
            "value_contains_any": any(word.lower() in str(value or "").lower() for word in expected_field.get("value_contains_any", [])),
        }
        mismatches += [
            f"{field_name}.{check}: expected {expected_field[check]!r}; got {status} {value!r} flags={sorted(codes)}"
            for check, passed in checks.items()
            if check in expected_field and not passed
        ]

    return mismatches


def outcome_signature(draft):
    """Status and value per field (status only for free-text fields), for comparing repeated runs."""
    signature = {"verdict": f"{draft.verdict}:{draft.rejection_reason or ''}"}
    for schema_field, result in draft.fields.items():
        signature[schema_field] = str(result.status) if schema_field in NARRATIVE_FIELDS else f"{result.status}:{result.value}"

    return signature


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", action="append", dest="case_ids", help="Run only this case id (repeatable).")
    parser.add_argument("--runs", type=int, default=1, help="Runs per transcript case; more than 1 reports agreement.")
    arguments = parser.parse_args()

    manifest = json.loads((DATASET_DIR / "expected.json").read_text("utf-8"))
    cases = [case for case in manifest["cases"] if not arguments.case_ids or case["id"] in arguments.case_ids]
    RESULTS_DIR.mkdir(exist_ok=True)
    passed_cases = 0
    for case in cases:
        draft = run_case(case)
        mismatches = find_mismatches(draft, case.get("expect", {}))
        passed_cases += not mismatches
        result_file = RESULTS_DIR / f"{case['id']}.json"
        result_file.write_text(json.dumps({"mismatches": mismatches, "draft": draft.model_dump(mode="json")}, indent=2, ensure_ascii=False))
        print(f"{'FAIL' if mismatches else 'PASS'} {case['id']}: {draft.verdict}", *(f"\n    {mismatch}" for mismatch in mismatches))

        if arguments.runs > 1 and case["input"]["type"] == "transcript":
            signatures = [outcome_signature(draft)] + [outcome_signature(run_case(case)) for _ in range(arguments.runs - 1)]
            agreement = {key: Counter(signature.get(key) for signature in signatures).most_common(1)[0][1] / arguments.runs for key in signatures[0]}
            print("    agreement:", ", ".join(f"{key} {share:.0%}" for key, share in agreement.items()))

    print(f"\n{passed_cases}/{len(cases)} cases met every expectation. Drafts written to {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
