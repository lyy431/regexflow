from django.urls import path
from rest_framework.routers import SimpleRouter

from datasets import views

router = SimpleRouter()
router.register("datasets", views.DatasetViewSet, basename="dataset")

urlpatterns = [
    path("health/", views.health, name="health"),
    *router.urls,
]
