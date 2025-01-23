import time

def calculate_similarity_with_probability(correct_symptoms, user_symptoms, symptom_disease_mapping):
    """
    Calculate the similarity score between the correct symptoms and the user's guessed symptoms,
    factoring in the probabilities for each symptom.
    """
    matching = []
    difference = set(correct_symptoms).symmetric_difference(set(user_symptoms))
    
    total_possible_score = 0  # Initialize the total score
    
    for symptom in correct_symptoms:
        # Get the probability for the symptom from symptom_disease_mapping
        correct_prob = symptom_disease_mapping.get(symptom, 0)  # Default to 0 if no probability found
        
        total_possible_score += correct_prob * 10_000_000  # Add the maximum score possible (scaled by 1 million)
        
        if symptom in user_symptoms:
            matching.append(symptom)
    
    similarity_percentage = (len(matching) / len(correct_symptoms)) * 100 if correct_symptoms else 0
    
    # Return similarity percentage, matching symptoms, and difference (for feedback)
    return similarity_percentage, matching, difference, total_possible_score

def rate_performance(start_time, end_time, correct_symptoms, user_symptoms, correct_disease, guessed_disease, symptom_disease_mapping):
    """
    Rate the user's performance based on their guess and the time taken, considering symptom probabilities.
    """
    time_taken = end_time - start_time
    similarity_percentage, matching, difference, total_possible_score = calculate_similarity_with_probability(correct_symptoms, user_symptoms, symptom_disease_mapping)
    
    # Base score calculation
    base_similarity_score = similarity_percentage  # Start with the similarity score
    time_penalty = time_taken * 2  # Deduct 2 points per second taken
    score = base_similarity_score - time_penalty
    score = max(0, score)  # Ensure the score is not negative

    # Categorize differences
    missed_symptoms = list(difference.intersection(correct_symptoms))
    extra_symptoms_guessed = list(difference.difference(correct_symptoms))

    # Feedback structure
    feedback = {
        "score": round(score, 2),
        "time_taken": round(time_taken, 2),
        "correct_disease": correct_disease,
        "guessed_disease": guessed_disease,
        "symptoms_matched": list(matching),
        "symptoms_missed": missed_symptoms,
        "extra_symptoms_guessed": extra_symptoms_guessed,
        "similarity_percentage": round(similarity_percentage, 2),
        "total_possible_score": total_possible_score  # Optionally include total possible score in feedback
    }

    return feedback

def display_feedback(feedback):
    """
    Display the feedback to the user.
    """
    print("\n--- Performance Feedback ---")
    print(f"Score: {feedback['score']}")
    print(f"Time Taken: {feedback['time_taken']} seconds")
    print(f"Correct Disease: {feedback['correct_disease']}")
    print(f"Your Guess: {feedback['guessed_disease']}")
    print(f"Similarity with Correct Symptoms: {feedback['similarity_percentage']}%")
    
    if feedback['symptoms_matched']:
        print("\nSymptoms that matched:")
        for symptom in feedback['symptoms_matched']:
            print(f"- {symptom}")
    else:
        print("\nNo symptoms matched.")

    if feedback['symptoms_missed']:
        print("\nSymptoms you missed from the correct disease:")
        for symptom in feedback['symptoms_missed']:
            print(f"- {symptom}")
    
    if feedback['extra_symptoms_guessed']:
        print("\nSymptoms you guessed that don't align with the correct disease:")
        for symptom in feedback['extra_symptoms_guessed']:
            print(f"- {symptom}")

    print("\n--- End of Feedback ---\n")
