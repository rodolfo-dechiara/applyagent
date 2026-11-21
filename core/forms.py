"""Forms for the core app. Widgets carry Tailwind classes (CDN, no build step)."""

from typing import Any, ClassVar

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from core.models import Application, JobPosting, Profile

INPUT_CLASS = "w-full rounded border border-slate-300 bg-white p-2 text-sm"
TEXTAREA_CLASS = INPUT_CLASS + " min-h-24"


class RegisterForm(UserCreationForm):
    """Registration requires an email: the account is unusable until verified."""

    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields: ClassVar[list[str]] = ["username", "email"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASS


class ResendVerificationForm(forms.Form):
    """Ask for a new verification link. The response is identical whether or not
    the address is registered, so the endpoint cannot be used for enumeration."""

    email = forms.EmailField(required=True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs["class"] = INPUT_CLASS


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields: ClassVar[list[str]] = [
            "headline",
            "skills",
            "experience",
            "education",
            "links",
            "cv_text",
        ]
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "headline": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "skills": forms.Textarea(attrs={"class": TEXTAREA_CLASS}),
            "experience": forms.Textarea(attrs={"class": TEXTAREA_CLASS}),
            "education": forms.Textarea(attrs={"class": TEXTAREA_CLASS}),
            "links": forms.Textarea(attrs={"class": TEXTAREA_CLASS}),
            "cv_text": forms.Textarea(attrs={"class": TEXTAREA_CLASS + " min-h-48"}),
        }


class JobPostingForm(forms.ModelForm):
    class Meta:
        model = JobPosting
        fields: ClassVar[list[str]] = ["title", "company", "description", "source_url"]
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "company": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "description": forms.Textarea(attrs={"class": TEXTAREA_CLASS + " min-h-48"}),
            "source_url": forms.URLInput(attrs={"class": INPUT_CLASS}),
        }


class ApplicationEditForm(forms.ModelForm):
    """The human review pass over the agent-drafted package."""

    class Meta:
        model = Application
        fields: ClassVar[list[str]] = ["tailored_summary", "cover_letter"]
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "tailored_summary": forms.Textarea(attrs={"class": TEXTAREA_CLASS}),
            "cover_letter": forms.Textarea(attrs={"class": TEXTAREA_CLASS + " min-h-64"}),
        }
