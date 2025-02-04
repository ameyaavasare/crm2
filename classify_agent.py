import os
import openai
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def classify_message(message_body: str) -> str:
    """
    Uses GPT to classify the incoming SMS.
    Possible outputs: 'contacts_change', 'query_contacts', 
                      'interaction', 'interaction_query', or 'unknown'.
    This is a placeholder for demonstration.
    """
    # For brevity, we'll do a simple mock classification:
    # In production, you'd use openai.ChatCompletion.create with a prompt or system message
    lower_body = message_body.lower()
    if "add contact" in lower_body or "update contact" in lower_body or "delete contact" in lower_body:
        return "contacts_change"
    elif "contact info" in lower_body or "find contact" in lower_body:
        return "query_contacts"
    elif "new interaction" in lower_body or "log this interaction" in lower_body:
        return "interaction"
    elif "interaction query" in lower_body or "find interactions" in lower_body:
        return "interaction_query"
    else:
        return "unknown"
