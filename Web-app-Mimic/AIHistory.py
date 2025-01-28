from dotenv import load_dotenv
import openai
import os
import psycopg2
from datetime import date

# Load environment variables
load_dotenv()

# OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Database connection settings
DB_CONFIG = {
    "dbname": "mimiciii",
    "user": "postgres",
    "password": "123",
    "host": "localhost",
    "port": 5432,
}

# Connect to the database
def connect_to_db(config):
    try:
        connection = psycopg2.connect(**config, options="-c statement_timeout=100000")
        print("Database connection successful.")
        return connection
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None

# Fetch patient data
def fetch_patient_data(connection):
    try:
        with connection.cursor() as cursor:
            # Fetch random patient demographic and admission details
            cursor.execute(
                """
                SELECT p.subject_id, p.gender, p.dob, a.admittime, a.dischtime, a.hadm_id
                FROM mimiciii.patients p
                JOIN mimiciii.admissions a ON p.subject_id = a.subject_id
                WHERE p.subject_id IN (
                    SELECT subject_id
                    FROM mimiciii.patients
                    TABLESAMPLE SYSTEM(1)
                    LIMIT 1
                )
                LIMIT 1;
                """
            )
            patient = cursor.fetchone()
            if not patient:
                print("No patient found.")
                return None, None, None, None, None, None

            # Fetch diagnoses
            cursor.execute(
                """
                SELECT di.icd9_code, dd.long_title
                FROM mimiciii.diagnoses_icd di
                JOIN mimiciii.d_icd_diagnoses dd ON di.icd9_code = dd.icd9_code
                WHERE di.subject_id = %s AND di.hadm_id = %s
                LIMIT 5;
                """,
                (patient[0], patient[5]),
            )
            diagnoses = cursor.fetchall()

            # Fetch events (e.g., vitals, treatments)
            cursor.execute(
                """
                SELECT ce.charttime, d.label, ce.value, ce.valuenum, ce.valueuom
                FROM mimiciii.chartevents ce
                JOIN mimiciii.d_items d ON ce.itemid = d.itemid
                WHERE ce.subject_id = %s AND ce.hadm_id = %s
                LIMIT 5;
                """,
                (patient[0], patient[5]),
            )
            events = cursor.fetchall()

            # Fetch clinical notes
            cursor.execute(
                """
                SELECT n.category, n.text
                FROM mimiciii.noteevents n
                WHERE n.subject_id = %s AND n.hadm_id = %s
                LIMIT 3;
                """,
                (patient[0], patient[5]),  # Correctly use hadm_id
            )
            notes = cursor.fetchall()

            # Fetch lab tests
            cursor.execute(
                """
                SELECT le.charttime, dl.label, le.value, le.valuenum, le.flag
                FROM mimiciii.labevents le
                JOIN mimiciii.d_labitems dl ON le.itemid = dl.itemid
                WHERE le.subject_id = %s AND le.hadm_id = %s
                LIMIT 5;
                """,
                (patient[0], patient[5]),
            )
            lab_tests = cursor.fetchall()

            # Fetch prescriptions
            cursor.execute(
                """
                SELECT drug, formulary_drug_cd, prod_strength, dose_val_rx
                FROM mimiciii.prescriptions
                WHERE subject_id = %s AND hadm_id = %s
                LIMIT 5;
                """,
                (patient[0], patient[5]),
            )
            prescriptions = cursor.fetchall()

            return patient, diagnoses, events, notes, lab_tests, prescriptions
    except Exception as e:
        print(f"Error fetching patient data: {e}")
        return None, None, None, None, None, None

def generate_patient_history_with_gpt(patient, diagnoses, events, notes, lab_tests, prescriptions):
    subject_id, gender, dob, admittime, dischtime, hadm_id = patient
    age = calculate_age(dob, admittime)

    # Format data for the prompt
    diagnoses_text = ", ".join([f"{diag[1]} (ICD-9: {diag[0]})" for diag in diagnoses])
    events_text = "; ".join(
        [f"{event[1]}: {event[2]} {event[4] if event[4] else ''}" for event in events]
    )
    notes_text = "\n".join([f"Category: {note[0]}\nNote: {note[1][:200]}...\n" for note in notes])  # Truncate long notes
    lab_tests_text = ", ".join([f"{test[1]}: {test[3]} ({test[4] if test[4] else 'normal'})" for test in lab_tests])
    prescriptions_text = ", ".join([f"{prescription[0]} ({prescription[2]}, {prescription[3]})" for prescription in prescriptions])

    # ChatGPT prompt
    prompt = f"""
Write a detailed case summary for a patient in the following format:

CASE: A [Case-Specific Title]

History:
Summarize the patient's medical background, reasons for admission, and relevant past conditions.

Examination:
Summarize current findings, vital signs, physical observations, and relevant lab results.

Questions(You should construct this section by asking questions related to the case in a similar way as this. Only ask questions in this section, do not answer them):
- What is the most likely underlying cause for this acute episode?
- What signs would you look for of impending respiratory failure?
# - Outline your management plan for this acute episode?
- What should happen before the patient is discharged?

---

Details:
- Patient ID: {subject_id}
- Age: {age}
- Gender: {'Male' if gender == 'M' else 'Female'}
- Admission Date: {admittime.date()}
- Discharge Date: {dischtime.date() if dischtime else 'N/A'}
- Diagnoses: {diagnoses_text}
- Events: {events_text}
- Lab Tests: {lab_tests_text}
- Prescriptions: {prescriptions_text}
- Clinical Notes:
{notes_text}
    """

    try:
        # Use ChatGPT API
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Use "gpt-4" if available
            messages=[
                {"role": "system", "content": "You are a highly detailed medical assistant generating structured patient case summaries."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1200,
            temperature=0.7
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Error using ChatGPT: {e}")
        return None

# Calculate age at the time of admission
def calculate_age(dob, admittime):
    try:
        age = admittime.year - dob.year - ((admittime.month, admittime.day) < (dob.month, dob.day))
        return age if age >= 0 else "Unknown"  # Handle any inconsistencies
    except Exception as e:
        print(f"Error calculating age: {e}")
        return "Unknown"


if __name__ == "__main__":
    connection = connect_to_db(DB_CONFIG)
    if not connection:
        exit()

    try:
        # Fetch patient data
        patient, diagnoses, events, notes, lab_tests, prescriptions = fetch_patient_data(connection)
        if patient:
            # Generate patient history
            history = generate_patient_history_with_gpt(patient, diagnoses, events, notes, lab_tests, prescriptions)
            if history:
                # Save to file
                with open("formatted_patient_history.txt", "w") as file:
                    file.write(history)
                print("Patient history saved to 'formatted_patient_history.txt'.")
            else:
                print("Failed to generate patient history.")
        else:
            print("No patient data available.")
    finally:
        if connection:
            connection.close()
