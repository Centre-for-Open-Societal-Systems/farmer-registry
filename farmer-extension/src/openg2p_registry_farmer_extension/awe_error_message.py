"""Wording for a failed call to the approval service (no framework imports)."""

import re

_UNSAFE = re.compile(r"[{}\[\]]|https?://|://|Traceback|\b(?:HTTP|Errno|errno)\b|_[A-Za-z]|[A-Za-z]_")


def awe_error_message(status_code, reply) -> str:
    """A sentence for the person who pressed the button.

    A reply that already reads as one short sentence is kept. JSON, an
    internal address, a code or a stack trace never reaches the screen.
    """
    text = " ".join(str(reply or "").split())
    if text and len(text) <= 200 and not _UNSAFE.search(text) and " " in text:
        return text if text[-1] in ".!?" else text + "."
    if status_code in (401, 403):
        return "You do not have permission to do this in the approvals list. Sign in again, or ask an administrator."
    if status_code == 404:
        return "This approval task was not found. It may have been decided already; refresh the approvals list."
    if status_code == 409:
        return "This approval task has changed since you opened it. Refresh the approvals list and try again."
    return ("The approval service could not complete this. Try again in a few minutes, "
            "and contact support if it continues.")
