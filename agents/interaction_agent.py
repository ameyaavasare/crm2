import os
import openai
import json
from dotenv import load_dotenv
from ..supabase_client import supabase

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def handle_interaction(message: str) -> str:
    """
    Create a new interaction record in the 'interactions' table, in a more conversational way.
    1. Parse the user message with GPT to find contact name and note.
    2. Look up the contact by name; if not found, optionally create or ask user for clarification.
    3. Insert a new row in 'interactions' with contact_id and note.
    """

    # Step 1: parse user message
    interaction_data = parse_interaction_info(message)

    contact_name = interaction_data.get("contact_name")
    note = interaction_data.get("note")

    if not contact_name:
        return "I couldn't find a contact name in your message. Please mention who you spoke with."

    # Step 2: find contact in supabase
    result = supabase.table("contacts").select("uuid,name").eq("name", contact_name).execute()
    rows = result.data

    if not rows:
        # For demo, we create a new contact automatically if not found
        insert_res = supabase.table("contacts").insert({"name": contact_name}).execute()
        new_contact_id = insert_res.data[0]["uuid"]
    else:
        new_contact_id = rows[0]["uuid"]

    if not note:
        return "I couldn't find any notes to record for this interaction."

    # Step 3: create the interaction row
    supabase.table("interactions").insert({
        "contact_id": new_contact_id,
        "note": note
    }).execute()

    return f"Interaction recorded for {contact_name}."

def parse_interaction_info(user_text: str) -> dict:
    """
    Uses GPT to find the contact name and note in a conversation.
    Returns { 'contact_name': str, 'note': str }.
    If either is missing, returns blank.
    """
    system_prompt = (
        "You are a specialized parser for logging interactions in a personal CRM. "
        "User messages might say: 'Spoke with Stamford Raffles about his trip to ski in Paris...' "
        "Output MUST be JSON with keys 'contact_name' and 'note'. "
        "If you can't find a name or note, leave them blank. "
        "Example: {'contact_name': 'Stamford Raffles', 'note': 'He got hurt skiing...'}"
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
        parsed = json.loads(raw_content)
        return {
            "contact_name": parsed.get("contact_name", "").strip(),
            "note": parsed.get("note", "").strip(),
        }
    except Exception:
        return {}
