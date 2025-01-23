import json
import random
import zipfile
import csv
from src.osce_rating import rate_performance, display_feedback
from src.disease_categories import categorize_diseases
import time

# Load the conditions (diseases)
def load_conditions(filepath):
    with open(filepath, 'r', encoding='utf-8') as file:
        data = json.load(file)
        if isinstance(data, dict):  # Ensure the JSON structure is a dictionary
            return data
        else:
            raise ValueError("Unexpected JSON format in release_conditions.json")

# Load the evidences (symptoms and antecedents)
def load_evidences(filepath):
    with open(filepath, 'r', encoding='utf-8') as file:
        data = json.load(file)
        if isinstance(data, dict):  # Ensure the JSON structure is a dictionary
            return data
        else:
            raise ValueError("Unexpected JSON format in release_evidences.json")

# Extract patient cases from a zipped CSV file
def load_patients(zip_filepath):
    with zipfile.ZipFile(zip_filepath, 'r') as zip_ref:
        with zip_ref.open(zip_ref.namelist()[0]) as file:
            reader = csv.DictReader(file.read().decode('utf-8').splitlines())
            return [row for row in reader]

def display_symptoms(patient, conditions, evidences):
    symptoms = []
    antecedents = []
    missing_keys = []  # Collect keys that are not mapped

    # Get the correct disease and its evidence codes
    disease_name = patient['PATHOLOGY']
    if disease_name not in conditions:
        print(f"⚠️ Condition '{disease_name}' not found in conditions!")
        return symptoms, antecedents

    # Retrieve the condition details
    condition = conditions[disease_name]

    # Extract and map symptoms
    for evidence_code in condition.get('symptoms', {}).keys():
        if evidence_code in evidences:
            symptom_name = evidences[evidence_code].get('question_en', evidences[evidence_code].get('name', evidence_code))
            symptoms.append(f"Doctor: {symptom_name}\nPatient: Yes.")
        else:
            symptoms.append(f"Doctor: Unknown symptom ({evidence_code})\nPatient: Yes.")
            missing_keys.append(evidence_code)

    # Extract and map antecedents
    for evidence_code in condition.get('antecedents', {}).keys():
        if evidence_code in evidences:
            antecedent_name = evidences[evidence_code].get('question_en', evidences[evidence_code].get('name', evidence_code))
            antecedents.append(f"Doctor: {antecedent_name}\nPatient: Yes.")
        else:
            antecedents.append(f"Doctor: Unknown antecedent ({evidence_code})\nPatient: Yes.")
            missing_keys.append(evidence_code)

    # Notify about missing mappings for debugging
    if missing_keys:
        print(f"⚠️ Missing mappings for: {', '.join(missing_keys)}")
        print("🔍 Please check if these codes exist in release_evidences.json")

    return symptoms, antecedents


def run_cli(patients, conditions, evidences):
    # Categorize diseases at the start
    disease_categories = categorize_diseases(conditions)

    # Let the user choose a category
    print("Available categories:")
    for category in disease_categories:
        print(f"- {category.capitalize()} ({len(disease_categories[category])} diseases)")
    
    selected_category = input("\nSelect a category to proceed: ").strip().lower()
    if selected_category not in disease_categories or not disease_categories[selected_category]:
        print("Invalid category or no diseases in selected category. Exiting.")
        return

    # Filter patients based on selected category
    category_diseases = set(disease_categories[selected_category])
    filtered_patients = [p for p in patients if p["PATHOLOGY"] in category_diseases]

    if not filtered_patients:
        print(f"No patients available for the selected category '{selected_category}'. Exiting.")
        return

    print(f"\nYou selected '{selected_category.capitalize()}'. Starting simulation...\n")

    while True:
        patient = random.choice(filtered_patients)
        print("\nA new patient presents with the following symptoms and history:")

        # Extract symptoms and antecedents dynamically from patient data
        symptoms, antecedents = display_symptoms(patient, conditions, evidences)

        print("\nSymptoms:")
        for symptom in symptoms:
            print(symptom)

        print("\nAntecedents:")
        for antecedent in antecedents:
            print(antecedent)

        correct_disease = patient['PATHOLOGY']
        correct_name = conditions[correct_disease]['cond-name-eng']
        correct_symptoms = [e for e in patient['EVIDENCES'].strip("[]").split(", ")]

        start_time = time.time()
        user_guess = input("\nWhat is your diagnosis? ").strip()
        end_time = time.time()

        if user_guess.lower() == correct_name.lower():
            print("✅ Correct! Well done.")
        else:
            print(f"❌ Incorrect. The correct diagnosis is: {correct_name}.")

        # Rate performance dynamically
        feedback = rate_performance(
            start_time=start_time,
            end_time=end_time,
            correct_symptoms=correct_symptoms,
            user_symptoms=[user_guess],
            correct_disease=correct_name,
            guessed_disease=user_guess
        )
        display_feedback(feedback)

        play_again = input("\nDo you want to try another case? (yes/no): ").strip().lower()
        if play_again != 'yes':
            print("Goodbye!")
            break


# Main function
if __name__ == "__main__":
    # File paths
    conditions_file = "data/release_conditions.json"
    evidences_file = "data/release_evidences.json"
    train_zip_file = "data/release_train_patients.zip"

    # Load data
    conditions = {c['condition_name']: c for c in load_conditions(conditions_file).values()}
    evidences = {e['name']: e for e in load_evidences(evidences_file).values()}
    patients = load_patients(train_zip_file)

    # Run CLI
    run_cli(patients, conditions, evidences)
