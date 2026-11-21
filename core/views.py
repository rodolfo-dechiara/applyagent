"""Server-rendered views for the core app. All application views are login-only
and filter by request.user, so another user's application is a 404."""

from typing import Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser, User
from django.core.mail import send_mail
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, FormView, ListView, TemplateView, UpdateView, View

from agent.service import ApplicationPackage, GenerationError, generate_application_package
from core.demo_data import ensure_demo_jobs
from core.forms import (
    ApplicationEditForm,
    JobPostingForm,
    ProfileForm,
    RegisterForm,
    ResendVerificationForm,
)
from core.models import (
    EMAIL_VERIFICATION_TTL,
    Application,
    EmailVerification,
    JobPosting,
    Profile,
)
from core.ratelimit import rate_limited
from core.security import client_ip
from core.security import logger as security_logger


def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    """Branded 403 for CSRF rejections.

    The usual cause in normal use: a page rendered *before* a login rotated
    the CSRF cookie (Django rotates it on every login) is submitted after the
    rotation — e.g. the navbar's Log out button on a tab that was open across
    a re-login. The internal reason stays in the server log
    (django.security.csrf) and is never shown to the user.
    """
    if reason:
        security_logger.info(
            "csrf_rejected reason=%s path=%s ip=%s", reason, request.path, client_ip(request)
        )
    return render(request, "403_csrf.html", status=403)


def send_verification_email(request: HttpRequest, user: User) -> bool:
    """Create/rotate the token and email the verification link.

    Returns False (and logs) instead of raising when the mail backend fails,
    so a broken SMTP relay degrades to a friendly error message, not a 500.
    """
    verification = EmailVerification.create_for(user)
    url = request.build_absolute_uri(reverse("verify_email", args=[verification.token]))
    subject = render_to_string(
        "registration/verification_email_subject.txt", {"user": user}
    ).strip()
    body = render_to_string(
        "registration/verification_email_body.txt",
        {
            "user": user,
            "url": url,
            "ttl_hours": int(EMAIL_VERIFICATION_TTL.total_seconds() // 3600),
        },
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
    except Exception:
        security_logger.exception(
            "verification_email_failed user=%s ip=%s", user.username, client_ip(request)
        )
        return False
    security_logger.info("verification_email_sent user=%s ip=%s", user.username, client_ip(request))
    return True


def apply_package(application: Application, package: ApplicationPackage) -> None:
    """Write a generated package onto an Application, including provenance."""
    application.tailored_summary = package.tailored_summary
    application.cover_letter = package.cover_letter
    application.screening_answers = package.screening_answers
    application.match_score = package.match_score
    application.match_reasons = package.match_reasons
    application.red_flags = package.red_flags
    application.agent_mode = package.mode
    application.agent_model = package.model
    application.generated_at = timezone.now()
    application.save()


@method_decorator(rate_limited("register", 5, 3600), name="dispatch")
class RegisterView(FormView):
    """Register, then require email verification before the account can log in.

    The account is created inactive (ASVS V2.1); a single-use, expiring token
    is emailed and the candidate is sent to a "check your inbox" page instead
    of being logged in.
    """

    template_name = "registration/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("register_done")

    def form_valid(self, form: RegisterForm) -> HttpResponse:
        user = form.save(commit=False)
        user.is_active = False
        user.save()
        sent = send_verification_email(self.request, user)
        security_logger.info(
            "register user=%s ip=%s (unverified)", user.username, client_ip(self.request)
        )
        if sent:
            messages.info(
                self.request,
                "Account created — we sent a verification link to your email. "
                "You can log in once you click it.",
            )
        else:
            messages.error(
                self.request,
                "Account created, but we could not send the verification email — "
                "please try resending it from the login page.",
            )
        return super().form_valid(form)


class RegisterDoneView(TemplateView):
    """Neutral 'check your inbox' page; reveals nothing about any address."""

    template_name = "registration/register_done.html"


@method_decorator(
    rate_limited(
        "login",
        10,
        900,
        ident=lambda request: f"{client_ip(request)}:{request.POST.get('username', '')}",
    ),
    name="dispatch",
)
class RateLimitedLoginView(auth_views.LoginView):
    """Django's login view with per-IP + per-account rate limiting (ASVS V2.2.1)."""


class VerifyEmailView(View):
    """Visit the emailed link: activate the account, consume the token, log in."""

    def get(self, request: HttpRequest, token: str, *args: Any, **kwargs: Any) -> HttpResponse:
        verification = EmailVerification.objects.filter(token=token).select_related("user").first()
        if verification is None:
            return HttpResponse(status=404)
        user = verification.user
        if verification.is_expired:
            verification.delete()
            security_logger.info(
                "verify_expired_token user=%s ip=%s", user.username, client_ip(request)
            )
            messages.error(
                request,
                "That verification link has expired — request a new one from the login page.",
            )
            return redirect("resend_verification")
        user.is_active = True
        user.save(update_fields=["is_active"])
        verification.delete()
        user.backend = "django.contrib.auth.backends.ModelBackend"
        login(request, user)
        security_logger.info("email_verified user=%s ip=%s", user.username, client_ip(request))
        messages.success(request, "Email verified — welcome to You're Hired!")
        return redirect("core:dashboard")


@method_decorator(rate_limited("resend", 3, 3600), name="dispatch")
class ResendVerificationView(FormView):
    """Resend the verification link. The response never reveals whether the
    address is registered or already verified (no account enumeration)."""

    template_name = "registration/resend_verification.html"
    form_class = ResendVerificationForm
    success_url = reverse_lazy("register_done")

    def form_valid(self, form: ResendVerificationForm) -> HttpResponse:
        email = form.cleaned_data["email"]
        user = User.objects.filter(email__iexact=email, is_active=False).first()
        if user is not None:
            if not send_verification_email(self.request, user):
                messages.error(
                    self.request,
                    "We could not send the verification email right now — please try again later.",
                )
                return super().form_valid(form)
        else:
            security_logger.info("verification_resend_noop ip=%s", client_ip(self.request))
        messages.info(
            self.request,
            "If that address is registered and not yet verified, we've sent a new "
            "verification link.",
        )
        return super().form_valid(form)


class DashboardView(LoginRequiredMixin, TemplateView):
    """The applications list, with an empty state and a profile nudge."""

    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["applications"] = Application.objects.filter(user=self.request.user).select_related(
            "job"
        )
        context["has_profile"] = Profile.objects.filter(user=self.request.user).exists()
        return context


class ProfileView(LoginRequiredMixin, View):
    """One view for the master profile: creates on first save, updates after."""

    template_name = "core/profile_form.html"

    def get_profile(self) -> Profile:
        profile, _created = Profile.objects.get_or_create(user=self.request.user)
        return profile

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = ProfileForm(instance=self.get_profile())
        return render(request, self.template_name, {"form": form})

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = ProfileForm(request.POST, instance=self.get_profile())
        if form.is_valid():
            form.save()
            messages.success(request, "Profile saved.")
            return redirect("core:dashboard")
        return render(request, self.template_name, {"form": form})


def create_application_with_package(
    user: AbstractBaseUser | AnonymousUser, job: JobPosting
) -> tuple[Application, str | None]:
    """Create the Application for (user, job) and generate its package.

    Shared by the paste-a-job flow and the apply-from-public-board flow — both
    behind LoginRequiredMixin, so the assert below always holds.
    Returns (application, error): on GenerationError the application still
    exists (empty package, correct provenance) and error carries the message,
    so the candidate can regenerate from the application page.
    """
    assert isinstance(user, User)
    profile, _created = Profile.objects.get_or_create(user=user)
    try:
        package = generate_application_package(profile, job)
    except GenerationError as exc:
        application = Application.objects.create(
            job=job,
            user=user,
            agent_mode=(
                Application.AgentMode.MISTRAL
                if settings.MISTRAL_API_KEY
                else Application.AgentMode.DEMO
            ),
            agent_model=(str(settings.MISTRAL_MODEL) if settings.MISTRAL_API_KEY else "demo"),
            generated_at=timezone.now(),
        )
        return application, str(exc)
    application = Application.objects.create(job=job, user=user)
    apply_package(application, package)
    return application, None


class JobCreateView(LoginRequiredMixin, FormView):
    """Paste a job posting; on save the package is generated immediately."""

    template_name = "core/job_form.html"
    form_class = JobPostingForm

    def form_valid(self, form: JobPostingForm) -> HttpResponse:
        job = form.save(commit=False)
        job.owner = self.request.user
        job.save()
        application, error = create_application_with_package(self.request.user, job)
        if error is not None:
            messages.error(
                self.request,
                f"Generation failed: {error} You can regenerate from the application page.",
            )
        else:
            messages.success(
                self.request,
                "Application package generated — review and edit it; nothing is "
                "final until you say so.",
            )
        return redirect("core:application_detail", pk=application.pk)


class JobBoardView(ListView):
    """The public jobs board: every posting whose owner opted in with
    is_public. Anonymous access is intended. When the demo flag is on,
    clearly-marked fake postings are seeded on first view (idempotent)."""

    template_name = "core/job_board.html"
    context_object_name = "postings"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        ensure_demo_jobs()  # no-op unless settings.DEMO_JOBS_ENABLED
        return super().get(request, *args, **kwargs)

    def get_queryset(self) -> QuerySet[JobPosting]:
        return (
            JobPosting.objects.filter(is_public=True)
            .select_related("owner")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["demo_jobs_enabled"] = settings.DEMO_JOBS_ENABLED
        return context


class JobBoardDetailView(DetailView):
    """Public detail for a board posting. Private postings are visible only to
    their owner — everyone else (including anonymous) gets a 404, matching the
    cross-user ownership rule used for applications."""

    template_name = "core/job_board_detail.html"
    context_object_name = "posting"

    def get_object(self, queryset: QuerySet[JobPosting] | None = None) -> JobPosting:
        posting = get_object_or_404(JobPosting, pk=self.kwargs["pk"])
        if not posting.is_public and posting.owner != self.request.user:
            raise Http404
        return posting


@method_decorator(rate_limited("job_apply", 20, 3600), name="dispatch")
class JobBoardApplyView(LoginRequiredMixin, View):
    """POST-only: build the candidate's own application from a board posting.

    The public posting is never modified — the candidate gets a private clone
    (same title/company/description/source_url, is_public=False) and a fresh
    generated package. Applying twice to the same posting reuses the existing
    clone and application instead of duplicating them. Private postings are
    off-limits to everyone but their owner (404)."""

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        posting = get_object_or_404(JobPosting, pk=kwargs["pk"])
        if not posting.is_public and posting.owner != request.user:
            raise Http404
        clone = JobPosting.objects.filter(
            owner=request.user,
            title=posting.title,
            company=posting.company,
            source_url=posting.source_url,
        ).first()
        if clone is not None:
            existing = Application.objects.filter(job=clone, user=request.user).first()
            if existing is not None:
                messages.info(request, "You already have an application for this posting.")
                return redirect("core:application_detail", pk=existing.pk)
        else:
            clone = JobPosting.objects.create(
                owner=request.user,
                title=posting.title,
                company=posting.company,
                description=posting.description,
                source_url=posting.source_url,
                is_public=False,
            )
        application, error = create_application_with_package(request.user, clone)
        if error is not None:
            messages.error(
                request, f"Generation failed: {error} You can regenerate from the application page."
            )
        else:
            messages.success(
                request,
                "Application package generated — review and edit it; nothing is "
                "final until you say so.",
            )
        return redirect("core:application_detail", pk=application.pk)


class ApplicationMixin(LoginRequiredMixin):
    """Base for application views: everything is scoped to the owner (else 404)."""

    model = Application
    request: HttpRequest  # set by View.setup() on every request

    def get_queryset(self) -> QuerySet[Application]:
        return Application.objects.filter(user=self.request.user).select_related("job")


class ApplicationDetailView(ApplicationMixin, DetailView):
    """The package sections, status buttons, and edit/delete/regenerate actions."""

    template_name = "core/application_detail.html"
    context_object_name = "application"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        current = self.object.status
        context["statuses"] = [c for c in Application.Status.choices if c[0] != current]
        return context


class ApplicationRegenerateView(ApplicationMixin, View):
    """POST-only regenerate (GET is 405 via View.dispatch, after the login check);
    HTMX gets the swapped package partial, others a redirect."""

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        application = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        profile, _created = Profile.objects.get_or_create(user=request.user)
        try:
            package = generate_application_package(profile, application.job)
        except GenerationError as exc:
            messages.error(request, f"Regeneration failed: {exc}")
        else:
            apply_package(application, package)
            messages.success(request, "Package regenerated — review it again.")
        if request.headers.get("HX-Request") == "true":
            return render(request, "core/_package.html", {"application": application})
        return redirect("core:application_detail", pk=application.pk)


class ApplicationEditView(ApplicationMixin, UpdateView):
    """The human review pass over tailored_summary and cover_letter."""

    template_name = "core/application_form.html"
    form_class = ApplicationEditForm
    context_object_name = "application"

    def get_success_url(self) -> str:
        return str(reverse_lazy("core:application_detail", kwargs={"pk": self.object.pk}))

    def form_valid(self, form: ApplicationEditForm) -> HttpResponse:
        messages.success(self.request, "Review saved — this is your edit, not the agent's.")
        return super().form_valid(form)


class ApplicationStatusView(ApplicationMixin, View):
    """POST-only status transitions (GET is 405), validated against the choices."""

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        application = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        new_status = request.POST.get("status", "")
        valid = {value for value, _label in Application.Status.choices}
        if new_status not in valid:
            messages.error(request, f"Unknown status: {new_status!r}.")
            return redirect("core:application_detail", pk=application.pk)
        application.status = new_status
        application.save(update_fields=["status", "updated_at"])
        messages.success(request, f"Status updated to {application.get_status_display()}.")
        return redirect("core:application_detail", pk=application.pk)


class ApplicationDeleteView(ApplicationMixin, View):
    """Delete removes the application and its job posting (cascade)."""

    template_name = "core/application_confirm_delete.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        application = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        return render(request, self.template_name, {"application": application})

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        application = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        job = application.job
        job.delete()  # cascades to the application
        messages.success(request, "Application and posting deleted.")
        return redirect("core:dashboard")
