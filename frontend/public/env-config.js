// This file is overwritten at container startup by the Dockerfile CMD.
// It injects runtime environment variables so NEXT_PUBLIC_API_URL
// can be set via Railway environment variables without a rebuild.
window.__ENV__ = window.__ENV__ || {};
