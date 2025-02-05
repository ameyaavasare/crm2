# main.py

from fastapi import FastAPI, Form, Request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from fastapi.responses import Response
import logging
import os
import re
from datetime import datetime
from dotenv import load_dotenv

from agents.text_parser import parse_message
from agents.interactions_agent import handle_interaction_message
from agents.interaction_query import handle_interaction_query

from supabase_client import (
    insert_contact, 
    store_classification_outcome, 
    get_classification_examples
)

import openai

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
    raise ValueError("Missing Twilio credentials. Check .env")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

app = FastAPI()

contact_storage = {}
classification_storage = {}

openai.api_key = os.getenv("OPENAI_API_KEY")
CLASSIFIER_MODEL = "gpt-4o-2024-08-06"


def build_few_shot_prompt() -> str:
    examples = get_classification_examples(limit=5)
    if not examples:
        return ""
    lines = ["\nHere are some past corrected examples:\n"]
    for idx, ex in enumerate(examples, start=1):
        lines.append(
            f"{idx}) Message: '{ex['message']}' => correct_label: '{ex['correct_label']}' "
            f"(original_label was '{ex['original_label']}')"
        )
    return "\n".join(lines)

def classify_for_query(message: str) -> bool:
    few_shot_snippet = build_few_shot_prompt()
    base_system_prompt = (
        "You are a classification assistant. The user might:\n"
        "1) Provide details for a new contact or an interaction (like 'Had a chat with X...'), or\n"
        "2) Ask a question to query existing interactions (like 'Show me my last 3 calls').\n\n"
        "If the user is asking about retrieving or listing interactions, output 'query'.\n"
        "If not, output 'noquery'."
    )
    system_prompt = base_system_prompt + few_shot_snippet
    user_prompt = f"Message: {message}\nReturn JSON: {{\"label\": \"query\" or \"noquery\"}}"

    try:
        resp = openai.ChatCompletion.create(
            model=CLASSIFIER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=50
        )
        raw = resp.choices[0].message.content.strip()
        data = {}
        try:
            data = json.loads(raw)
        except:
            pass
        label = data.get("label", "noquery")
        return (label.lower() == "query")
    except Exception as e:
        logger.error(f"Error in classify_for_query: {e}")
        return False

def fallback_query_keywords(message: str) -> bool:
    """
    Simple check for words that strongly imply a query about interactions.
    """
    low = message.lower()
    query_phrases = [
        r"\bwhat\b",
        r"\btell me\b",
        r"\bshow me\b",
        r"\bwho did i speak with\b",
        r"\bdiscussions?\b",
        r"\bwho did i talk to\b",
        r"\bwho did i meet\b",
        r"\bmy last (discussion|interaction)\b",
        r"\bno results from queries?\b",  # optional
        # etc. add more if needed
    ]
    for pattern in query_phrases:
        if re.search(pattern, low):
            return True
    return False

@app.post("/sms")
async def receive_sms(request: Request, Body: str = Form(...), From: str = Form(...)):
    message = Body.strip()
    sender = From
    logger.info(f"Received SMS from {sender}: {message}")

    # Check for "FIX:" override
    fix_prefix = message.upper().strip()
    if fix_prefix.startswith("FIX:"):
        corrected_label = fix_prefix.replace("FIX:", "").strip().lower()
        user_class_data = classification_storage.get(sender)

        if not user_class_data:
            response_message = "No previous classification to fix. Please try again."
        else:
            original_label = user_class_data["original_label"]
            original_text = user_class_data["original_message"]
            store_classification_outcome(
                message=original_text,
                original_label=original_label,
                correct_label=corrected_label
            )
            if corrected_label == "query":
                response_message = handle_interaction_query(original_text)
            elif corrected_label == "interaction":
                response_message = handle_interaction_message(original_text)
            elif corrected_label == "contact":
                contact_storage[sender] = {}
                parse_result = parse_message(original_text, {})
                new_state = (
                    "awaiting_confirmation" 
                    if parse_result["status"] == "needs_confirmation"
                    else "awaiting_fields"
                )
                contact_storage[sender] = {
                    "contact_data": parse_result["contact_data"],
                    "state": new_state
                }
                response_message = parse_result["message"]
            else:
                response_message = "Unknown fix type. Must be FIX:QUERY, FIX:INTERACTION, or FIX:CONTACT."

            del classification_storage[sender]

        twilio_client.messages.create(
            body=response_message,
            from_=TWILIO_PHONE_NUMBER,
            to=sender
        )
        twiml_resp = MessagingResponse()
        twiml_resp.message(response_message)
        return Response(
            content=str(twiml_resp),
            media_type="application/xml",
            headers={"Content-Type": "application/xml; charset=utf-8"}
        )

    try:
        # 1) Priority check: Do we see an explicit "interaction" pattern?
        #    Because "I spoke with David. He told me..." = definitely interaction
        interaction_phrases = [
            "had a chat with",
            "call with",
            "spoke with",
            "spoke to",
            "met with",
            "had coffee with",
            "had lunch with",
            "had a call with",
        ]
        lower_msg = message.lower()
        is_interaction = any(p in lower_msg for p in interaction_phrases)

        if is_interaction:
            # If we find explicit interaction keywords, we classify as interaction
            classification_storage[sender] = {
                "original_label": "interaction",
                "original_message": message
            }
            response_message = handle_interaction_message(message)

        else:
            # 2) Otherwise, try GPT for "query" vs "noquery"
            gpt_says_query = classify_for_query(message)

            # 3) If GPT says "noquery" but we see fallback keywords => set query
            if not gpt_says_query and fallback_query_keywords(message):
                gpt_says_query = True
                logger.info("Manual fallback: recognized query keywords in message.")

            if gpt_says_query:
                classification_storage[sender] = {
                    "original_label": "query",
                    "original_message": message
                }
                response_message = handle_interaction_query(message)
            else:
                # 4) If neither interaction nor query => contact
                classification_storage[sender] = {
                    "original_label": "contact",
                    "original_message": message
                }
                state_entry = contact_storage.get(sender)
                if state_entry and state_entry.get("state") == "awaiting_confirmation":
                    if message.lower() in ["yes", "y"]:
                        insert_result = insert_contact(state_entry["contact_data"])
                        del contact_storage[sender]
                        if insert_result and "error" not in insert_result:
                            response_message = "Contact saved successfully!"
                        else:
                            response_message = f"Error saving contact: {insert_result.get('error','unknown error')}"
                    elif message.lower() in ["no", "n"]:
                        del contact_storage[sender]
                        response_message = "Contact creation cancelled."
                    else:
                        existing_data = state_entry["contact_data"]
                        parse_result = parse_message(message, existing_data)
                        new_state = (
                            "awaiting_confirmation" 
                            if parse_result["status"] == "needs_confirmation"
                            else "awaiting_fields"
                        )
                        contact_storage[sender] = {
                            "contact_data": parse_result["contact_data"],
                            "state": new_state
                        }
                        response_message = parse_result["message"]
                else:
                    existing_data = state_entry["contact_data"] if state_entry else {}
                    parse_result = parse_message(message, existing_data)
                    new_state = (
                        "awaiting_confirmation" 
                        if parse_result["status"] == "needs_confirmation"
                        else "awaiting_fields"
                    )
                    contact_storage[sender] = {
                        "contact_data": parse_result["contact_data"],
                        "state": new_state
                    }
                    response_message = parse_result["message"]

        # Send Twilio SMS
        twilio_client.messages.create(
            body=response_message,
            from_=TWILIO_PHONE_NUMBER,
            to=sender
        )

        # Return TwiML
        twiml_resp = MessagingResponse()
        twiml_resp.message(response_message)
        return Response(
            content=str(twiml_resp),
            media_type="application/xml",
            headers={"Content-Type": "application/xml; charset=utf-8"}
        )

    except Exception as e:
        logger.error(f"Error processing SMS: {e}", exc_info=True)
        error_message = "Sorry, there was an error. Please try again."
        twilio_client.messages.create(
            body=error_message,
            from_=TWILIO_PHONE_NUMBER,
            to=sender
        )
        twiml_resp = MessagingResponse()
        twiml_resp.message(error_message)
        return Response(
            content=str(twiml_resp),
            media_type="application/xml",
            headers={"Content-Type": "application/xml; charset=utf-8"}
        )
