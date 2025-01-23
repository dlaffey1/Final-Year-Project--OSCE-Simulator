import os
import json
import pandas as pd

# Adjust the path to match your directory structure
project_folder = os.path.dirname(os.getcwd())  # This will point to the root of your project
print("Project Folder:", project_folder)

# Define the paths to the dataset files
data_folder = os.path.join(project_folder, "data")  # Path to the data folder
processed_data_folder = os.path.join(project_folder, "processed_data")  # Path to the processed_data folder

# Paths to the JSON files in the "data" folder
evidences_file = os.path.join(data_folder, "release_evidences.json")  # Adjusted path for the evidence file
conditions_file = os.path.join(data_folder, "release_conditions.json")  # Adjusted path for the conditions file

# Function to load the data from JSON files
def load_data():
    with open(evidences_file, 'r') as f:
        evidences = json.load(f)
    
    with open(conditions_file, 'r') as f:
        conditions = json.load(f)
    
    return evidences, conditions

# Function to check keyword relationships between symptoms and conditions
def create_symptom_condition_mapping(evidences, conditions):
    evidence_df = pd.DataFrame(evidences)
    condition_df = pd.DataFrame(conditions)

    # Print column names of the conditions DataFrame
    print("Columns in conditions_df:", condition_df.columns)

    symptom_condition_mapping = {}

    # Iterate through all symptoms and try to match keywords from condition names
    for symptom in evidence_df.columns:
        matching_conditions = []
        for condition in condition_df.columns:  # Iterate over condition names in condition_df
            # Check if any of the condition name contains the symptom (case insensitive)
            if any(keyword.lower() in condition.lower() for keyword in symptom.split("_")):
                matching_conditions.append(condition)
        
        if matching_conditions:
            symptom_condition_mapping[symptom] = matching_conditions

    return symptom_condition_mapping

# Generate the symptom-condition mapping
evidences, conditions = load_data()
symptom_condition_mapping = create_symptom_condition_mapping(evidences, conditions)

# Print some sample mappings
for symptom, conditions in list(symptom_condition_mapping.items())[:5]:  # Display the first 5 mappings
    print(f"Symptom: {symptom} -> Conditions: {', '.join(conditions)}")
# Save the symptom-condition mappings to a JSON file
output_mapping_file = os.path.join(processed_data_folder, "symptom_condition_mapping.json")
with open(output_mapping_file, 'w') as f:
    json.dump(symptom_condition_mapping, f, indent=4)

print(f"Symptom-condition mappings saved to: {output_mapping_file}")
