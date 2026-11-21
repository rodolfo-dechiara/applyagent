"""URL configuration for the core app (dashboard, profile, applications)."""

from django.urls import URLPattern, path

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
    ProfileView,
)

app_name = "core"

urlpatterns: list[URLPattern] = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("profile/", ProfileView.as_view(), name="profile"),
    # Public jobs board (anonymous access intended; <int:pk> never matches "new").
    path("jobs/", JobBoardView.as_view(), name="job_board"),
    path("jobs/<int:pk>/", JobBoardDetailView.as_view(), name="job_board_detail"),
    path("jobs/<int:pk>/apply/", JobBoardApplyView.as_view(), name="job_board_apply"),
    path("jobs/new/", JobCreateView.as_view(), name="job_new"),
    path("applications/<int:pk>/", ApplicationDetailView.as_view(), name="application_detail"),
    path(
        "applications/<int:pk>/regenerate/",
        ApplicationRegenerateView.as_view(),
        name="application_regenerate",
    ),
    path("applications/<int:pk>/edit/", ApplicationEditView.as_view(), name="application_edit"),
    path(
        "applications/<int:pk>/delete/", ApplicationDeleteView.as_view(), name="application_delete"
    ),
    path(
        "applications/<int:pk>/status/", ApplicationStatusView.as_view(), name="application_status"
    ),
]
