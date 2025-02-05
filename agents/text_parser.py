import os
import sys
import json
import re
import logging
from datetime import datetime
from dateutil import parser as date_parser
from dotenv import load_dotenv
import openai

# We only need supabase_client if we were to insert directly, 
# but your code uses insert_contact in main flow.
# from supabase_client import insert_contact

load_dotenv()

# Always use gpt-4o-2024-08-06
openai.api_key = os.getenv("OPENAI_API_KEY")
MODEL_NAME = "gpt-4o-2024-08-06"
MAX_TOKENS = 150
TEMPERATURE = 0.0

logger = logging.getLogger(__name__)

def format_phone_number(phone: str) -> str:
    """
    Convert phone to E.164 format if possible.
    """
    if not phone:
        return None
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    elif len(digits) > 11:
        return f"+{digits}"
    return None

def parse_contact_message(message: str) -> dict:
    """
    GPT extraction: name, phone, email, birthday, family_members, description.
    Return that as a dict or empty on failure.
    """
    prompt = (
        "You are a data extraction assistant. The user wants to create or update a contact. "
        "Extract these fields in JSON:\n"
        "- name\n"
        "- phone\n"
        "- email\n"
        "- birthday (YYYY-MM-DD)\n"
        "- family_members (comma-separated)\n"
        "- description\n"
        "If not found, put null.\n"
        f"Message: '{message}'\n"
        "Output JSON only with these keys."
    )
    try:
        resp = openai.ChatCompletion.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a helpful assistant for data extraction."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )
        raw = resp.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Error parsing contact: {e}")
        return {}

def prepare_contact_for_supabase(message: str) -> dict:
    """
    Convert GPT extraction to a final dict for supabase with correct formats.
    """
    parsed = parse_contact_message(message)
    if not parsed:
        return {}

    # Format phone
    if parsed.get("phone"):
        parsed["phone"] = format_phone_number(parsed["phone"])

    # Normalize birthday
    if parsed.get("birthday"):
        try:
            dt = date_parser.parse(parsed["birthday"])
            parsed["birthday"] = dt.strftime("%Y-%m-%d")
        except Exception as e:
            logger.error(f"Error formatting birthday: {e}")
            parsed["birthday"] = None

    # Guarantee all fields exist
    for field in ["name", "phone", "email", "birthday", "family_members", "description"]:
        if field not in parsed:
            parsed[field] = None

    return parsed

def parse_message(message: str, existing_data: dict = None) -> dict:
    """
    Part of your existing contact creation flow:
    - If there's existing data, we skip re-asking missing fields; 
      we just update and confirm.
    - If no existing data, we check what's missing, prompt user, or confirm if all found.
    """
    contact_record = existing_data.copy() if existing_data else {}
    new_data = prepare_contact_for_supabase(message)

    # Only fill in newly provided fields
    for k, v in new_data.items():
        if v and not contact_record.get(k):
            contact_record[k] = v

    required_fields = {
        'name': 'Full name',
        'phone': 'Phone number',
        'email': 'Email address',
        'birthday': 'Birthday (YYYY-MM-DD)',
        'family_members': 'Family members',
        'description': 'Description',
    }

    # If we already had data, we just confirm
    if existing_data:
        return {
            "message": (
                f"Please confirm the contact:\n{json.dumps(contact_record, indent=2)}\n"
                "Reply 'yes' or 'y' to confirm, 'no' to cancel."
            ),
            "status": "needs_confirmation",
            "contact_data": contact_record
        }

    # If new entry, see if anything is missing
    missing = [label for f, label in required_fields.items() if not contact_record.get(f)]
    if missing:
        return {
            "message": (
                "Missing: " + ", ".join(missing) + 
                "\nPlease provide them."
            ),
            "status": "missing_fields",
            "contact_data": contact_record
        }

    # If everything is found, confirm
    return {
        "message": (
            f"Please confirm the contact:\n{json.dumps(contact_record, indent=2)}\n"
            "Reply 'yes' or 'y' to confirm, or 'no' to cancel."
        ),
        "status": "needs_confirmation",
        "contact_data": contact_record
    }
