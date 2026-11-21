"""Forms for the core app. Widgets carry Tailwind classes (CDN, no build step)."""

from typing import Any, ClassVar

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import MaxLengthValidator

from core.models import Application, JobPosting, Profile

INPUT_CLASS = (
    "w-full rounded-lg border border-slate-300 bg-white/90 p-2.5 text-sm shadow-sm transition "
    "placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 "
    "focus:ring-indigo-200"
)
TEXTAREA_CLASS = INPUT_CLASS + " min-h-24"

# Free-text inputs are length-capped at the form level (ASVS V5.2) so a paste
# cannot store unbounded payloads.
PROFILE_MAX_LENGTHS: dict[str, int] = {
    "headline": 200,
    "skills": 20_000,
    "experience": 20_000,
    "education": 20_000,
    "links": 2_000,
    "cv_text": 50_000,
}
JOB_DESCRIPTION_MAX_LENGTH = 50_000
APPLICATION_TEXT_MAX_LENGTH = 20_000


def _cap_lengths(form: forms.BaseForm, limits: dict[str, int]) -> None:
    for name, max_length in limits.items():
        field = form.fields[name]
        if isinstance(field, forms.CharField):
            field.max_length = max_length
            field.validators.append(MaxLengthValidator(max_length))
            field.widget.attrs["maxlength"] = str(max_length)


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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _cap_lengths(self, PROFILE_MAX_LENGTHS)


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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _cap_lengths(self, {"description": JOB_DESCRIPTION_MAX_LENGTH})


class ApplicationEditForm(forms.ModelForm):
    """The human review pass over the agent-drafted package."""

    class Meta:
        model = Application
        fields: ClassVar[list[str]] = ["tailored_summary", "cover_letter"]
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "tailored_summary": forms.Textarea(attrs={"class": TEXTAREA_CLASS}),
            "cover_letter": forms.Textarea(attrs={"class": TEXTAREA_CLASS + " min-h-64"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _cap_lengths(
            self,
            {
                "tailored_summary": APPLICATION_TEXT_MAX_LENGTH,
                "cover_letter": APPLICATION_TEXT_MAX_LENGTH,
            },
        )
