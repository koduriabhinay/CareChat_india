/** @type {import('next').NextConfig} */
// Static export: the whole web app is plain files that any static host (or Catalyst
// web client hosting, which serves under /app) can serve. Pages take ids from the query string.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";
const nextConfig = { reactStrictMode: true, output: "export", trailingSlash: true, images: { unoptimized: true }, basePath };
export default nextConfig;
