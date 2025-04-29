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
def fetch_patient_data(client: bigquery.Client, subject_id=None):
    """
    Fetch a patient (random or by subject_id) by joining PATIENTS and ADMISSIONS,
    then retrieve additional data for that patient:
      - Diagnoses (DIAGNOSES_ICD + D_ICD_DIAGNOSES)
      - Admissions (full details from ADMISSIONS)
      - Clinical Notes (NOTEEVENTS)
      - Lab Tests (LABEVENTS + D_LABITEMS)
      - Prescriptions (PRESCRIPTIONS)
      - ICU Stays (ICUSTAYS)
      - Transfers (TRANSFERS)
      - Procedures (PROCEDURES_ICD + D_ICD_PROCEDURES)
      - Services (SERVICES)
      - Microbiology (MICROBIOLOGYEVENTS)
      
    Returns a tuple of:
      (patient, diagnoses, admissions, notes, lab_tests, prescriptions,
       icu_stays, transfers, procedures, services, microbiology)
    """
    try:
        # 1. GET PATIENT (random if no subject_id provided)
        if subject_id is None:
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
        else:
            query_patient = f"""
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
                WHERE p.subject_id = {subject_id}
                ORDER BY a.admittime DESC
                LIMIT 1;
            """
        query_job = client.query(query_patient)
        rows = list(query_job.result())
        if not rows:
            logger.warning("No patient found.")
            return (None, None, None, None, None, None, None, None, None, None, None)
        
        patient = dict(rows[0])
        subject_id = patient["subject_id"]
        hadm_id = patient["hadm_id"]

        # 2. ADMISSIONS (full details)
        query_admissions = f"""
            SELECT 
                hadm_id,
                subject_id,
                admittime,
                dischtime,
                admission_type,
                admission_location,
                discharge_location,
                insurance,
                marital_status,
                ethnicity
            FROM `fyp-project-451413.mimic_iii_local.ADMISSIONS`
            WHERE subject_id = {subject_id}
            ORDER BY admittime DESC
            LIMIT 1;
        """
        admissions_rows = list(client.query(query_admissions).result())
        admissions = [dict(row) for row in admissions_rows]

        # 3. DIAGNOSES (ICD codes and their descriptions)
        query_diagnoses = f"""
            SELECT
                d.icd9_code,
                d.seq_num,
                dd.long_title AS diagnosis_title
            FROM `fyp-project-451413.mimic_iii_local.DIAGNOSES_ICD` AS d
            LEFT JOIN `fyp-project-451413.mimic_iii_local.D_ICD_DIAGNOSES` AS dd
              ON d.icd9_code = dd.icd9_code
            WHERE d.subject_id = {subject_id}
              AND d.hadm_id = {hadm_id}
            ORDER BY d.seq_num;
        """
        diagnoses_rows = list(client.query(query_diagnoses).result())
        diagnoses = [dict(row) for row in diagnoses_rows]

        # 4. ICU STAYS
        query_icu = f"""
            SELECT
                icustay_id,
                first_careunit,
                last_careunit,
                intime,
                outtime,
                los
            FROM `fyp-project-451413.mimic_iii_local.ICUSTAYS`
            WHERE subject_id = {subject_id}
              AND hadm_id = {hadm_id}
            ORDER BY intime;
        """
        icu_rows = list(client.query(query_icu).result())
        icu_stays = [dict(row) for row in icu_rows]

        # 5. TRANSFERS (using correct field names)
        query_transfers = f"""
            SELECT
                eventtype,
                curr_careunit,
                prev_careunit,
                intime,
                outtime,
                los
            FROM `fyp-project-451413.mimic_iii_local.TRANSFERS`
            WHERE subject_id = {subject_id}
              AND hadm_id = {hadm_id}
            ORDER BY intime DESC
            LIMIT 20;
        """
        transfers_rows = list(client.query(query_transfers).result())
        transfers = [dict(row) for row in transfers_rows]

        # 6. PROCEDURES (with descriptions; updated to use icd9_code)
        query_procedures = f"""
            SELECT
                p.icd9_code AS procedure_code,
                p.seq_num,
                dp.long_title AS procedure_title
            FROM `fyp-project-451413.mimic_iii_local.PROCEDURES_ICD` AS p
            LEFT JOIN `fyp-project-451413.mimic_iii_local.D_ICD_PROCEDURES` AS dp
              ON p.icd9_code = dp.icd9_code
            WHERE p.subject_id = {subject_id}
              AND p.hadm_id = {hadm_id}
            ORDER BY p.seq_num;
        """
        procedures_rows = list(client.query(query_procedures).result())
        procedures = [dict(row) for row in procedures_rows]

        # 7. SERVICES
        query_services = f"""
            SELECT
                subject_id,
                hadm_id,
                transfertime,
                prev_service,
                curr_service
            FROM `fyp-project-451413.mimic_iii_local.SERVICES`
            WHERE subject_id = {subject_id}
              AND hadm_id = {hadm_id}
            ORDER BY transfertime DESC;
        """
        services_rows = list(client.query(query_services).result())
        services = [dict(row) for row in services_rows]

        # 8. LAB TESTS (with test names)
        query_lab_tests = f"""
            SELECT
                l.itemid,
                d.label AS test_name,
                l.charttime,
                l.value,
                l.valuenum,
                l.valueuom,
                l.flag
            FROM `fyp-project-451413.mimic_iii_local.LABEVENTS` AS l
            LEFT JOIN `fyp-project-451413.mimic_iii_local.D_LABITEMS` AS d
              ON l.itemid = d.itemid
            WHERE l.subject_id = {subject_id}
              AND l.hadm_id = {hadm_id}
            ORDER BY l.charttime DESC
            LIMIT 10;
        """
        lab_rows = list(client.query(query_lab_tests).result())
        lab_tests = [dict(row) for row in lab_rows]

        # 9. PRESCRIPTIONS
        query_prescriptions = f"""
            SELECT
                startdate,
                enddate,
                drug_type,
                drug,
                dose_val_rx,
                dose_unit_rx,
                route
            FROM `fyp-project-451413.mimic_iii_local.PRESCRIPTIONS`
            WHERE subject_id = {subject_id}
              AND hadm_id = {hadm_id}
            ORDER BY startdate DESC
            LIMIT 10;
        """
        presc_rows = list(client.query(query_prescriptions).result())
        prescriptions = [dict(row) for row in presc_rows]

        # 10. MICROBIOLOGY
        query_microbiology = f"""
            SELECT
                chartdate,
                spec_type_desc,
                org_name,
                isolate_num,
                ab_name,
                interpretation
            FROM `fyp-project-451413.mimic_iii_local.MICROBIOLOGYEVENTS`
            WHERE subject_id = {subject_id}
              AND hadm_id = {hadm_id}
            ORDER BY chartdate DESC
            LIMIT 20;
        """
        micro_rows = list(client.query(query_microbiology).result())
        microbiology = [dict(row) for row in micro_rows]

        # 11. CLINICAL NOTES
        query_notes = f"""
            SELECT
                chartdate,
                category,
                description,
                text
            FROM `fyp-project-451413.mimic_iii_local.NOTEEVENTS`
            WHERE subject_id = {subject_id}
              AND hadm_id = {hadm_id}
            ORDER BY chartdate DESC
            LIMIT 5;
        """
        notes_rows = list(client.query(query_notes).result())
        notes = [dict(row) for row in notes_rows]

        return (patient, diagnoses, admissions, notes, lab_tests, prescriptions,
                icu_stays, transfers, procedures, services, microbiology)

    except Exception as e:
        logger.exception("Error fetching patient data: %s", e)
        return (None, None, None, None, None, None, None, None, None, None, None)

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
