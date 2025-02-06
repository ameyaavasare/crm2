# agents/query_request_generator.py

import os
import json
import openai
import logging
import re
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-4o-2024-08-06"

def parse_nl_query(user_query: str) -> dict:
    """
    1) Takes a user question about interactions (e.g. "What were my last 3 discussions with Xander")
    2) Returns a JSON "plan":
       {
         "contact_name": str or None,
         "start_date": str or None,
         "end_date": str or None,
         "limit": int or None,
         "sort": "desc" or "asc" or None,
       }
    If GPT can't parse, we do a fallback so e.g. "my last interaction with X" => limit=1, contact_name = "X", sort=desc.
    """
    system_prompt = (
        "You are a query planning assistant. The user wants to retrieve rows from a CRM `interactions` table. "
        "We also have a `contacts` table joined on `interactions.contact_id = contacts.uuid`.\n"
        "Return a JSON with keys: contact_name, start_date, end_date, limit, sort.\n"
        "If the user doesn't specify, set them to null. If user says 'last 3 discussions', set limit=3, sort=desc.\n"
        "If user says 'last interaction', set limit=1, sort=desc.\n"
        "If user has a date range, set start_date and end_date to an ISO8601 date/time. "
        "If they only mention a single month or year, guess a range.\n"
        "Example:\n"
        "User: 'Tell me about my last 2 chats with Alice from July'\n"
        "Possible JSON: {\n"
        "  \"contact_name\": \"Alice\", \n"
        "  \"start_date\": \"2023-07-01T00:00:00Z\", \n"
        "  \"end_date\": \"2023-07-31T23:59:59Z\",\n"
        "  \"limit\": 2,\n"
        "  \"sort\": \"desc\"\n"
        "}"
    )

    user_prompt = (
        f"User request: {user_query}\n"
        "Output JSON exactly in the format: {\"contact_name\":..., \"start_date\":..., \"end_date\":..., \"limit\":..., \"sort\":...}"
    )

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=2048
        )
        raw_json = resp.choices[0].message.content.strip()
        plan = json.loads(raw_json)
    except Exception as e:
        logger.error(f"GPT parse error or JSON decode error: {e}")
        plan = {}

    # If GPT gave us something but it's missing keys, fill them with None
    for key in ["contact_name", "start_date", "end_date", "limit", "sort"]:
        if key not in plan:
            plan[key] = None

    # ------ Fallback Heuristics ------
    # If everything is None or we suspect GPT didn't parse well, let's handle "last X interactions with NAME" or "my last interaction with NAME"

    # 1) If the user says "last interaction" or "last X interactions" but GPT didn't fill limit
    if plan["limit"] is None:
        # match "last X" 
        match_last_num = re.search(r"last\s+(\d+)", user_query.lower())
        if match_last_num:
            # user said "last 3" or "last 2" etc.
            plan["limit"] = int(match_last_num.group(1))
            plan["sort"] = "desc"
        else:
            # if we see "last interaction" but no number
            if re.search(r"last interaction", user_query.lower()):
                plan["limit"] = 1
                plan["sort"] = "desc"

    # 2) If there's "with <name>" but GPT didn't parse a contact_name
    if not plan["contact_name"]:
        # quick guess: "with X"
        match_with_name = re.search(r"with\s+([A-Za-z]+(?:\s+[A-Za-z]+)*)", user_query, re.IGNORECASE)
        # e.g. "with Xander Taylor"
        if match_with_name:
            guess_name = match_with_name.group(1).strip()
            plan["contact_name"] = guess_name

    logger.info(f"parse_nl_query final plan: {plan}")
    return plan

def finalize_results_with_gpt(user_query: str, interactions: list) -> str:
    """
    Takes the original user query + the raw results from supabase.
    Asks GPT to present them in a concise textual summary.
    """
    system_prompt = (
        "You are a summarization assistant. You have a list of interactions from a CRM. "
        "Each item has 'note', 'created_at', 'contact_name'. Summarize them in a helpful way. "
        "Keep it short but descriptive. If no items, say so."
    )
    user_content = {
        "query": user_query,
        "results": interactions
    }
    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_content)},
            ],
            temperature=0.0,
            max_tokens=400
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error finalizing results with GPT: {e}")
        # fallback
        if len(interactions) == 0:
            return "No matching interactions found."
        else:
            lines = ["Here are the results:"]
            for i in interactions:
                lines.append(f"- {i['created_at']}: {i['contact_name']} => {i['note']}")
            return "\n".join(lines)
