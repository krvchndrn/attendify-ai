/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Inject the runtime env-config script into every page <head>
  // so NEXT_PUBLIC_API_URL can be overridden at container startup without a rebuild.
  async headers() {
    return [];
  },
};

export default nextConfig;
