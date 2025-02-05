from fastapi import FastAPI, Form, Request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from fastapi.responses import Response
import logging
import os
from agents.text_parser import parse_message
from supabase_client import insert_contact
from datetime import datetime
from dotenv import load_dotenv

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get and verify Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Verify credentials are loaded
if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
    raise ValueError(
        "Missing Twilio credentials. Please check TWILIO_ACCOUNT_SID, "
        "TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER in your .env file"
    )

logger.info(f"Initialized with Twilio number: {TWILIO_PHONE_NUMBER}")

# Initialize Twilio client
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

app = FastAPI()

# Store temporary contact data between messages
contact_storage = {}

@app.post("/sms")
async def receive_sms(request: Request, Body: str = Form(...), From: str = Form(...)):
    logger.info("=" * 50)
    logger.info(f"Received SMS - From: {From}, Body: {Body}")
    logger.info(f"Current contact_storage state: {contact_storage}")

    # Preserve original message casing (for names, emails, etc.)
    message = Body.strip()
    sender = From  # Use as key in contact_storage
    state_entry = contact_storage.get(sender)

    try:
        # Check if we are waiting for confirmation (i.e. all fields have been gathered)
        if state_entry and state_entry.get("state") == "awaiting_confirmation":
            if message.lower() in ['yes', 'y']:
                logger.info("Confirmation received, inserting contact")
                insert_result = insert_contact(state_entry["contact_data"])
                logger.info(f"Insert result: {insert_result}")
                del contact_storage[sender]
                response_message = "Contact saved successfully!"
            elif message.lower() in ['no', 'n']:
                logger.info("Confirmation denied, clearing storage")
                del contact_storage[sender]
                response_message = "Contact creation cancelled. Please start over."
            else:
                # Assume additional data is provided to update the contact.
                logger.info("Additional data received while awaiting confirmation, updating contact info.")
                existing_data = state_entry["contact_data"]
                result = parse_message(message, existing_data)
                new_state = "awaiting_confirmation" if result["status"] == "needs_confirmation" else "awaiting_fields"
                contact_storage[sender] = {"contact_data": result["contact_data"], "state": new_state}
                response_message = result["message"]
        else:
            # Not yet in the confirmation state; process the incoming message as new info or missing info.
            existing_data = state_entry["contact_data"] if state_entry else {}
            result = parse_message(message, existing_data)
            new_state = "awaiting_confirmation" if result["status"] == "needs_confirmation" else "awaiting_fields"
            contact_storage[sender] = {"contact_data": result["contact_data"], "state": new_state}
            response_message = result["message"]

        logger.info(f"Final contact_storage state: {contact_storage}")
        logger.info(f"Sending response: {response_message}")

        # Send SMS using Twilio client
        twilio_client.messages.create(
            body=response_message,
            from_=TWILIO_PHONE_NUMBER,
            to=sender
        )
        logger.info("Message sent successfully")

        return Response(
            content=str(MessagingResponse().message(response_message)),
            media_type="application/xml",
            headers={"Content-Type": "application/xml; charset=utf-8"}
        )

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}", exc_info=True)
        error_message = "Sorry, there was an error processing your message. Please try again."
        
        twilio_client.messages.create(
            body=error_message,
            from_=TWILIO_PHONE_NUMBER,
            to=sender
        )
        
        return Response(
            content=str(MessagingResponse().message(error_message)),
            media_type="application/xml",
            headers={"Content-Type": "application/xml; charset=utf-8"}
        )

if __name__ == "__main__":
    import uvicorn
    # Run the app on localhost:8000
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)