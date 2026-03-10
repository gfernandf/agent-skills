"""
Email baseline service module.
Provides baseline implementations for email-related capabilities.
"""

def read_emails(mailbox):
    """
    Read emails from a mailbox.
    
    Args:
        mailbox (str): The mailbox or folder name.
    
    Returns:
        dict: {"messages": list}
    """
    # Baseline implementation: return sample emails
    messages = [
        {
            "subject": f"Sample email 1 from {mailbox}",
            "body": "This is a sample email body.",
            "sender": "sender1@example.com",
            "date": "2023-01-01"
        },
        {
            "subject": f"Sample email 2 from {mailbox}",
            "body": "Another sample email.",
            "sender": "sender2@example.com",
            "date": "2023-01-02"
        }
    ]
    return {"messages": messages}

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