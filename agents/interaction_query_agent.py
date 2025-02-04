import os
import openai
import json
from dotenv import load_dotenv
from ..supabase_client import supabase

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def handle_interaction_query(message: str) -> str:
    """
    Query interactions from the 'interactions' table in a more conversational manner.
    Example user request: "Show me the last 3 times I spoke with Stamford Raffles."
    We'll parse 'contact_name' and a limit or date range. If limit is missing, default e.g. 5.
    Then we find the contact, select from interactions, and return a simple summary.
    """

    query_data = parse_interaction_query(message)
    contact_name = query_data.get("contact_name")
    limit_str = query_data.get("limit", "5")
    try:
        limit_val = int(limit_str)
    except ValueError:
        limit_val = 5

    if not contact_name:
        return "I couldn’t find a contact name to look up. Please mention who you're asking about."

    # Find contact by name
    contact_res = supabase.table("contacts").select("uuid").eq("name", contact_name).execute()
    contact_rows = contact_res.data
    if not contact_rows:
        return f"No contact found with the name '{contact_name}'."

    contact_uuid = contact_rows[0]["uuid"]

    # Query interactions
    interaction_res = (
        supabase.table("interactions")
        .select("*")
        .eq("contact_id", contact_uuid)
        .order("created_at", desc=True)
        .limit(limit_val)
        .execute()
    )
    interactions = interaction_res.data

    if not interactions:
        return f"No interactions found for {contact_name}."

    # Summarize results
    summary_lines = []
    for i, row in enumerate(interactions, start=1):
        note = row["note"]
        created_at = row["created_at"]
        summary_lines.append(f"{i}. {note} (on {created_at})")

    return f"Here are the last {len(interactions)} interactions with {contact_name}:\n" + "\n".join(summary_lines)

def parse_interaction_query(user_text: str) -> dict:
    """
    Uses GPT to extract 'contact_name' and 'limit' (number of interactions requested).
    If not specified, default limit to e.g. 5.
    Returns { 'contact_name': str, 'limit': str }
    """
    system_prompt = (
        "You are a specialized parser for queries about interactions in a personal CRM. "
        "User messages might say: 'Can you tell me about the last 3 times I spoke with Stamford Raffles?' "
        "Output MUST be valid JSON with 'contact_name' and 'limit'. "
        "If the user doesn’t specify how many times, use '5' as limit. "
        "If the name is missing, leave it blank. Example: {'contact_name': 'Stamford Raffles', 'limit': '3'}."
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
            "contact_name": parsed.get("contact_name", ""),
            "limit": parsed.get("limit", "5"),
        }
    except Exception:
        return {}
