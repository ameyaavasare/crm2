import os
import json
import openai
import logging
from dotenv import load_dotenv
from supabase_client import supabase, insert_interaction

# Load environment variables
load_dotenv()

# Always refer to https://platform.openai.com/docs/api-reference
# and use gpt-4o-2024-08-06
openai.api_key = os.getenv("OPENAI_API_KEY")
MODEL_NAME = "gpt-4o-2024-08-06"

logger = logging.getLogger(__name__)

def parse_interaction_name(message: str) -> str:
    """
    Use GPT to extract a contact name from text like:
      "Had a call with Stamford Raffles about..."
    Return that name or "" if none found.
    """
    system_prompt = (
        "You are a data extraction assistant. The user is describing an interaction. "
        "Extract ONLY the person's full name in a JSON object, like {\"name\": \"John Smith\"}.\n"
        "If you cannot find a name, output {\"name\": \"\"}.\n"
    )
    user_prompt = f"Message: {message}\nReturn JSON only."

    try:
        response = openai.ChatCompletion.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            response_format={ "type": "json_object" }  # Force JSON response
        )
        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)
        return data.get("name", "")
    except Exception as e:
        logger.error(f"Error parsing name with GPT: {e}")
        return ""

def fuzzy_search_contacts(name: str):
    """
    Fuzzy search by name in 'contacts' table. Returns list of matching records.
    """
    try:
        res = supabase.table("contacts").select("*").ilike("name", f"%{name}%").execute()
        return res.data if res.data else []
    except Exception as e:
        logger.error(f"Error searching contacts by fuzzy name: {e}")
        return []

def handle_interaction_message(message: str) -> str:
    """
    1) Extract contact name from the user's text
    2) Fuzzy search contacts
    3) If exactly one match, insert into 'interactions'
    4) Return a short response
    """
    extracted_name = parse_interaction_name(message)
    if not extracted_name:
        return (
            "Sorry, I couldn't detect a name. Try something like 'Had a call with Jane Doe...'"
        )

    matches = fuzzy_search_contacts(extracted_name)
    if len(matches) == 1:
        contact = matches[0]
        data = {
            "contact_id": contact["uuid"],
            "note": message
        }
        result = insert_interaction(data)
        if "error" in result:
            return f"Error saving interaction: {result['error']}"
        return f"Interaction saved under {contact['name']}!"

    elif len(matches) > 1:
        names = [m["name"] for m in matches]
        return (
            "Found multiple contacts: " + ", ".join(names) +
            ". Please be more specific (e.g. full name or email)."
        )

    else:
        return (
            "No matching contact found. Please create the contact first "
            "or try a more accurate name."
        )
