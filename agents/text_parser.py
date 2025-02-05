import os
import sys
import json
import uuid
import re
from datetime import datetime

import openai
from dotenv import load_dotenv

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
    Parse the message for contact details, add a UUID,
    and format the phone number and birthday appropriately.
    """
    contact = parse_contact_message(message)
    if not contact:
        return {}

    # Add a unique identifier
    contact["uuid"] = str(uuid.uuid4())

    # Format phone number if present
    if contact.get("phone"):
        contact["phone"] = format_phone_number(contact["phone"])

    # Validate and reformat birthday if present
    birthday = contact.get("birthday")
    if birthday:
        try:
            dt = datetime.strptime(birthday, "%Y-%m-%d")
            contact["birthday"] = dt.date().isoformat()
        except ValueError:
            contact["birthday"] = None

    return contact


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
