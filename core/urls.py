from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API Routes Base
    path('api/v1/', include('tenants.urls')),
    path('api/v1/profiles/', include('profiles.urls')),
    path('api/v1/academics/', include('academics.urls')),
    path('api/v1/operations/', include('operations.urls')),
    path('api/v1/accounts/', include('accounts.urls')),
    
    # YOUR ISOLATED ADMIN ROUTE LAYER
    path('api/v1/school-admin/', include('school_admin.urls')),
    
    # AI TUTOR MODULE
    path('api/v1/tutor/', include('tutor.urls')),
    
    # Swagger / OpenAPI Endpoints (Restored!)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]