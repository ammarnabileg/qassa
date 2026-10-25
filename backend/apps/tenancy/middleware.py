from apps.tenancy.context import clear_context


class TenantContextResetMiddleware:
    """Guarantees no tenant context leaks between requests handled by the same worker thread."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        clear_context()
        try:
            return self.get_response(request)
        finally:
            clear_context()
