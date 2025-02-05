from fastapi import FastAPI, Form, Request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from fastapi.responses import Response
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

# For contact creation
from agents.text_parser import parse_message

# For interactions
from agents.interactions_agent import handle_interaction_message

# Insert new contacts
from supabase_client import insert_contact

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

# Store partial contact data for your existing creation flow
contact_storage = {}

@app.post("/sms")
async def receive_sms(request: Request, Body: str = Form(...), From: str = Form(...)):
    message = Body.strip()
    sender = From
    logger.info(f"Received SMS from {sender}: {message}")

    # Very basic phrase check for "with" => an interaction
    possible_interaction_phrases = [
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

    try:
        if any(p in lower_msg for p in possible_interaction_phrases):
            # Interaction flow
            response_message = handle_interaction_message(message)
        else:
            # Contact creation flow (existing logic)
            state_entry = contact_storage.get(sender)
            if state_entry and state_entry.get("state") == "awaiting_confirmation":
                # Possibly confirming
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
                # Start new contact flow
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

        # Send Twilio SMS back
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
