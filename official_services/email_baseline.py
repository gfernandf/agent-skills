"""
Email baseline service module.
Provides baseline implementations for email-related capabilities.
"""

def read_email(email_id):
    """
    Read an email by its ID.
    
    Args:
        email_id (str): The email identifier.
    
    Returns:
        dict: {"subject": str, "body": str, "sender": str}
    """
    # Baseline implementation: placeholder
    return {
        "subject": f"Email {email_id}",
        "body": "[Email body content]",
        "sender": "sender@example.com"
    }

def send_email(to, subject, body):
    """
    Send an email.
    
    Args:
        to (str): The recipient email address.
        subject (str): The email subject.
        body (str): The email body.
    
    Returns:
        dict: {"sent": bool}
    """
    # Baseline implementation: always succeed
    return {"sent": True}