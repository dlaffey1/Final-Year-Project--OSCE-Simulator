import json
import ast
import unicodedata
import random
import re

# Normalize text to remove accents, brackets, quotes, and whitespace
def normalize_text(text):
    if not text:
        return ""
    # Remove brackets, quotes, and normalize accents
    cleaned = re.sub(r'[\'"\[\]{}()]', '', text).strip()
    normalized = (
        unicodedata.normalize('NFKD', cleaned)
        .encode('ascii', 'ignore')
        .decode('utf-8')
        .strip()
        .lower()
    )
    return normalized


# Load JSON data
def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as file:
        return json.load(file)


# Parse CSV data
def parse_csv(filepath):
    with open(filepath, 'r', encoding='utf-8-sig') as file:
        lines = file.readlines()
        header = lines[0].strip().split(",")
        data = [dict(zip(header, line.strip().split(",", len(header) - 1))) for line in lines[1:]]
        return data


# Find patients by pathology
def find_patients_by_pathology(data, target_pathology):
    normalized_target = normalize_text(target_pathology)
    print(f"Searching for pathology: '{normalized_target}'")
    patients = []
    for entry in data:
        pathology_raw = entry["PATHOLOGY"]
        pathology = normalize_text(pathology_raw)
        # print(f"Comparing with pathology: Raw: '{pathology_raw}' -> Normalized: '{pathology}'")
        if pathology == normalized_target:
            patients.append(entry)
    return patients


# Translate evidences using JSON
def translate_evidences(evidences, patient_evidences):
    translated = []
    try:
        # Clean and parse patient_evidences string
        cleaned_evidences = re.sub(r'[\'"\[\]]', '', patient_evidences).strip()
        evidence_codes = ast.literal_eval(f"[{cleaned_evidences}]")  # Wrap for safe parsing
        for evidence_code in evidence_codes:
            question = evidences.get(str(evidence_code).strip(), {}).get("question_en", str(evidence_code))
            translated.append(question)
    except (ValueError, SyntaxError) as e:
        print(f"Error parsing EVIDENCES: {patient_evidences} -> {e}")
    return [str(ev) for ev in translated]


# Parse `INITIAL_EVIDENCE`
def parse_initial_evidence(initial_evidence, evidences):
    try:
        cleaned_initial_evidence = re.sub(r'[\'"\[\]]', '', initial_evidence).strip()
        evidence_codes = ast.literal_eval(f"[{cleaned_initial_evidence}]")
        return [
            evidences.get(str(evidence).strip(), {}).get("question_en", str(evidence).strip())
            for evidence in evidence_codes
        ]
    except (ValueError, SyntaxError) as e:
        print(f"Error parsing INITIAL_EVIDENCE: {initial_evidence} -> {e}")
        return ["Unable to parse initial evidence"]


# Create patient history
def create_patient_history(patient, evidences, conditions):
    age = patient["AGE"]
    sex = "male" if patient["SEX"] == "M" else "female"
    pathology = patient["PATHOLOGY"]

    # Translate evidences
    translated_evidences = translate_evidences(evidences, patient.get("EVIDENCES", ""))

    # Parse initial evidence
    initial_evidence = parse_initial_evidence(patient.get("INITIAL_EVIDENCE", ""), evidences)

    # Fetch condition details from the JSON
    condition_key = normalize_text(pathology)
    condition = next(
        (value for key, value in conditions.items() if normalize_text(key) == condition_key),
        {}
    )
    english_name = condition.get("cond-name-eng", pathology)

    history = f"""
    Patient History:
    Age: {age}
    Sex: {sex}
    Pathology: {english_name} ({normalize_text(pathology)})

    Symptoms reported:
    - {", ".join(translated_evidences) if translated_evidences else "None reported"}

    Initial evidence:
    - {", ".join(initial_evidence)}

    Severity: {condition.get('severity', 'Unknown')}
    """
    return history


if __name__ == "__main__":
    # File paths
    conditions_file = "data/release_conditions.json"
    evidences_file = "data/release_evidences.json"
    patient_file = "processed_data/release_train_patients/release_train_patients.csv"

    # Load data
    conditions = load_json(conditions_file)
    evidences = load_json(evidences_file)
    patient_data = parse_csv(patient_file)

    # Target pathology
    target_pathology = "Myasthénie grave"

    # Find matching patients
    matching_patients = find_patients_by_pathology(patient_data, target_pathology)

    if matching_patients:
        # Pick a random patient
        random_patient = random.choice(matching_patients)

        # Generate history for the random patient
        patient_history = create_patient_history(random_patient, evidences, conditions)
        print(patient_history)
    else:
        print(f"No patients found with the pathology '{target_pathology}'.")
