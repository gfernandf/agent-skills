"""
Message baseline service module.
Provides baseline implementations for message-related capabilities.
"""

def send_message(channel, message):
    """
    Send a message to a channel.
    
    Args:
        channel (str): The channel identifier.
        message (str): The message content.
    
    Returns:
        dict: {"sent": bool}
    """
    # Baseline implementation: always succeed
    return {"sent": True}