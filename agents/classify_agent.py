import os
import openai
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def classify_message(message_body: str) -> str:
    """
    Uses GPT to classify the incoming SMS into one of:
      'contacts_change', 'query_contacts', 'interaction', 'interaction_query', or 'unknown'.

    Model: gpt-4o-2024-08-06
    Reference: https://platform.openai.com/docs/api-reference
    """
    system_prompt = (
        "You are a classification agent for a personal CRM. "
        "The user will send a message about contacts or interactions. "
        "You must respond ONLY with exactly one category (no extra text). "
        "Valid categories: contacts_change, query_contacts, interaction, interaction_query, unknown."
    )

    user_message = message_body.strip()

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=5,
            temperature=0
        )
        classification = response.choices[0].message.content.strip().lower()

        valid = {
            "contacts_change",
            "query_contacts",
            "interaction",
            "interaction_query",
        }
        return classification if classification in valid else "unknown"

    except Exception:
        return "unknown"
