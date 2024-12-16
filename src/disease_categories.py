# disease_categories.py
import sys


def categorize_diseases(conditions):
    """
    Categorize diseases into specific categories based on predefined groupings.
    """
    categories = {
        "respiratory": [],
        "cardiovascular": [],
        "neurological": [],
        "gastrointestinal": [],
        "musculoskeletal": [],
        "infectious": [],
        "other": []
    }

    # Map diseases to categories
    for disease_id, disease_data in conditions.items():
        disease_name = disease_data["cond-name-eng"].lower()

        # Categorize based on keywords in disease name (adjust as needed)
        if "lung" in disease_name or "respiratory" in disease_name or "sinus" in disease_name:
            categories["respiratory"].append(disease_id)
        elif "heart" in disease_name or "vascular" in disease_name:
            categories["cardiovascular"].append(disease_id)
        elif "brain" in disease_name or "neuro" in disease_name:
            categories["neurological"].append(disease_id)
        elif "stomach" in disease_name or "intestinal" in disease_name:
            categories["gastrointestinal"].append(disease_id)
        elif "muscle" in disease_name or "bone" in disease_name:
            categories["musculoskeletal"].append(disease_id)
        elif "infection" in disease_name or "viral" in disease_name:
            categories["infectious"].append(disease_id)
        else:
            categories["other"].append(disease_id)

    return categories
