import json
import random
from src.osce_rating import rate_performance, display_feedback
from src.disease_categories import categorize_diseases
import time

# Load the conditions (diseases) with probabilities
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

# Load the symptom-disease mapping with probabilities
def load_symptom_disease_mapping(filepath):
    with open(filepath, 'r', encoding='utf-8') as file:
        data = json.load(file)
        return data

# Function to extract symptoms and antecedents from the condition
import ast  # To safely evaluate string representations of lists

def display_symptoms(patient, conditions, evidences, symptom_disease_mapping):
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

    # Extract and map symptoms with probabilities from symptom_disease_mapping
    for evidence_code in condition.get('symptoms', {}).keys():
        if evidence_code in evidences:
            symptom_name = evidences[evidence_code].get('question_en', evidences[evidence_code].get('name', evidence_code))
            
            # Look for the symptom in the disease mapping
            symptom_list = None
            for symptoms_key, probability in symptom_disease_mapping.get(disease_name, {}).items():
                # Convert the symptom key string back into a list (safe evaluation)
                symptoms_list = ast.literal_eval(symptoms_key)
                if evidence_code in symptoms_list:
                    symptom_list = symptoms_list
                    probability = probability  # get the associated probability

                    try:
                        probability = float(probability)  # Ensure probability is a float
                        symptoms.append(f"Doctor: {symptom_name} (Probability: {probability*100:.2f}%)\nPatient: Yes.")
                    except ValueError:
                        symptoms.append(f"Doctor: {symptom_name} (Probability: Unknown)\nPatient: Yes.")
                    break  # Break out of the loop after finding the matching symptoms
            if not symptom_list:
                symptoms.append(f"Doctor: {symptom_name} (Probability: Unknown)\nPatient: Yes.")
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

def run_cli(conditions, evidences, symptom_disease_mapping):
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

    # Filter conditions based on selected category
    category_diseases = set(disease_categories[selected_category])
    filtered_conditions = {disease: conditions[disease] for disease in category_diseases if disease in conditions}

    if not filtered_conditions:
        print(f"No diseases available for the selected category '{selected_category}'. Exiting.")
        return

    print(f"\nYou selected '{selected_category.capitalize()}'. Starting simulation...\n")

    # Now loop through diseases to simulate the interaction
    for disease_name, condition in filtered_conditions.items():
        print(f"\nDisease: {disease_name}")
        symptoms, antecedents = display_symptoms({'PATHOLOGY': disease_name}, conditions, evidences, symptom_disease_mapping)

        print("\nSymptoms:")
        for symptom in symptoms:
            print(symptom)

        print("\nAntecedents:")
        for antecedent in antecedents:
            print(antecedent)

        correct_name = condition['cond-name-eng']

        start_time = time.time()
        user_guess = input("\nWhat is your diagnosis? ").strip()
        end_time = time.time()

        if user_guess.lower() == correct_name.lower():
            print("✅ Correct! Well done.")
        else:
            print(f"❌ Incorrect. The correct diagnosis is: {correct_name}.")

        # Pass symptom_disease_mapping to rate_performance function
        feedback = rate_performance(
            start_time=start_time,
            end_time=end_time,
            correct_symptoms=[symptom for symptom in symptoms],  # Adjust this to real symptom matching
            user_symptoms=[user_guess],
            correct_disease=correct_name,
            guessed_disease=user_guess,
            symptom_disease_mapping=symptom_disease_mapping  # Pass it here
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
    symptom_mapping_file = "processed_data/symptom_disease_mapping_with_probabilities.json"  # Path to your new mapping file

    # Load data
    conditions = {c['condition_name']: c for c in load_conditions(conditions_file).values()}
    evidences = {e['name']: e for e in load_evidences(evidences_file).values()}
    symptom_disease_mapping = load_symptom_disease_mapping(symptom_mapping_file)

    # Run CLI
    run_cli(conditions, evidences, symptom_disease_mapping)
