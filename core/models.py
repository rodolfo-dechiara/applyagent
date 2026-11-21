"""Core data model: candidate Profile, pasted JobPosting, generated Application."""

from typing import ClassVar

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Profile(models.Model):
    """The candidate's one master profile. Exactly one per user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    headline = models.CharField(max_length=200, blank=True)
    skills = models.TextField(blank=True)
    experience = models.TextField(blank=True)
    education = models.TextField(blank=True)
    links = models.TextField(blank=True)
    cv_text = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Profile of {self.user.username}"


class JobPosting(models.Model):
    """A job posting pasted by the candidate. No scraping: postings arrive by paste."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="job_postings"
    )
    title = models.CharField(max_length=300)
    company = models.CharField(max_length=200, blank=True)
    description = models.TextField()
    source_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.title} at {self.company}".strip()


class Application(models.Model):
    """The agent-generated application package for one job posting.

    Nothing here is final until the candidate reviews and edits it; the status
    is tracked by the candidate and v0 never submits anything anywhere.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready"
        SUBMITTED = "submitted", "Submitted"
        INTERVIEW = "interview", "Interview"
        OFFER = "offer", "Offer"
        REJECTED = "rejected", "Rejected"

    class AgentMode(models.TextChoices):
        MISTRAL = "mistral", "Mistral"
        DEMO = "demo", "Demo"

    job = models.OneToOneField(JobPosting, on_delete=models.CASCADE, related_name="application")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    # Agent package fields (human-editable: the review pass happens in the edit view).
    tailored_summary = models.TextField(blank=True)
    cover_letter = models.TextField(blank=True)
    screening_answers = models.JSONField(default=list, blank=True)
    match_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    match_reasons = models.JSONField(default=list, blank=True)
    red_flags = models.JSONField(default=list, blank=True)

    # Provenance: how this package was produced.
    agent_mode = models.CharField(max_length=20, choices=AgentMode.choices, default=AgentMode.DEMO)
    agent_model = models.CharField(max_length=100, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-updated_at"]

    def __str__(self) -> str:
        return f"Application for {self.job} ({self.status})"
