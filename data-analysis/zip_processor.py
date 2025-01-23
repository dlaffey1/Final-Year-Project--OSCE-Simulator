import os
import pandas as pd
import json

# Adjust the path to match your directory structure
project_folder = os.path.dirname(os.getcwd())  # This will point to the root of your project
print("Project Folder:", project_folder)

# Define the base path to the processed_data folder
processed_data_folder = os.path.join(project_folder, "processed_data")  # Path to the processed_data folder

# Define the paths to the respective subfolders for each dataset
test_folder = os.path.join(processed_data_folder, "release_test_patients")  # Path to the folder containing release_test_patients
train_folder = os.path.join(processed_data_folder, "release_train_patients")  # Path to the folder containing release_train_patients
validate_folder = os.path.join(processed_data_folder, "release_validate_patients")  # Path to the folder containing release_validate_patients

# Paths to the CSV files inside the respective folders
test_file_path = os.path.join(test_folder, "release_test_patients.csv")
train_file_path = os.path.join(train_folder, "release_train_patients.csv")
validate_file_path = os.path.join(validate_folder, "release_validate_patients.csv")

# Function to load the CSV files and return DataFrame
def load_csv(file_path):
    if os.path.exists(file_path):
        return pd.read_csv(file_path)
    else:
        print(f"The file {file_path} does not exist.")
        return None

# Load the data
train_data = load_csv(train_file_path)
test_data = load_csv(test_file_path)
validate_data = load_csv(validate_file_path)

# Function to create symptom-disease mapping with probabilities
def create_symptom_disease_mapping(train_data, test_data, validate_data):
    symptom_disease_mapping = {}

    # Combine data from all CSVs
    all_data = pd.concat([train_data[['EVIDENCES', 'PATHOLOGY']],
                          test_data[['EVIDENCES', 'PATHOLOGY']],
                          validate_data[['EVIDENCES', 'PATHOLOGY']]])

    print(f"Combined Data Shape: {all_data.shape}")
    print("Preview of combined data:")
    print(all_data.head(3))  # Preview to ensure data is correctly loaded

    # Iterate over each disease
    for disease in all_data['PATHOLOGY'].unique():
        print(f"Processing disease: {disease}")  # Debugging line to check the disease being processed

        disease_data = all_data[all_data['PATHOLOGY'] == disease]
        
        # Initialize a dictionary for this disease
        symptom_probabilities = {}

        # Total number of patients diagnosed with this disease
        total_patients_for_disease = disease_data.shape[0]

        # For each symptom (EVIDENCES column) associated with the disease
        for symptom in disease_data['EVIDENCES'].unique():
            print(f"  Processing symptom: {symptom}")  # Debugging line to check symptom being processed
            
            # Count how many times this symptom occurs for this disease
            count_symptom = disease_data[disease_data['EVIDENCES'] == symptom].shape[0]
            
            # Calculate the probability (simple frequency count / total occurrences of the disease)
            prob = count_symptom / total_patients_for_disease
            
            # Store the calculated probability for the symptom
            symptom_probabilities[symptom] = prob

        # Add the disease and its associated symptom probabilities to the mapping
        symptom_disease_mapping[disease] = symptom_probabilities

    return symptom_disease_mapping

# Create the symptom-disease mapping with probabilities
print("Creating symptom-disease mapping...")
symptom_disease_mapping = create_symptom_disease_mapping(train_data, test_data, validate_data)

# Save the mapping to a JSON file
output_mapping_file = os.path.join(processed_data_folder, "symptom_disease_mapping_with_probabilities.json")
with open(output_mapping_file, 'w') as f:
    json.dump(symptom_disease_mapping, f, indent=4)

print(f"Symptom-disease mapping with probabilities saved to: {output_mapping_file}")
