"""Three views exercising the SDK end-to-end."""

from django.http import HttpResponse

import insider


def home(_request):
    return HttpResponse("demo home — try /boom/ or /notice/")


def boom(_request):
    """Raise an unhandled exception. The middleware captures it as a Beacon."""
    raise ValueError("intentional demo explosion")


def notice(_request):
    """Manual capture: send a Beacon without raising."""
    insider.capture_message("demo notice from /notice/", level="warning")
    return HttpResponse("captured")
