import os
import json
import openai
import logging

from dotenv import load_dotenv

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

logger = logging.getLogger(__name__)

CHECK_MODEL = "gpt-4o-mini"  # second "agent" for verifying classification

def verify_classification(message: str, initial_label: str) -> bool:
    """
    Checks if the initial classification is correct.
    
    message: The user's original SMS text
    initial_label: "contact" or "interaction"

    Returns True if correct, False otherwise.
    """
    system_prompt = (
        "You are a classification verification assistant.\n"
        "The user wrote some text. Another assistant classified it as either:\n"
        "   1) 'contact' -> means user wants to add or update a contact\n"
        "   2) 'interaction' -> means user is describing an interaction they had with a contact\n\n"
        "You must decide if that classification is correct.\n"
        "If it is correct, return JSON: { 'correct_classification': true }\n"
        "If not correct, return JSON: { 'correct_classification': false }\n"
    )

    # Provide a short explanation in the user content so GPT knows the current guess
    user_prompt = (
        f"Message:\n{message}\n\n"
        f"Initial Classification: '{initial_label}'\n\n"
        "Possible categories:\n"
        "- 'contact': user providing details to create/update a contact record\n"
        "- 'interaction': user describing an interaction with an existing contact\n"
        "Is this correct?"
        "\nReturn JSON only with the key 'correct_classification'."
    )

    try:
        response = openai.ChatCompletion.create(
            model=CHECK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=30
        )
        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)
        return data.get("correct_classification", False)
    except Exception as e:
        logger.error(f"Error verifying classification: {e}")
        # On error, assume the classification might be correct
        return True
