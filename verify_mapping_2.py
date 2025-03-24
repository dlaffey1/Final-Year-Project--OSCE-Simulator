import json
import os
import openai
import logging
import random
import time
from difflib import get_close_matches
from google.cloud import bigquery

# Configuration file names and paths
TEXT2DT_MAPPING_FILE = "text2dt_mimic_mapping1.json"  # New mapping file with mapped Text2DT records
VERIFICATION_OUTPUT_FILE = "verification_output.json"  # Output file for verification results

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Helper functions ---
def load_text2dt_mapping():
    if not os.path.exists(TEXT2DT_MAPPING_FILE):
        logger.error(f"Text2DT mapping file {TEXT2DT_MAPPING_FILE} not found.")
        return []
    with open(TEXT2DT_MAPPING_FILE, "r", encoding="utf-8") as f:
        mapping_data = json.load(f)
    logger.info(f"Loaded {len(mapping_data)} mapped Text2DT records from {TEXT2DT_MAPPING_FILE}.")
    return mapping_data

def pick_random_text2dt_record(mapping_data):
    if not mapping_data:
        logger.error("No mapped Text2DT records available.")
        return None
    selected_record = random.choice(mapping_data)
    logger.info(f"Selected Text2DT record with condition: '{selected_record.get('text2dt_condition', 'N/A')}'")
    return selected_record

def query_condition_details(codes):
    client = bigquery.Client()
    query = """
    SELECT i.icd9_code, d.long_title AS description
    FROM `fyp-project-451413.mimic_iii_local.DIAGNOSES_ICD` AS i
    JOIN `fyp-project-451413.mimic_iii_local.D_ICD_DIAGNOSES` AS d
      ON i.icd9_code = d.icd9_code
    WHERE i.icd9_code IN UNNEST(@codes)
    GROUP BY i.icd9_code, d.long_title
    ORDER BY i.icd9_code
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("codes", "STRING", codes)
        ]
    )
    query_job = client.query(query, job_config=job_config)
    details = [
        {"icd9_code": row.icd9_code, "description": row.description}
        for row in query_job.result()
    ]
    logger.info(f"Queried {len(details)} condition details from BigQuery.")
    return details

def translate_to_chinese(english_text):
    prompt = f"Translate the following English medical condition into Chinese: '{english_text}'"
    logger.info(f"Translating to Chinese: {english_text}")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a medical translation assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=60,
        )
        translation = response["choices"][0]["message"]["content"].strip()
        logger.info(f"Translation result: {translation}")
        return translation
    except Exception as e:
        logger.error(f"Error during translation: {e}")
        return english_text  # Fallback to original

def verify_mapping_with_ai(mimic_condition, codes, condition_details, text2dt_condition, text2dt_profile):
    prompt = f"""
You are a medical coding assistant.
I have a Mimic-III group with the name: "{mimic_condition}".
This group represents the following ICD-9 codes: {codes}.
The database reports the following details for these codes:
{json.dumps(condition_details, ensure_ascii=False, indent=2)}

I also have a Text2DT condition (in Chinese) and its decision tree profile:
Condition: "{text2dt_condition}"
Profile: {json.dumps(text2dt_profile, ensure_ascii=False, indent=2)}

Please verify whether the English group name "{mimic_condition}" is an accurate and appropriate translation for the above Text2DT condition.
Provide a brief explanation and then state either "Correct" or "Incorrect".
"""
    logger.info(f"Sending verification prompt to ChatGPT for group '{mimic_condition}'")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a medical coding assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200,
        )
        answer = response["choices"][0]["message"]["content"].strip()
        logger.info(f"ChatGPT verification response: {answer}")
        return answer
    except Exception as e:
        logger.error(f"Error during verification: {e}")
        return "Error during verification."

def main():
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not set in environment.")
        return

    mapping_data = load_text2dt_mapping()
    if not mapping_data:
        return

    selected_record = pick_random_text2dt_record(mapping_data)
    if not selected_record:
        logger.error("No record selected.")
        return

    # For the new format, check that "mapped_mimic_group" contains a valid "mimic_condition" and non-empty "icd9_codes"
    mimic_group = selected_record.get("mapped_mimic_group", {})
    mimic_condition = mimic_group.get("mimic_condition")
    codes = mimic_group.get("icd9_codes", [])
    text2dt_condition = selected_record.get("text2dt_condition", "Not found")
    text2dt_profile = selected_record.get("profile", [])

    if not mimic_condition or not codes:
        logger.error("Selected record does not have a valid mimic group.")
        return

    condition_details = query_condition_details(codes)
    translated_group = translate_to_chinese(mimic_condition)
    logger.info(f"Translated group name: {translated_group}")

    verification = verify_mapping_with_ai(mimic_condition, codes, condition_details, text2dt_condition, text2dt_profile)

    output = {
        "mimic_condition": mimic_condition,
        "icd9_codes": codes,
        "condition_details": condition_details,
        "text2dt_condition": text2dt_condition,
        "text2dt_profile": text2dt_profile,
        "verification": verification
    }

    try:
        with open(VERIFICATION_OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logger.info(f"Verification output saved to {VERIFICATION_OUTPUT_FILE}")
    except Exception as e:
        logger.error(f"Error writing verification output file: {e}")
    
    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
