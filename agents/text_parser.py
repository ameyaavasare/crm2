import os
import sys
import json
import uuid
import re
from datetime import datetime

import openai
from dotenv import load_dotenv
import logging
from dateutil import parser as date_parser

# Add the project root directory to Python path (if needed)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from supabase_client import insert_contact

# Load environment variables and set OpenAI API key
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Constants for OpenAI API calls
MODEL_NAME = "gpt-4o-mini"
MAX_TOKENS = 150
TEMPERATURE = 0.0

logger = logging.getLogger(__name__)


def format_phone_number(phone: str) -> str:
    """
    Format a phone number string into E.164 format (+19995551234).
    Assumes US numbers if no country code is provided.
    """
    if not phone:
        return None

    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:  # US number without country code
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):  # US with country code
        return f"+{digits}"
    elif len(digits) > 11:  # International number
        return f"+{digits}"
    return None


def parse_contact_message(message: str) -> dict:
    """
    Use GPT to extract structured contact data from a conversational message.
    Expected fields: name, phone, email, birthday, family_members, description.
    """
    prompt = (
        "You are a data extraction assistant. Your task is to read a conversational message "
        "and extract contact details. Extract the following fields:\n"
        "- name: The full name of the contact.\n"
        "- phone: The phone number.\n"
        "- email: The email address (if present, otherwise null).\n"
        "- birthday: The birthday in YYYY-MM-DD format (if mentioned, otherwise null).\n"
        "- family_members: Any mentioned family member names as a comma-separated string (if none, null).\n"
        "- description: A short description summarizing extra details about the contact.\n\n"
        "Given the input message below, output only a JSON object with these keys. Do not include any extra text.\n\n"
        f"Input message: \"{message}\""
    )

    try:
        response = openai.ChatCompletion.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a helpful assistant for data extraction."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )
    except Exception as e:
        print("API call failed:", e)
        return {}

    parsed_text = response.choices[0].message.content.strip()
    try:
        return json.loads(parsed_text)
    except json.JSONDecodeError:
        print("Failed to parse JSON. Raw response:", parsed_text)
        return {}


def prepare_contact_for_supabase(message: str) -> dict:
    """
    Extract contact information from the message.
    
    This function leverages GPT (via parse_contact_message) to extract structured details,
    then normalizes the data for insertion into Supabase. The expected fields are:
      - name: The full name of the contact.
      - phone: The phone number, which will be formatted in E.164 style.
      - email: The email address, or None if not provided.
      - birthday: The birthday date (normalized to YYYY-MM-DD), or None.
      - family_members: A comma-separated string of family member names, or None.
      - description: A short description with extra details.
    """
    logger.info("Preparing contact info for Supabase.")
    
    parsed_data = parse_contact_message(message)
    logger.info(f"Parsed data from GPT: {parsed_data}")
    
    if parsed_data:
        # Format the phone number using our helper
        if parsed_data.get("phone"):
            parsed_data["phone"] = format_phone_number(parsed_data["phone"])
        
        # Attempt to normalize the birthday to YYYY-MM-DD format if provided
        if parsed_data.get("birthday"):
            try:
                dt = date_parser.parse(parsed_data["birthday"])
                parsed_data["birthday"] = dt.strftime("%Y-%m-%d")
            except Exception as e:
                logger.error(f"Error formatting birthday '{parsed_data.get('birthday')}': {e}")
        
        # Ensure that all required fields exist. If any are not present, set them to None.
        for field in ['name', 'phone', 'email', 'birthday', 'family_members', 'description']:
            if field not in parsed_data:
                parsed_data[field] = None

        return parsed_data
    
    # If parsing fails return an empty dict
    return {}


def parse_message(message: str, existing_data: dict = None) -> dict:
    """
    Process the incoming text message for contact details.
    Returns a dict with either:
      - A prompt for missing information (for the initial turn), or
      - A confirmation request if this is a follow-up turn.
    
    This version ensures that:
      1) Once a request for additional info has been sent, only one turn is allowed –
         any follow-up info is merged without re-prompting for missing fields.
      2) Fields already provided are not overwritten by subsequent messages.
    """
    # Start with existing data if provided
    contact_record = existing_data.copy() if existing_data else {}

    # Update contact_record with new information from the message,
    # but do not overwrite fields that already have a value.
    new_data = prepare_contact_for_supabase(message)
    if new_data:
        for key, value in new_data.items():
            if value and not contact_record.get(key):
                contact_record[key] = value

    required_fields = {
        'name': 'Full name',
        'phone': 'Phone number',
        'email': 'Email address',
        'birthday': 'Birthday (YYYY-MM-DD)',
        'family_members': 'Family members',
        'description': 'Description',
    }

    # If we're processing a follow-up turn (existing_data was provided),
    # then do not ask again for missing fields; simply ask for confirmation.
    if existing_data:
        return {
            "message": (
                f"Please confirm the contact information:\n{json.dumps(contact_record, indent=2)}\n"
                "Reply 'yes' or 'y' to confirm."
            ),
            "status": "needs_confirmation",
            "contact_data": contact_record
        }

    # Otherwise (first turn) prompt for any missing fields.
    missing = {field: label for field, label in required_fields.items() if not contact_record.get(field)}
    if missing:
        return {
            "message": (
                "Missing information for: " + ", ".join(missing.values()) +
                ". Please provide these details."
            ),
            "status": "missing_fields",
            "contact_data": contact_record
        }

    # If no fields are missing initially, ask for confirmation right away.
    return {
        "message": (
            f"Please confirm the contact information:\n{json.dumps(contact_record, indent=2)}\n"
            "Reply 'yes' or 'y' to confirm."
        ),
        "status": "needs_confirmation",
        "contact_data": contact_record
    }


def prompt_for_missing_fields(contact: dict, required_fields: dict) -> dict:
    """
    Check for missing fields in the contact record and prompt the user to input them.
    Only updates fields that are missing.
    """
    missing = {field: label for field, label in required_fields.items() if not contact.get(field)}
    if not missing:
        return contact

    print("\nMissing fields:")
    for label in missing.values():
        print(f" - {label}")

    completion_message = input("\nPlease provide the missing information in a message: ").strip()
    if completion_message:
        completion_data = parse_contact_message(completion_message)
        for field in missing:
            if completion_data.get(field):
                contact[field] = completion_data[field]
    return contact


def main():
    """CLI interface to parse and insert contact information."""
    message = input("Enter contact information: ").strip()
    if not message:
        print("No input provided.")
        return

    contact_record = prepare_contact_for_supabase(message)
    if not contact_record:
        print("Failed to parse contact information.")
        return

    required_fields = {
        'name': 'Full name',
        'phone': 'Phone number',
        'email': 'Email address',
        'birthday': 'Birthday (YYYY-MM-DD)',
        'family_members': 'Family members',
        'description': 'Description',
    }

    contact_record = prompt_for_missing_fields(contact_record, required_fields)

    print("\nPlease confirm the contact information:")
    print(json.dumps(contact_record, indent=2))
    confirmation = input("\nConfirm adding this contact? (yes/no): ").strip().lower()
    if confirmation not in ['yes', 'y']:
        print("Contact not added.")
        return

    now_iso = datetime.now().isoformat()
    contact_record.update({'created_at': now_iso, 'updated_at': now_iso})

    inserted_contact = insert_contact(contact_record)
    if inserted_contact:
        print("\nContact successfully added:")
        print(json.dumps(inserted_contact, indent=2))
    else:
        print("Error: Failed to add contact to database.")


if __name__ == "__main__":
    main()
