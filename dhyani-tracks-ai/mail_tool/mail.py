import os
import base64
import pandas as pd
import json
import time
from datetime import datetime
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pandas import Series

SCOPES = ['https://www.googleapis.com/auth/gmail.send',"https://www.googleapis.com/auth/gmail.readonly"]

def get_gmail_service():
    creds = None
    # token.json stores your secure, passwordless login session
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    # If there are no valid credentials, handle the passwordless login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            # This opens your default web browser for a secure login
            creds = flow.run_local_server(port=0)
            
        # Save the token for future silent runs
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)

def send_email_via_api(to_email, subject, body_text):
    try:
        service = get_gmail_service()
        
        # Structure the email
        message = MIMEText(body_text)
        message['to'] = to_email
        message['subject'] = subject
        
        # Gmail API requires encoding the mail into base64 format
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        email_body = {'raw': raw_message}
        
        print("Agent is transmitting email securely...")
        send_operation = service.users().messages().send(userId="me", body=email_body).execute()
        print(f"🚀 Sent! Message ID: {send_operation['id']}")
        return True, send_operation['id']
        
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False, None


def is_bounced(email_address):
    service = get_gmail_service()

    query = "from:mailer-daemon newer_than:1d"

    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=20)
        .execute()
    )

    messages = results.get("messages", [])

    if not messages:
        return False

    error_keywords = [
        "address not found",
        "couldn't be found",
        "wasn't delivered",
        "550 5.1.1",
        "does not exist",
        "no such user",
        "nosuchuser",
        "recipient address rejected",
        "delivery status notification (failure)"
    ]

    for msg in messages:

        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=msg["id"],
                format="full"
            )
            .execute()
        )

        # Start with Gmail's snippet
        text_to_check = message.get("snippet", "").lower()

        # Extract text/plain parts if present
        payload = message.get("payload", {})

        if "parts" in payload:

            for part in payload["parts"]:

                if part.get("mimeType") == "text/plain":

                    data = part.get("body", {}).get("data")

                    if data:
                        try:
                            body = base64.urlsafe_b64decode(
                                data
                            ).decode(errors="ignore")

                            text_to_check += "\n" + body.lower()

                        except Exception:
                            pass

        else:

            data = payload.get("body", {}).get("data")

            if data:
                try:
                    body = base64.urlsafe_b64decode(
                        data
                    ).decode(errors="ignore")

                    text_to_check += "\n" + body.lower()

                except Exception:
                    pass

        # Check if this bounce is for our recipient
        if email_address.lower() in text_to_check:

            if any(keyword in text_to_check for keyword in error_keywords):
                return True

    return False

def check_mail_send(party_mail):
    if is_bounced(party_mail):
        print("❌ Email does NOT exist")
        return False
    else:
        print("✅ No bounce detected")
        return True


date = datetime.now().strftime("%d-%m-%Y")
current_time = datetime.now().strftime("%H:%M:%S")
customer_data = pd.read_json("file2.json",  typ = "series")
customer_mail = customer_data["client mail"]
chat_summary = customer_data["chat summary"]
total_amount = customer_data["total"]
items = customer_data["item(s)"].split(", ")
items_df = pd.DataFrame(items,columns=["Item"])
pricing_df = pd.DataFrame(
    list(customer_data["pricing"].items()),
    columns=["Item", "Price"])
items_df["Price"] = items_df["Item"].map(customer_data["pricing"])
items_table = items_df.to_string(index=False, col_space=18, justify="center")

# if __name__ == '__main__':
def first_party_mail():
    
    # No passwords here!
    return send_email_via_api(
        to_email= customer_mail,
        subject="Your Order Has Been Successfully Placed!",
        body_text=f"""
Dear Customer,

Thank you for your order. We are pleased to confirm that your order has been successfully placed and is now being processed.

Order Details:

* Chat Summary:
{chat_summary}

* Order Date: {date}
* Order Time: {time}
* Estimated Delivery Date: [delivery_date]

Ordered Items:

{items_table}

* Total Amount: ₹{total_amount}

We will send you another email once your order has been shipped, along with tracking information.
If you have any questions regarding your order, please feel free to contact us.

Thank you for choosing [company_name].

Warm regards,
[company_name]
[contact_information]"""
    )


def second_party_mail():

    date = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    return send_email_via_api(
        to_email="catgu12321@gmail.com",
        subject="New Order Received!",
        body_text=f"""
Chat Summary : 
{chat_summary}

Order Date: {date}
Order Time: {time}
Client Email: {customer_mail}

Ordered Items:

{items_table}


Total Amount

₹{total_amount}"""
    )

# first party is our customer
# 
customer_success, customer_msg_id = first_party_mail()
print("Waiting for bounce for first party...")
time.sleep(30)
first_party_mail_check = check_mail_send(customer_mail)


admin_success, admin_msg_id = second_party_mail()
print("Waiting for bounce for second party...")
time.sleep(30)
second_party_mail_check = check_mail_send("catgu12321@gmail.com")


if first_party_mail_check and second_party_mail_check:

    data = {
        "Status":"Successful"
    }

    with open(f"{customer_msg_id}.json", "w") as f:
        json.dump(data, f, indent=4)

    print("JSON file created.")

else:

    data = {
            "Status":"UnSuccessful"
        }
    
    with open(f"{customer_msg_id}.json", "w") as f:
            json.dump(data, f, indent=4)
    
    print("JSON file created.")