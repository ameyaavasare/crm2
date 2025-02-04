import os
import openai
import json
from dotenv import load_dotenv
from supabase_client import supabase

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def handle_interaction_query(message: str) -> str:
    """
    Query interactions in a more conversational manner.
    1) parse user text for contact_name, limit, or date range,
    2) partial-match contact,
    3) fetch 'interactions' sorted by created_at desc,
    4) return them as a summary.
    """

    data = parse_interaction_query(message)
    contact_name = data.get("contact_name", "").strip()
    limit_val = data.get("limit", "5").strip()

    try:
        limit = int(limit_val)
    except:
        limit = 5

    if not contact_name:
        return "I’m not sure whose interactions you want to see. Please name the contact."

    # partial match
    possible = supabase.table("contacts").select("*").ilike("name", f"%{contact_name}%").execute().data
    if not possible:
        return f"No contacts found matching '{contact_name}'."
    if len(possible) > 1:
        # multiple matches
        matches = [p["name"] for p in possible]
        return (f"Found multiple contacts matching '{contact_name}': {matches}.\n"
                "Please clarify the exact name or unique detail.")
    contact_id = possible[0]["uuid"]

    # get interactions
    rows = (supabase.table("interactions")
            .select("*")
            .eq("contact_id", contact_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data)

    if not rows:
        return f"No interactions found for '{possible[0]['name']}'."

    lines = [f"Interaction {i+1}: {r['note']} (Date: {r['created_at']})" for i, r in enumerate(rows)]
    return (f"Here are the last {len(rows)} interactions for {possible[0]['name']}:\n" +
            "\n".join(lines))

def parse_interaction_query(user_text: str) -> dict:
    """
    GPT parser for 'contact_name' and 'limit' from user request. If no limit, default to '5'.
    """
    system_prompt = (
        "You are a specialized parser for queries about interactions in a personal CRM. "
        "User might say: 'Show me the last 3 times I spoke with John Doe' or 'All interactions with Jane' etc. "
        "Output MUST be JSON with 'contact_name' and 'limit'. If limit not specified, use '1'."
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
        parsed = json.loads(response.choices[0].message.content.strip())
        return {
            "contact_name": parsed.get("contact_name", ""),
            "limit": max(int(parsed.get("limit", "1")), 1)
        }
    except:
        return {}
