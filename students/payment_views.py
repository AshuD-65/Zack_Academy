import json
import os

from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

try:
    import stripe
except ModuleNotFoundError:  # pragma: no cover - depends on environment
    stripe = None

from .models import Student, Course

def _get_stripe_secret_key() -> str:
    """
    Fetch Stripe secret key from settings/env.
    Never fall back to a hard-coded key: it causes payments to go to the wrong
    Stripe account/mode and makes debugging impossible.
    """
    key = getattr(settings, "STRIPE_SECRET_KEY", None) or os.getenv("STRIPE_SECRET_KEY")
    if not key:
        raise ImproperlyConfigured(
            "Missing STRIPE_SECRET_KEY. Set it in your environment or .env."
        )
    return key


def _configure_stripe():
    if stripe is None:
        raise ImproperlyConfigured(
            "Stripe SDK is not installed. Run `pip install stripe`."
        )
    stripe.api_key = _get_stripe_secret_key()


def checkout(request):
    """Show checkout page with amount and proceed button."""
    course_code = request.GET.get("course_code", "")
    amount_str = request.GET.get("amount_dollars", "2.00")
    try:
        amount_dollars = float(amount_str)
        amount_cents = int(round(amount_dollars * 100))
    except (ValueError, TypeError):
        amount_dollars = 2.00
        amount_cents = 200
    if amount_cents < 50:
        amount_cents = 50
        amount_dollars = 0.50

    context = {
        "course_code": course_code,
        "amount_dollars": f"{amount_dollars:.2f}",
        "amount_cents": amount_cents,
    }
    return render(request, "students/checkout.html", context)


@require_POST
def create_checkout_session(request):
    """
    Create a Stripe Checkout Session and redirect to Stripe's hosted payment page.
    This avoids embedded iframes that can block input.
    """
    course_code = request.POST.get("course_code", "")
    amount_str = request.POST.get("amount_dollars", "2.00")
    try:
        amount_dollars = float(amount_str)
        amount_cents = int(round(amount_dollars * 100))
    except (ValueError, TypeError):
        amount_cents = 200
        amount_dollars = 2.00
    if amount_cents < 50:
        amount_cents = 50

    base_url = request.build_absolute_uri("/").rstrip("/")
    success_url = f"{base_url}{reverse('payment_success')}?session_id={{CHECKOUT_SESSION_ID}}"
    if course_code:
        success_url += f"&course_code={course_code}"
    cancel_url = f"{base_url}{reverse('payment_checkout')}?course_code={course_code}&amount_dollars={amount_dollars:.2f}"

    product_name = "Course Enrollment"
    if course_code:
        try:
            course = Course.objects.get(course_code=course_code)
            product_name = f"{course.course_name} ({course_code})"
        except Course.DoesNotExist:
            pass

    try:
        _configure_stripe()
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": product_name},
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "course_code": course_code or "",
                "student_id": str(request.session.get("student_id", "")),
            },
        )
        return redirect(session.url, status=303)
    except Exception as e:
        from django.contrib import messages
        messages.error(request, f"Payment error: {str(e)}")
        return redirect(
            reverse("payment_checkout")
            + f"?course_code={course_code}&amount_dollars={amount_dollars:.2f}"
        )


@require_GET
def payment_success(request):
    """Handle return from Stripe Checkout; verify payment and enroll if course_code present."""
    session_id = request.GET.get("session_id")
    course_code = request.GET.get("course_code", "")

    if not session_id:
        from django.contrib import messages
        messages.error(request, "Invalid payment session.")
        return redirect("dashboard")

    try:
        _configure_stripe()
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status != "paid":
            from django.contrib import messages
            messages.warning(request, "Payment was not completed.")
            return redirect("dashboard")
    except Exception:
        from django.contrib import messages
        messages.error(request, "Could not verify payment.")
        return redirect("dashboard")

    # Enroll student if course_code and logged in
    if course_code and "student_id" in request.session:
        try:
            student = Student.objects.get(student_id=request.session["student_id"])
            course = Course.objects.get(course_code=course_code)
            if not student.courses.filter(course_code=course_code).exists():
                student.courses.add(course)
            from django.contrib import messages
            messages.success(request, f"Payment successful! You are now enrolled in {course.course_name}.")
        except (Student.DoesNotExist, Course.DoesNotExist):
            from django.contrib import messages
            messages.success(request, "Payment successful!")

    return redirect("dashboard")


@csrf_exempt
@require_POST
def create_payment_intent(request):
    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    amount = body.get("amount", 200)
    try:
        amount_int = int(amount)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Amount must be an integer (cents)")

    # Enforce Stripe minimum for USD (50 cents)
    if amount_int < 50:
        amount_int = 50

    try:
        _configure_stripe()
        intent = stripe.PaymentIntent.create(
            amount=amount_int,
            currency="usd",
            automatic_payment_methods={
                "enabled": True,
                "allow_redirects": "never",
            },
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"clientSecret": intent.client_secret})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """
    Stripe webhook to reliably capture successful payments even if the user
    closes the browser before returning to /payment/success/.
    """
    try:
        _configure_stripe()
    except ImproperlyConfigured:
        return HttpResponseBadRequest("Stripe is not configured")

    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", None)

    # If webhook secret is not configured, we can't verify signatures safely.
    if not webhook_secret:
        return HttpResponseBadRequest("Missing STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        return HttpResponseBadRequest("Invalid payload")
    except stripe.error.SignatureVerificationError:
        return HttpResponseBadRequest("Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        if session.get("payment_status") == "paid":
            metadata = session.get("metadata") or {}
            course_code = (metadata.get("course_code") or "").strip()
            student_id = (metadata.get("student_id") or "").strip()
            if course_code and student_id:
                try:
                    student = Student.objects.get(student_id=student_id)
                    course = Course.objects.get(course_code=course_code)
                    if not student.courses.filter(course_code=course_code).exists():
                        student.courses.add(course)
                except (Student.DoesNotExist, Course.DoesNotExist):
                    return JsonResponse({"received": True})
