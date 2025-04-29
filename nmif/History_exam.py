import openai
import time
from AIHistory import (
    fetch_patient_data,
    generate_patient_history_with_gpt,
    connect_to_db,
    calculate_age
)
import openai

# Timer and rating mechanism
def rate_performance(start_time, end_time):
    """
    Calculate and display the time taken by the user for each question.
    """
    time_taken = round(end_time - start_time, 2)
    print(f"\nTime taken: {time_taken} seconds")
    return time_taken


def run_cli():
    """
    CLI interface for generating histories and asking questions.
    """
    # Database connection
    DB_CONFIG = {
        "dbname": "mimiciii",
        "user": "postgres",
        "password": "123",
        "host": "localhost",
        "port": 5432,
    }

    connection = connect_to_db(DB_CONFIG)
    if not connection:
        print("Failed to connect to the database. Exiting.")
        return

    try:
        print("\nWelcome to the Medical History CLI!\n")
        while True:
            # Fetch patient data
            patient, diagnoses, events, notes, lab_tests, prescriptions = fetch_patient_data(connection)
            if not patient:
                print("No patient data available. Exiting.")
                break

            # Generate and display patient history
            print("\nGenerating patient history...")
            history = generate_patient_history_with_gpt(patient, diagnoses, events, notes, lab_tests, prescriptions)
            if not history:
                print("Failed to generate patient history. Exiting.")
                break
            print("\n--- Generated Patient History ---\n")
            print(history)
            print("\n--- End of History ---\n")

            # Start interactive question session
            print("\nYou can now ask questions about the patient history. Type 'exit' to quit the session.")
            while True:
                user_input = input("\nYour question: ").strip()
                if user_input.lower() == "exit":
                    print("Exiting question session.")
                    break

                # Send user question to ChatGPT
                prompt = f"""
                Based on the following patient history, answer the user's question:

                Patient History:
                {history}

                Question:
                {user_input}
                """
                start_time = time.time()
                try:
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",  # Use "gpt-4" if available
                        messages=[
                            {"role": "system", "content": "You are a medical assistant answering questions about patient cases."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=600,
                        temperature=0.7
                    )
                    answer = response["choices"][0]["message"]["content"].strip()
                except Exception as e:
                    print(f"Error using ChatGPT: {e}")
                    continue
                end_time = time.time()

                # Display ChatGPT's response and calculate time taken
                print("\n--- ChatGPT's Response ---")
                print(answer)
                print("\n--- End of Response ---")
                rate_performance(start_time, end_time)

            # Option to process another patient
            continue_prompt = input("\nDo you want to generate another patient history? (yes/no): ").strip().lower()
            if continue_prompt != "yes":
                print("Goodbye!")
                break
    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    run_cli()
