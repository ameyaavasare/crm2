import os
import sys
import json
import re
import logging
from datetime import datetime
from dateutil import parser as date_parser
from dotenv import load_dotenv
from openai import OpenAI

# We only need supabase_client if we were to insert directly, 
# but your code uses insert_contact in main flow.
# from supabase_client import insert_contact

load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL_NAME = "gpt-4o-2024-08-06"
MAX_TOKENS = 150
TEMPERATURE = 0.0

logger = logging.getLogger(__name__)

def format_phone_number(phone: str) -> str:
    """
    Convert phone numbers to E.164 format.
    Handles international numbers with various formats:
    - US/Canada: +1XXXXXXXXXX
    - International: +[country_code][number]
    - Numbers with or without + prefix
    - Numbers with spaces, dashes, parentheses
    """
    if not phone:
        return None
        
    # Remove all non-digit characters except '+'
    cleaned = ''.join(char for char in phone if char.isdigit() or char == '+')
    
    # If number already starts with +, just remove any spaces and return
    if cleaned.startswith('+'):
        return cleaned
    
    # If number starts with 00 (international prefix), replace with +
    if cleaned.startswith('00'):
        return f"+{cleaned[2:]}"
        
    # Handle US/Canada numbers (default if 10 digits)
    if len(cleaned) == 10:
        return f"+1{cleaned}"
    
    # If it starts with a country code (no +), add the +
    # Common country codes are 1-3 digits
    if len(cleaned) > 10:
        return f"+{cleaned}"
        
    return None

def parse_contact_message(message: str) -> dict:
    """
    GPT extraction: name, phone, email, birthday, family_members, description.
    Return that as a dict or empty on failure.
    """
    prompt = (
        "Extract contact information from this message. Format the response as valid JSON with these exact keys:\n"
        "{\n"
        '  "name": "full name",\n'
        '  "phone": "phone number in E.164 format (e.g., +66625319066 for Thai numbers)",\n'
        '  "email": "email address",\n'
        '  "birthday": "YYYY-MM-DD",\n'
        '  "family_members": "comma-separated list or null",\n'
        '  "description": "brief description"\n'
        "}\n\n"
        "Rules:\n"
        "1. Use null for missing fields\n"
        "2. Format birthday as YYYY-MM-DD\n"
        "3. Include any location or status info in description\n"
        "4. For phone numbers:\n"
        "   - Remove spaces, dashes, and parentheses\n"
        "   - Keep the + prefix\n"
        "   - For Thai numbers (+66), ensure format is +66XXXXXXXXX\n"
        f"Message: {message}"
    )

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system", 
                    "content": "You are a contact information extraction assistant. Always return valid JSON. For phone numbers, always use E.164 format (e.g., +66625319066 for Thai numbers)."
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=2048,
            response_format={ "type": "json_object" }  # Force JSON response
        )
        
        raw = resp.choices[0].message.content.strip()
        parsed = json.loads(raw)
        
        # Ensure all required fields exist
        required_fields = ["name", "phone", "email", "birthday", "family_members", "description"]
        for field in required_fields:
            if field not in parsed:
                parsed[field] = None
        
        # Additional validation for phone number
        if parsed.get("phone"):
            # Ensure phone starts with +
            if not parsed["phone"].startswith("+"):
                parsed["phone"] = "+" + parsed["phone"]
                
        return parsed
        
    except Exception as e:
        logger.error(f"Error parsing contact: {e}")
        # Return a valid empty dict with all required fields
        return {
            "name": None,
            "phone": None,
            "email": None,
            "birthday": None,
            "family_members": None,
            "description": None
        }

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
