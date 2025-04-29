import json
import os
import openai
import logging
import random
import time
from difflib import get_close_matches, SequenceMatcher
from google.cloud import bigquery

# Configuration file names and paths
MIMIC_MAPPING_FILE = "mimic_mapping.json"         # Generated mimic mapping file: representative group -> list of ICD-9 codes
TEXT2DT_FILE = "Text2DT_train.json"                 # Your Text2DT training file
OUTPUT_MAPPING_FILE = "text2dt_mimic_mapping.json"  # Output file for Text2DT records with mimic mappings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 50  # Adjust batch size if needed

# Set a higher similarity threshold to be more strict
SIMILARITY_THRESHOLD = 0.8  

# --- Helper functions ---
def clean_json_response(response_text):
    """Remove markdown formatting (e.g. ```json ... ```) from the ChatGPT response."""
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
    """Extract a JSON object string from the response by locating the first '{' and the last '}'."""
    start = response_text.find("{")
    end = response_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return response_text[start:end+1]
    return response_text

def similarity(a, b):
    """Compute the similarity ratio between two strings."""
    return SequenceMatcher(None, a, b).ratio()

# New: Translate Chinese text to English
def translate_to_english(chinese_text):
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

# =============================
# 1. Query BigQuery for all mimic conditions (no filtering)
# =============================
def fetch_conditions_from_bigquery():
    logger.info("Starting to fetch conditions from BigQuery...")
    client = bigquery.Client()
    query = """
    SELECT DISTINCT i.icd9_code, d.long_title AS description
    FROM `fyp-project-451413.mimic_iii_local.DIAGNOSES_ICD` AS i
    JOIN `fyp-project-451413.mimic_iii_local.D_ICD_DIAGNOSES` AS d
      ON i.icd9_code = d.icd9_code
    ORDER BY i.icd9_code
    """
    query_job = client.query(query)
    results = query_job.result()
    conditions = [{"icd9_code": row.icd9_code, "description": row.description} for row in results]
    logger.info(f"Fetched {len(conditions)} conditions from BigQuery.")
    return conditions

# =============================
# 2. Group conditions using ChatGPT (with retry and fallback)
# =============================
def group_conditions_with_ai(conditions, mapping, retry_count=3):
    if not conditions:
        logger.info("No conditions provided for grouping.")
        return mapping, []
    
    prompt = f"""
You are a medical coding assistant. I have the following list of ICD-9 codes with their descriptions:
{json.dumps(conditions, ensure_ascii=False, indent=2)}

Please group these codes into clusters where each cluster contains codes that represent the same clinical condition.
Return a JSON object in the following format:
{{
  "clusters": [
    {{
      "representative": "<a representative description or code from the cluster>",
      "codes": ["<ICD-9 code 1>", "<ICD-9 code 2>", ...]
    }},
    ...
  ]
}}

Only include clusters that have at least two codes. Do not include unique codes.
"""
    logger.info("Sending grouping prompt to ChatGPT for conditions...")
    clusters = []
    for attempt in range(retry_count):
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a medical coding assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=600,
            )
            reply = response["choices"][0]["message"]["content"].strip()
            logger.info(f"ChatGPT grouping response (attempt {attempt+1}): {reply}")
            reply = clean_json_response(reply)
            reply = extract_json_from_response(reply)
            result = json.loads(reply)
            clusters = result.get("clusters", [])
            if clusters:
                logger.info("Valid clusters obtained from ChatGPT.")
                break
        except Exception as e:
            logger.error("Attempt %d: Error processing grouping response: %s", attempt+1, e)
        time.sleep(2)
    
    if not clusters:
        logger.info("No clusters returned by AI after retries; applying fallback grouping (each condition becomes its own group).")
        for cond in conditions:
            key = cond["description"]
            mapping[key] = [cond["icd9_code"]]
        return mapping, []
    
    grouped_codes = set()
    for cluster in clusters:
        rep = cluster.get("representative")
        codes_in_cluster = cluster.get("codes", [])
        if rep and codes_in_cluster:
            mapping[rep] = codes_in_cluster
            grouped_codes.add(rep)
            grouped_codes.update(codes_in_cluster)
    
    remaining = [cond for cond in conditions if cond["icd9_code"] not in grouped_codes]
    logger.info(f"Grouped {len(conditions) - len(remaining)} codes in this batch; {len(remaining)} remain ungrouped.")
    return mapping, remaining

def recursive_grouping():
    conditions = fetch_conditions_from_bigquery()
    mapping = {}
    logger.info("Starting recursive grouping of mimic conditions...")
    for i in range(0, len(conditions), BATCH_SIZE):
        batch = conditions[i:i+BATCH_SIZE]
        logger.info(f"Processing batch {i // BATCH_SIZE + 1} with {len(batch)} conditions.")
        mapping, _ = group_conditions_with_ai(batch, mapping)
        try:
            with open(MIMIC_MAPPING_FILE, "w", encoding="utf-8") as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved mimic mapping to {MIMIC_MAPPING_FILE} after batch {i // BATCH_SIZE + 1}.")
            if os.path.exists(MIMIC_MAPPING_FILE):
                file_stats = os.stat(MIMIC_MAPPING_FILE)
                logger.info(f"{MIMIC_MAPPING_FILE} created: size={file_stats.st_size} bytes, modified={time.ctime(file_stats.st_mtime)}")
            else:
                logger.error(f"{MIMIC_MAPPING_FILE} was not created!")
        except Exception as e:
            logger.error("Error writing mimic mapping file: %s", e)
        try:
            process_all_text2dt_records(mapping)
            logger.info(f"Updated {OUTPUT_MAPPING_FILE} with current mimic mapping after batch {i // BATCH_SIZE + 1}.")
            if os.path.exists(OUTPUT_MAPPING_FILE):
                file_stats = os.stat(OUTPUT_MAPPING_FILE)
                logger.info(f"{OUTPUT_MAPPING_FILE} updated: size={file_stats.st_size} bytes, modified={time.ctime(file_stats.st_mtime)}")
            else:
                logger.error(f"{OUTPUT_MAPPING_FILE} was not created!")
        except Exception as e:
            logger.error("Error updating Text2DT mapping file: %s", e)
        time.sleep(2)
    logger.info("Completed grouping of mimic conditions.")
    return mapping

# =============================
# 3. Additional AI matching for Text2DT records
# =============================
def get_matching_group(condition, mapping):
    mapping_keys = list(mapping.keys())
    if not mapping_keys:
        logger.error("Mapping is empty. Cannot match condition.")
        return "No Groups"
    mapping_keys_str = ", ".join(mapping_keys)
    prompt = f"""
You are a medical coding assistant.
I have the following groups: {mapping_keys_str}
I have a Text2DT condition: "{condition}".
Based on the above groups, please choose the one that best matches this condition.
Your answer must be exactly one of the groups listed above. If none appear to match well, please choose the closest match.
Which group best matches this condition?
"""
    logger.info(f"Sending matching prompt to ChatGPT for condition: {condition}")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a medical coding assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=60,
        )
        answer = response["choices"][0]["message"]["content"].strip()
        logger.info(f"ChatGPT matching response for condition '{condition}': {answer}")
    except Exception as e:
        logger.error(f"Error calling OpenAI API for mapping condition '{condition}': {e}")
        answer = ""
    
    if answer not in mapping_keys or answer.lower() == "unknown":
        fallback_matches = get_close_matches(condition, mapping_keys, n=1, cutoff=0.7)
        if fallback_matches:
            answer = fallback_matches[0]
            logger.info(f"Fuzzy matching fallback: condition '{condition}' matched to group '{answer}'.")
        else:
            answer = mapping_keys[0]
            logger.info(f"No close matches found; defaulting condition '{condition}' to group '{answer}'.")
    time.sleep(2)
    return answer

# =============================
# 4. Process Text2DT Records to Map Conditions
# =============================
def load_text2dt_data():
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

def process_text2dt_record(record, mapping):
    text = record.get("text", "")
    logger.info(f"Processing Text2DT record with text (first 30 chars): {text[:30]}...")
    condition_name = text.split("@")[0].strip() if "@" in text else text.strip()
    logger.info(f"Extracted condition name: {condition_name}")
    
    # First try direct substring matching
    assigned_group = None
    for rep, codes in mapping.items():
        if rep.lower() in condition_name.lower():
            assigned_group = rep
            logger.info(f"Condition '{condition_name}' matched by substring with group '{rep}'.")
            break
        for code in codes:
            if code.lower() in condition_name.lower():
                assigned_group = rep
                logger.info(f"Condition '{condition_name}' matched by code substring with group '{rep}'.")
                break
        if assigned_group:
            break

    # If still no match, translate the Chinese condition to English and then compute similarity
    if not assigned_group:
        english_condition = translate_to_english(condition_name)
        logger.info(f"Translated condition '{condition_name}' to English: '{english_condition}'")
        best_match = None
        best_ratio = 0.0
        for group in mapping.keys():
            ratio = similarity(english_condition.lower(), group.lower())
            logger.info(f"Similarity between '{english_condition}' and '{group}': {ratio}")
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = group
        if best_ratio >= SIMILARITY_THRESHOLD:
            assigned_group = best_match
            logger.info(f"Best fuzzy match based on English translation: '{assigned_group}' with ratio {best_ratio}")
        else:
            logger.info(f"No fuzzy match above threshold for condition '{condition_name}' (best ratio {best_ratio}); using AI matching.")
            assigned_group = get_matching_group(condition_name, mapping)
    
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
    
    mimic_details = {
        "representative": assigned_group,
        "icd9_codes": mapping.get(assigned_group, [])
    }
    logger.info(f"Assigned mimic group for condition '{condition_name}': {mimic_details}")
    
    return {
        "text2dt_condition": condition_name,
        "mapped_mimic_group": mimic_details,
        "profile": profile
    }

def process_all_text2dt_records(mapping):
    logger.info("Starting to process all Text2DT records...")
    records = load_text2dt_data()
    if not records:
        logger.error("No Text2DT records to process. Exiting Text2DT mapping stage.")
        return []
    logger.info("Processing individual Text2DT records...")
    processed = []
    for idx, rec in enumerate(records):
        try:
            mapped_record = process_text2dt_record(rec, mapping)
            processed.append(mapped_record)
        except Exception as e:
            logger.error(f"Error processing a Text2DT record: {e}")
        
        # Update the output file every 10 records
        if (idx + 1) % 10 == 0:
            try:
                with open(OUTPUT_MAPPING_FILE, "w", encoding="utf-8") as f:
                    json.dump(processed, f, ensure_ascii=False, indent=2)
                logger.info(f"Updated {OUTPUT_MAPPING_FILE} after processing {idx+1} records.")
                if os.path.exists(OUTPUT_MAPPING_FILE):
                    file_stats = os.stat(OUTPUT_MAPPING_FILE)
                    logger.info(f"{OUTPUT_MAPPING_FILE} updated: size={file_stats.st_size} bytes, modified={time.ctime(file_stats.st_mtime)}")
                else:
                    logger.error(f"{OUTPUT_MAPPING_FILE} was not created!")
            except Exception as e:
                logger.error(f"Error updating Text2DT mapping file: {e}")
            time.sleep(1)
    
    # Final write after processing all records
    try:
        with open(OUTPUT_MAPPING_FILE, "w", encoding="utf-8") as f:
            json.dump(processed, f, ensure_ascii=False, indent=2)
        logger.info(f"Final update: Processed {len(processed)} Text2DT records; output saved to {OUTPUT_MAPPING_FILE}.")
        if os.path.exists(OUTPUT_MAPPING_FILE):
            file_stats = os.stat(OUTPUT_MAPPING_FILE)
            logger.info(f"{OUTPUT_MAPPING_FILE} created: size={file_stats.st_size} bytes, modified={time.ctime(file_stats.st_mtime)}")
        else:
            logger.error(f"{OUTPUT_MAPPING_FILE} was not created!")
    except Exception as e:
        logger.error(f"Error writing final Text2DT mapping file: {e}")
    
    return processed

# =============================
# 5. Main Script
# =============================
def main():
    logger.info("Script started.")
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not set in environment.")
        return
    
    mapping = recursive_grouping()
    logger.info(f"Final mimic mapping: {json.dumps(mapping, ensure_ascii=False, indent=2)}")
    
    processed_text2dt = process_all_text2dt_records(mapping)
    if processed_text2dt:
        logger.info("Final processed Text2DT mapping:")
        logger.info(json.dumps(processed_text2dt, ensure_ascii=False, indent=2))
    else:
        logger.error("No Text2DT mapping was produced.")
    
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
