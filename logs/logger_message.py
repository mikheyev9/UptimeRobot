
def create_message_site_is_up(url, downtime) -> str:
    return f"🟢 Monitor is UP: {url}. It was down for {downtime}."

def create_error_message(url, status, error, downtime=None) -> str:
    message = f"🔴 Monitor is DOWN: {url} (Status: {status})."
    if downtime:
        message += f" Down for: {downtime}."
    if error:
        message += f" Error: {error[:100]}..."
    return message

def create_disabled_message(url) -> str:
    return f"⚫ Monitor is DISABLED for: {url}. The check has been turned off."

def create_exception_message(url, exception: str) -> str:
    return f"⚠️ An exception occurred while processing {url}: {str(exception)[:100]}..."

