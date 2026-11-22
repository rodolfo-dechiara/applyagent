"""URL configuration for the core app (dashboard, profile, applications)."""

from django.urls import URLPattern, path

import core.converters  # noqa: F401  (registers the <uid:...> path converter)
from core.views import (
    ApplicationDeleteView,
    ApplicationDetailView,
    ApplicationEditView,
    ApplicationRegenerateView,
    ApplicationStatusView,
    DashboardView,
    JobBoardApplyView,
    JobBoardDetailView,
    JobBoardView,
    JobCreateView,
    LandingView,
    ProfileView,
)

app_name = "core"

urlpatterns: list[URLPattern] = [
    path("", LandingView.as_view(), name="landing"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("profile/", ProfileView.as_view(), name="profile"),
    # Public jobs board (anonymous access intended; <uid:uid> never matches "new").
    path("jobs/", JobBoardView.as_view(), name="job_board"),
    path("jobs/<uid:uid>/", JobBoardDetailView.as_view(), name="job_board_detail"),
    path("jobs/<uid:uid>/apply/", JobBoardApplyView.as_view(), name="job_board_apply"),
    path("jobs/new/", JobCreateView.as_view(), name="job_new"),
    path("applications/<uid:uid>/", ApplicationDetailView.as_view(), name="application_detail"),
    path(
        "applications/<uid:uid>/regenerate/",
        ApplicationRegenerateView.as_view(),
        name="application_regenerate",
    ),
    path("applications/<uid:uid>/edit/", ApplicationEditView.as_view(), name="application_edit"),
    path(
        "applications/<uid:uid>/delete/", ApplicationDeleteView.as_view(), name="application_delete"
    ),
    path(
        "applications/<uid:uid>/status/", ApplicationStatusView.as_view(), name="application_status"
    ),
]
