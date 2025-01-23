import os
import json

# Paths to relevant files
project_folder = os.path.dirname(os.getcwd())  # Adjust as per your directory
processed_data_folder = os.path.join(project_folder, "processed_data")
conditions_file = os.path.join(processed_data_folder, "release_conditions.json")
evidences_file = os.path.join(processed_data_folder, "release_evidences.json")
symptom_condition_file = os.path.join(processed_data_folder, "symptom_condition_mapping.json")
output_translated_file = os.path.join(processed_data_folder, "translated_symptom_condition.json")

# Load JSON files
def load_json(file_path):
    """Loads a JSON file and returns its content."""
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from file {file_path}: {e}")
            return None
    else:
        print(f"File not found: {file_path}")
        return None

# Translation function
def translate_data(conditions, evidences, symptom_conditions):
    """Translates symptom and condition names from French to English."""
    translated_data = {}

    # Translate each symptom in symptom_conditions
    for symptom, associated_diseases in symptom_conditions.items():
        # Translate symptom using the 'question_en' field or default to the original symptom
        translated_symptom = evidences.get(symptom, {}).get("question_en", symptom)
        translated_data[translated_symptom] = []

        # Translate associated diseases
        for disease in associated_diseases:
            # Translate disease name using 'cond-name-eng' or default to the original name
            translated_disease = conditions.get(disease, {}).get("cond-name-eng", disease)
            translated_data[translated_symptom].append(translated_disease)

    return translated_data

# Main execution
if __name__ == "__main__":
    # Load data from files
    conditions = load_json(conditions_file)
    evidences = load_json(evidences_file)
    symptom_conditions = load_json(symptom_condition_file)

    # Validate loaded data
    if conditions and evidences and symptom_conditions:
        # Translate the data
        translated_data = translate_data(conditions, evidences, symptom_conditions)

        # Save translated data to a JSON file
        try:
            with open(output_translated_file, 'w', encoding='utf-8') as output_file:
                json.dump(translated_data, output_file, indent=4, ensure_ascii=False)
            print(f"Translated data saved to: {output_translated_file}")
        except IOError as e:
            print(f"Error saving translated data to file {output_translated_file}: {e}")
    else:
        print("One or more input files could not be loaded. Check file paths and JSON formatting.")
