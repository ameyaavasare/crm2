import os
import json
import logging
import openai
from dotenv import load_dotenv
from supabase_client import supabase
from agents.query_request_generator import parse_nl_query, finalize_results_with_gpt

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

logger = logging.getLogger(__name__)

def handle_interaction_query(user_query: str) -> str:
    """
    1) Convert user_query to a 'plan' using parse_nl_query()
    2) Execute that plan against the supabase
    3) Summarize results in a final text
    """
    # Step 1) Use GPT to interpret user's text -> query instructions
    plan = parse_nl_query(user_query)
    if not plan:
        return "Sorry, I couldn't interpret that request. Please try again."

    # 'plan' might look like:
    # {
    #   "filter": "...some ILIKE or date logic...",
    #   "limit": 3,
    #   "sort": "desc",
    #   "notes_only": false
    #   ...
    # }
    # We'll do a simplified approach here. Adjust as needed.
    try:
        query_builder = supabase.table("interactions").select("note, created_at, contact_id")

        # If plan has a name filter
        if plan.get("contact_name"):
            # Join with contacts (manual: we'll fetch contacts first, or do an in_ for contact uuids)
            # For simplicity, let's do a subquery approach or find contact uuids
            contacts_res = supabase.table("contacts").select("uuid,name").ilike("name", f"%{plan['contact_name']}%").execute()
            contact_ids = [c["uuid"] for c in contacts_res.data] if contacts_res.data else []
            if contact_ids:
                query_builder = query_builder.in_("contact_id", contact_ids)
            else:
                return f"No contacts found matching {plan['contact_name']}."

        # If we have a date range
        if plan.get("start_date") and plan.get("end_date"):
            # Filter between start_date and end_date in created_at
            query_builder = query_builder.gte("created_at", plan["start_date"]).lte("created_at", plan["end_date"])

        # If user asked for "limit"
        if plan.get("limit"):
            query_builder = query_builder.limit(plan["limit"])

        # If user asked for sorting
        if plan.get("sort") == "desc":
            query_builder = query_builder.order("created_at", desc=True)
        else:
            query_builder = query_builder.order("created_at", asc=True)

        # Actually run the query
        res = query_builder.execute()
        interactions = res.data if res.data else []

        # We might want to join contact name. Let's do it manually:
        # We'll fetch the relevant contact IDs -> map to names
        contact_ids = list({i["contact_id"] for i in interactions})
        name_map = {}
        if contact_ids:
            c_res = supabase.table("contacts").select("uuid,name").in_("uuid", contact_ids).execute()
            for c in c_res.data:
                name_map[c["uuid"]] = c["name"]

        # Attach contact name
        for i in interactions:
            i["contact_name"] = name_map.get(i["contact_id"], "Unknown")
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return "Sorry, something went wrong running that query."

    # Step 3) Summarize with GPT
    final_text = finalize_results_with_gpt(user_query, interactions)
    return final_text
