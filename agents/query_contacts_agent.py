import os
import openai
import json
from dotenv import load_dotenv
from supabase_client import supabase

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def handle_query_contacts(message: str) -> str:
    """
    Search the 'contacts' table by name or partial name, and return matching results.
    We'll parse the message to find the name user is looking for.
    Then we do a partial match (ilike) in Supabase.
    If multiple matches, we list them.
    If none found, we say so.
    """

    # Step 1: parse user text for the name to find
    parsed_data = parse_query_info(message)
    search_name = parsed_data.get("search_name", "").strip()

    if not search_name:
        return ("I’m not sure which contact you want to find. "
                "Please specify the name or partial name.")

    # Step 2: partial name search
    response = supabase.table("contacts").select("*").ilike("name", f"%{search_name}%").execute()
    rows = response.data

    if not rows:
        return f"No contacts found matching '{search_name}'."

    # If many matches, list them
    results_summary = []
    for row in rows:
        # Return relevant fields
        contact_summary = (
            f"Name: {row.get('name') or ''}\n"
            f"Phone: {row.get('phone') or ''}\n"
            f"Email: {row.get('email') or ''}\n"
            f"Birthday: {row.get('birthday') or ''}\n"
            f"Family members: {row.get('family_members') or ''}\n"
            f"Description: {row.get('description') or ''}\n"
            "-------"
        )
        results_summary.append(contact_summary)

    return f"Found {len(rows)} contact(s):\n" + "\n".join(results_summary)

def parse_query_info(user_text: str) -> dict:
    """
    GPT-based parser to extract 'search_name' from user text, e.g.:
    "Find contact info for John Smith" => {"search_name": "John Smith"}
    If user doesn't specify a name, we return blank.
    """
    system_prompt = (
        "You are a specialized parser for searching contacts in a personal CRM. "
        "The user might say: 'Find contact info for John Smith' or 'Show me Jane's contact.' "
        "Output MUST be valid JSON with one key: 'search_name'. "
        "If you can’t find a name, leave it blank."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            temperature=0,
            max_tokens=100,
        )
        parsed = json.loads(response.choices[0].message.content.strip())
        return {"search_name": parsed.get("search_name", "")}
    except:
        return {}
