import os
import openai
import json
from dotenv import load_dotenv
from supabase_client import supabase

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def handle_contacts_change(message: str) -> str:
    """
    Add, update, or delete a contact in a conversational manner.
    We parse the user message with GPT for action, name, phone, email, birthday, etc.
    If data is missing or multiple matches occur, we can highlight that and ask the user to clarify.
    """

    # Step 1: GPT parse
    contact_data = parse_contact_info(message)
    action = contact_data.get("action", "").lower()

    if action not in ["add", "update", "delete"]:
        return ("I’m not sure if you want to add, update, or delete a contact. "
                "Please specify 'add', 'update', or 'delete' in your message.")

    # For "delete":
    if action == "delete":
        name = contact_data.get("name", "").strip()
        if not name:
            return "I didn’t see which contact to delete. Please provide their name."

        # Attempt partial match with iLike
        existing = supabase.table("contacts").select("*").ilike("name", f"%{name}%").execute().data
        if not existing:
            return f"No contacts found matching '{name}' to delete."
        if len(existing) > 1:
            # If multiple matches, we require a clearer name
            matches = [c["name"] for c in existing]
            return (f"Found multiple contacts matching '{name}': {matches}\n"
                    f"Please specify more detail or the exact name to delete.")
        # Exactly one match:
        supabase.table("contacts").delete().eq("uuid", existing[0]["uuid"]).execute()
        return f"Contact '{existing[0]['name']}' deleted successfully."

    # For 'add' or 'update'
    contact_record = {}
    for field in ["name", "phone", "email", "birthday", "family_members", "description"]:
        val = contact_data.get(field, "").strip()
        if val:
            contact_record[field] = val

    if action == "add":
        if not contact_record.get("name"):
            return "Couldn’t find a contact name to add. Please include one."
        # Insert the new contact
        supabase.table("contacts").insert(contact_record).execute()
        return f"Contact '{contact_record['name']}' added successfully."

    elif action == "update":
        name = contact_data.get("name", "").strip()
        if not name:
            return "Please specify which contact’s name to update."

        # Step A: find existing contact(s) by partial name
        existing = supabase.table("contacts").select("*").ilike("name", f"%{name}%").execute().data
        if not existing:
            return f"No contacts found matching '{name}' to update."
        if len(existing) > 1:
            # If multiple found, ask user to clarify
            matches = [c["name"] for c in existing]
            return (f"Found multiple contacts matching '{name}': {matches}\n"
                    f"Please clarify which one you want to update.")
        # Exactly one match: update that record
        supabase.table("contacts").update(contact_record).eq("uuid", existing[0]["uuid"]).execute()
        return f"Contact '{existing[0]['name']}' updated successfully."

    return "No valid action specified."

def parse_contact_info(user_text: str) -> dict:
    """
    Uses GPT to parse fields:
      action: "add"|"update"|"delete"
      name, phone, email, birthday, family_members, description
    """
    system_prompt = (
        "You are a specialized parser for contact changes in a personal CRM. "
        "Possible actions: add, update, or delete. If unsure, default to 'add'. "
        "If missing fields, just leave them blank. Output must be valid JSON with keys:"
        "  action, name, phone, email, birthday, family_members, description."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            temperature=0,
            max_tokens=300,
        )
        parsed = json.loads(response.choices[0].message.content.strip())
        return {
            "action": parsed.get("action", ""),
            "name": parsed.get("name", ""),
            "phone": parsed.get("phone", ""),
            "email": parsed.get("email", ""),
            "birthday": parsed.get("birthday", ""),
            "family_members": parsed.get("family_members", ""),
            "description": parsed.get("description", ""),
        }
    except:
        return {}
