"""Project-level views: the single-page app shell and a JSON 404 for the API."""

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse


def spa_index(request):
    """Serve the built React app; the client takes over routing from there."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return HttpResponse(
            "The frontend has not been built. Run `npm run build` in frontend/, "
            "or use the Vite dev server (http://localhost:5173) during development.",
            status=503,
            content_type="text/plain; charset=utf-8",
        )
    response = FileResponse(index.open("rb"), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response


def api_not_found(request):
    return JsonResponse(
        {"error": {"code": "not_found", "message": f"No API endpoint at {request.path}."}},
        status=404,
    )
