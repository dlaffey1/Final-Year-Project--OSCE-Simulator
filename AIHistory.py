import json
import os
import re  # Ensure this import is present!
import openai
import logging
from google.cloud import bigquery  # Import BigQuery client
from datetime import date
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set your OpenAI API key from the environment
openai.api_key = os.getenv("OPENAI_API_KEY")

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# Updated fetch_patient_data to use BigQuery
def fetch_patient_data(client: bigquery.Client):
    try:
        # Query to get one random patient by joining PATIENTS and ADMISSIONS
        query_patient = """
            SELECT 
                p.subject_id, 
                p.gender, 
                p.dob, 
                a.admittime, 
                a.dischtime, 
                a.hadm_id
            FROM `fyp-project-451413.mimic_iii_local.PATIENTS` AS p
            JOIN `fyp-project-451413.mimic_iii_local.ADMISSIONS` AS a
              ON p.subject_id = a.subject_id
            ORDER BY RAND()
            LIMIT 1;
        """
        query_job = client.query(query_patient)
        rows = list(query_job.result())
        if not rows:
            logger.warning("No patient found.")
            return None, None, None, None, None, None
        patient = rows[0]
        
        # For the other data pieces, add additional queries or return placeholders.
        diagnoses = "Diagnoses data placeholder"  
        events = "Events data placeholder"
        notes = "Notes data placeholder"
        lab_tests = "Lab tests data placeholder"
        prescriptions = "Prescriptions data placeholder"
        
        return patient, diagnoses, events, notes, lab_tests, prescriptions
    except Exception as e:
        logger.exception("Error fetching patient data: %s", e)
        return None, None, None, None, None, None


# Calculate age at the time of admission
def calculate_age(dob, admittime):
    try:
        age = admittime.year - dob.year - ((admittime.month, admittime.day) < (dob.month, dob.day))
        return age if age >= 0 else "Unknown"
    except Exception as e:
        logger.error("Error calculating age: %s", e)
        return "Unknown"

# Generate patient history using ChatGPT
def generate_patient_history_with_gpt(patient, diagnoses, events, notes, lab_tests, prescriptions):
    subject_id, gender, dob, admittime, dischtime, hadm_id = patient
    age = calculate_age(dob, admittime)

    # Format the data for the prompt (modify as needed)
    diagnoses_text = diagnoses
    events_text = events
    notes_text = notes
    lab_tests_text = lab_tests
    prescriptions_text = prescriptions

    prompt = f"""
You are provided with the following patient data:
Patient Info: {patient}
Diagnoses: {diagnoses_text}
Events: {events_text}
Notes: {notes_text}
Lab tests: {lab_tests_text}
Prescriptions: {prescriptions_text}

Please generate a structured patient history under these headings:
1) Presenting complaint (PC)
2) History of presenting complaint (HPC)
3) Past medical history (PMHx)
4) Drug history (DHx)
5) Family history (FHx)
6) Social history (SHx)
7) Systems review (SR)

Return the entire result as valid JSON with each heading as a field, like:
{{
  "PC": "...",
  "HPC": "...",
  "PMHx": "...",
  "DHx": "...",
  "FHx": "...",
  "SHx": "...",
  "SR": "..."
}}

Make sure the JSON is valid and includes each heading, even if empty.
"""
    logger.debug("Constructed prompt for generate_history: %s", prompt)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # or "gpt-4" if available and desired
            messages=[
                {"role": "system", "content": "You are a medical assistant providing structured patient histories."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.7,
        )
        history_response = response["choices"][0]["message"]["content"].strip()
        logger.info("ChatGPT raw response (generate_history): %s", history_response)
    except Exception as e:
        logger.error("Error using ChatGPT: %s", e)
        return None

    try:
        history_data = json.loads(history_response)
    except json.JSONDecodeError:
        logger.warning("GPT returned invalid JSON; storing entire response in 'PC' only.")
        history_data = {
            "PC": history_response,
            "HPC": "",
            "PMHx": "",
            "DHx": "",
            "FHx": "",
            "SHx": "",
            "SR": ""
        }

    logger.info("Final structured history: %s", history_data)
    return history_data

if __name__ == "__main__":
    try:
        # Initialize BigQuery client (make sure your GOOGLE_APPLICATION_CREDENTIALS env variable is set)
        client = bigquery.Client()
        logger.info("BigQuery client initialized successfully.")
    except Exception as e:
        logger.error("Error initializing BigQuery client: %s", e)
        exit(1)

    try:
        patient, diagnoses, events, notes, lab_tests, prescriptions = fetch_patient_data(client)
        if patient:
            history_data = generate_patient_history_with_gpt(patient, diagnoses, events, notes, lab_tests, prescriptions)
            if history_data:
                with open("formatted_patient_history.txt", "w") as file:
                    file.write(json.dumps(history_data, indent=2))
                print("Patient history saved to 'formatted_patient_history.txt'.")
            else:
                print("Failed to generate patient history.")
        else:
            print("No patient data available.")
    except Exception as e:
        logger.exception("An unexpected error occurred: %s", e)
