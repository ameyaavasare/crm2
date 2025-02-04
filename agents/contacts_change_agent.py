import os
import openai
from dotenv import load_dotenv
# Changed to absolute import
from supabase_client import supabase

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def handle_contacts_change(message: str) -> str:
    """
    Add, update, or delete a contact in a more conversational manner.
    We'll parse the user message with GPT to extract fields:
      name, phone, email, birthday, location, family members, etc.
    If insufficient data is provided, we can ask the user to clarify.
    """

    # Step 1: Use GPT to parse user’s freeform text
    contact_data = parse_contact_info(message)

    # Check if GPT found any intended action (add/update/delete)
    action = contact_data.get("action", "").lower()
    if action not in ["add", "update", "delete"]:
        return (
            "I’m not sure if you want to add, update, or delete a contact. "
            "Please specify 'add', 'update', or 'delete' in your message."
        )

    if action == "delete":
        # For demonstration: we only do a naive delete by name
        name = contact_data.get("name")
        if not name:
            return "I didn’t find a contact name to delete. Please specify."
        supabase.table("contacts").delete().eq("name", name).execute()
        return f"Contact '{name}' deleted successfully."

    # For 'add' or 'update', we gather fields
    contact_record = {}
    for field in ["name", "phone", "email", "birthday", "family_members", "description"]:
        if contact_data.get(field):
            contact_record[field] = contact_data[field]

    if action == "add":
        if not contact_record.get("name"):
            return "Couldn’t find a name. Please mention the contact’s name to add."
        supabase.table("contacts").insert(contact_record).execute()
        return f"Contact '{contact_record['name']}' added successfully."

    elif action == "update":
        name = contact_data.get("name")
        if not name:
            return "Couldn’t find a contact name to update. Please include one."
        # Example: find contact by name, then update fields
        supabase.table("contacts").update(contact_record).eq("name", name).execute()
        return f"Contact '{name}' updated successfully."

    return "No valid action specified."

def parse_contact_info(user_text: str) -> dict:
    """
    Calls GPT to parse contact info from a conversational user message.
    Expects a JSON-like response with fields:
       action -> str ("add"/"update"/"delete")
       name -> str
       phone -> str
       email -> str
       birthday -> str
       family_members -> str
       description -> str
       location -> str (not stored yet, but you can expand)
    """
    system_prompt = (
        "You are a specialized parser for contact changes in a personal CRM. "
        "User messages may say something like: 'Hey, can you add Stamford Raffles? "
        "He is from Singapore, phone +!9995551234, email stamford@raffles.com, birthday 18 March 1900, 2 kids, etc.' "
        "Extract the meaning into JSON with keys: action, name, phone, email, birthday, family_members, description. "
        "Allowed actions: add, update, delete. If you’re unsure, action='add'. "
        "If missing some fields, just leave them blank. "
        "Output MUST be valid JSON, with the keys: action, name, phone, email, birthday, family_members, description."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            temperature=0,
            max_tokens=300,
        )
        raw_content = response.choices[0].message.content.strip()

        import json
        parsed = json.loads(raw_content)
        return {
            "action": parsed.get("action", ""),
            "name": parsed.get("name", ""),
            "phone": parsed.get("phone", ""),
            "email": parsed.get("email", ""),
            "birthday": parsed.get("birthday", ""),
            "family_members": parsed.get("family_members", ""),
            "description": parsed.get("description", ""),
        }
    except Exception:
        # If anything fails, return a blank dict
        return {}
