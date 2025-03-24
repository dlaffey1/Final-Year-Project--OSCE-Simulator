import json
import os
import openai
import logging
import time
from difflib import SequenceMatcher

# Configuration file names and paths
TEXT2DT_FILE = "Text2DT_train.json"                # Your Text2DT training file
OUTPUT_MAPPING_FILE = "text2dt_mimic_mapping1.json" # Output file for Text2DT records with mimic mappings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Helper functions ---
def clean_json_response(response_text):
    """
    Remove markdown formatting (e.g. ```json ... ```) from the ChatGPT response.
    """
    response_text = response_text.strip()
    if response_text.startswith("```"):
        lines = response_text.splitlines()
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().endswith("```"):
            lines = lines[:-1]
        response_text = "\n".join(lines).strip()
    return response_text

def extract_json_from_response(response_text):
    """
    Extract a JSON object string from the response by locating the first '{' and the last '}'.
    """
    start = response_text.find("{")
    end = response_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return response_text[start:end+1]
    return response_text

def similarity(a, b):
    """Compute the similarity ratio between two strings."""
    return SequenceMatcher(None, a, b).ratio()

def translate_to_english(chinese_text):
    """Translate Chinese text to English using ChatGPT."""
    prompt = f"Translate the following Chinese medical condition into English: '{chinese_text}'"
    logger.info(f"Translating to English: {chinese_text}")
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
        logger.error(f"Error during English translation: {e}")
        return chinese_text  # Fallback

def get_best_mimic_condition(text2dt_condition, profile):
    """
    Ask ChatGPT to determine the best fitting Mimic-III condition for the given Text2DT condition and its decision tree profile.
    The AI is instructed to output a JSON object with the keys:
       - "mimic_condition": a representative Mimic-III condition (string)
       - "icd9_codes": a list of ICD-9 codes associated with that condition
    """
    prompt = f"""
You are a medical coding assistant.
I have a Text2DT condition: "{text2dt_condition}".
Its decision tree profile is as follows:
{json.dumps(profile, ensure_ascii=False, indent=2)}
Based on this information, please select the best fitting Mimic-III condition.
Provide your answer strictly in JSON format as follows:
{{
    "mimic_condition": "<Representative mimic condition>",
    "icd9_codes": ["<ICD-9 code 1>", "<ICD-9 code 2>", ...]
}}
Only provide one mimic condition that best fits the given Text2DT condition and its profile.
"""
    logger.info(f"Asking AI for best Mimic-III condition for: {text2dt_condition}")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a medical coding assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150,
        )
        reply = response["choices"][0]["message"]["content"].strip()
        logger.info(f"AI response for condition '{text2dt_condition}': {reply}")
        reply = clean_json_response(reply)
        reply = extract_json_from_response(reply)
        result = json.loads(reply)
        mimic_condition = result.get("mimic_condition", "No Suitable Group")
        icd9_codes = result.get("icd9_codes", [])
        return mimic_condition, icd9_codes
    except Exception as e:
        logger.error(f"Error obtaining best mimic condition for '{text2dt_condition}': {e}")
        return "No Suitable Group", []

def get_category(text2dt_condition, profile):
    """
    Ask ChatGPT to assign a category to the Text2DT condition based on its decision tree profile.
    Available categories:
       - cardiovascular, respiratory, gastroenterology, musculoskeletal,
         neurological, endocrine, obs and gyne, paediatrics, ENT, ophthalmology,
         dermatology, other
    The AI should output a JSON object with the key "category".
    """
    available_categories = [
        "cardiovascular", "respiratory", "gastroenterology", "musculoskeletal",
        "neurological", "endocrine", "obs and gyne", "paediatrics", "ENT",
        "ophthalmology", "dermatology", "other"
    ]
    prompt = f"""
You are a medical classification assistant.
Given the Text2DT condition: "{text2dt_condition}" and its decision tree profile:
{json.dumps(profile, ensure_ascii=False, indent=2)}
Determine the most appropriate category from the following list:
{", ".join(available_categories)}
Respond strictly in JSON format as follows:
{{
  "category": "<selected category>"
}}
"""
    logger.info(f"Asking AI for category for: {text2dt_condition}")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a medical classification assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=60,
        )
        reply = response["choices"][0]["message"]["content"].strip()
        logger.info(f"AI response for category of '{text2dt_condition}': {reply}")
        reply = clean_json_response(reply)
        reply = extract_json_from_response(reply)
        result = json.loads(reply)
        category = result.get("category", "other").lower()
        # Validate category against available options:
        if category not in available_categories:
            category = "other"
        return category
    except Exception as e:
        logger.error(f"Error obtaining category for '{text2dt_condition}': {e}")
        return "other"

def process_text2dt_record(record):
    """
    Process a single Text2DT record: extract the condition (substring before '@'),
    build the decision tree profile, ask for the best Mimic-III condition and assign a category.
    """
    text = record.get("text", "")
    logger.info(f"Processing Text2DT record with text (first 30 chars): {text[:30]}...")
    condition_name = text.split("@")[0].strip() if "@" in text else text.strip()
    logger.info(f"Extracted condition name: {condition_name}")
    
    # Build profile from the decision tree (only include nodes with role "C")
    profile = []
    tree = record.get("tree", [])
    if not tree:
        logger.info(f"No decision tree found for condition '{condition_name}'.")
    for node in tree:
        if node.get("role") == "C":
            for triple in node.get("triples", []):
                subject, relation, obj = triple
                question = f"Does the patient have {obj} ({relation})?"
                profile.append(question)
    logger.info(f"Built profile for condition '{condition_name}': {profile}")
    
    # Ask the AI for the best matching Mimic-III condition
    mimic_condition, icd9_codes = get_best_mimic_condition(condition_name, profile)
    logger.info(f"AI assigned mimic condition for '{condition_name}': {mimic_condition} with codes: {icd9_codes}")
    
    # Ask the AI for a category assignment
    category = get_category(condition_name, profile)
    logger.info(f"AI assigned category for '{condition_name}': {category}")
    
    return {
        "text2dt_condition": condition_name,
        "mapped_mimic_group": {
            "mimic_condition": mimic_condition,
            "icd9_codes": icd9_codes
        },
        "category": category,
        "profile": profile
    }

def process_all_text2dt_records():
    """Process all Text2DT records and update the output mapping file every 10 records."""
    logger.info("Starting to process all Text2DT records...")
    records = load_text2dt_data()
    if not records:
        logger.error("No Text2DT records to process. Exiting mapping stage.")
        return []
    processed = []
    for idx, rec in enumerate(records):
        try:
            mapped_record = process_text2dt_record(rec)
            processed.append(mapped_record)
        except Exception as e:
            logger.error(f"Error processing a Text2DT record: {e}")
        
        # Update output file every 10 records
        if (idx + 1) % 10 == 0:
            try:
                with open(OUTPUT_MAPPING_FILE, "w", encoding="utf-8") as f:
                    json.dump(processed, f, ensure_ascii=False, indent=2)
                logger.info(f"Updated {OUTPUT_MAPPING_FILE} after processing {idx+1} records.")
            except Exception as e:
                logger.error(f"Error updating output mapping file: {e}")
            time.sleep(1)
    
    # Final update after processing all records
    try:
        with open(OUTPUT_MAPPING_FILE, "w", encoding="utf-8") as f:
            json.dump(processed, f, ensure_ascii=False, indent=2)
        logger.info(f"Final update: Processed {len(processed)} Text2DT records; output saved to {OUTPUT_MAPPING_FILE}.")
    except Exception as e:
        logger.error(f"Error writing final output mapping file: {e}")
    
    return processed

def query_by_category(processed_records, category):
    """
    Given a list of processed records and a category string,
    return all records that belong to that category.
    """
    return [rec for rec in processed_records if rec.get("category", "").lower() == category.lower()]

def load_text2dt_data():
    """Load Text2DT training data from file."""
    logger.info("Attempting to load Text2DT data from file...")
    if not os.path.exists(TEXT2DT_FILE):
        logger.error(f"Text2DT data file {TEXT2DT_FILE} not found.")
        return []
    try:
        with open(TEXT2DT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data)} Text2DT records from {TEXT2DT_FILE}.")
    except Exception as e:
        logger.error(f"Error loading Text2DT data: {e}")
        data = []
    return data

def main():
    logger.info("Script started.")
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not set in environment.")
        return
    
    processed_text2dt = process_all_text2dt_records()
    if processed_text2dt:
        logger.info("Final processed Text2DT mapping:")
        logger.info(json.dumps(processed_text2dt, ensure_ascii=False, indent=2))
    else:
        logger.error("No Text2DT mapping was produced.")
    
    # Example: Query by category. Change 'cardiovascular' to the desired category.
    queried = query_by_category(processed_text2dt, "cardiovascular")
    logger.info(f"Records in 'cardiovascular' category: {len(queried)}")
    
    if os.path.exists(OUTPUT_MAPPING_FILE):
        try:
            with open(OUTPUT_MAPPING_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                logger.info(f"Final check: {OUTPUT_MAPPING_FILE} exists and contains data.")
            else:
                logger.error(f"Final check: {OUTPUT_MAPPING_FILE} exists but is empty!")
        except Exception as e:
            logger.error(f"Final check: Error reading {OUTPUT_MAPPING_FILE}: {e}")
    else:
        logger.error(f"Final check: {OUTPUT_MAPPING_FILE} does not exist!")
    
    logger.info("Script finished.")

if __name__ == "__main__":
    main()
