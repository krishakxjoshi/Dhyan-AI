import os
import firebase_admin
from firebase_admin import credentials, firestore

# Path to the service account key JSON file
current_dir = os.path.dirname(os.path.abspath(__file__))
cred_path = os.path.join(current_dir, "firebase_credentials.json") 

# Initialize Firebase App
if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()

def save_user_email(email: str) -> bool:
    """
    Saves or updates the user email in the 'users' collection.
    Automatically assigns a unique Document ID using the email.
    """
    try:
        user_ref = db.collection("users").document(email.lower().strip())
        user_ref.set({
            "email": email.lower().strip(),
            "created_at": firestore.SERVER_TIMESTAMP
        }, merge=True) # merge=True prevents overwriting existing extra data if the user logs in again
        return True
    except Exception as e:
        print(f"Error saving to Firestore: {e}")
        return False