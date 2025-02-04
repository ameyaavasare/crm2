import os
import openai
import json
from dotenv import load_dotenv
from supabase_client import supabase

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def handle_interaction(message: str) -> str:
    """
    Create a new interaction record in 'interactions'.
    1) parse user message for contact name and note,
    2) find the contact by partial name,
    3) if multiple matches -> ask user to clarify,
    4) if none -> ask user to create contact first (or auto-create),
    5) insert new row in 'interactions'.
    """

    # 1) parse with GPT
    data = parse_interaction_info(message)
    contact_name = data.get("contact_name", "").strip()
    note = data.get("note", "").strip()

    if not contact_name:
        return "I didn’t see which contact you spoke with. Please mention a name."

    if not note:
        return "I couldn’t find any notes about what happened. Please provide details."

    # 2) partial name match in supabase
    existing = supabase.table("contacts").select("*").ilike("name", f"%{contact_name}%").execute().data

    if not existing:
        # No match -> ask user or create automatically
        # We'll create automatically in this example
        new_contact = supabase.table("contacts").insert({"name": contact_name}).execute().data
        contact_id = new_contact[0]["uuid"]
    elif len(existing) > 1:
        # multiple matches -> ask user to clarify
        matches = [row["name"] for row in existing]
        return (f"Found multiple contacts matching '{contact_name}': {matches}.\n"
                "Please clarify which one you meant, or specify the full name.")
    else:
        contact_id = existing[0]["uuid"]

    # 3) insert new row in interactions
    supabase.table("interactions").insert({
        "contact_id": contact_id,
        "note": note
    }).execute()

    return f"Logged interaction for '{contact_name}': {note}"

def parse_interaction_info(user_text: str) -> dict:
    """
    GPT parser to extract 'contact_name' and 'note'.
    E.g. "I spoke with Stamford Raffles about next week's meeting" => 
      { 'contact_name': 'Stamford Raffles', 'note': "about next week's meeting" }
    """
    system_prompt = (
        "You are a specialized parser for interaction logs in a personal CRM. "
        "User might say: 'Spoke with Jane Roe about project deadlines' or similar. "
        "Output MUST be valid JSON with 'contact_name' and 'note'."
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
            "contact_name": parsed.get("contact_name", ""),
            "note": parsed.get("note", ""),
        }
    except:
        return {}
