from django.urls import include, path, re_path

from config import views

urlpatterns = [
    path("api/", include("datasets.urls")),
    re_path(r"^api/", views.api_not_found),
    # Everything else is a route of the single-page app.
    re_path(r"^(?!static/).*$", views.spa_index),
]
