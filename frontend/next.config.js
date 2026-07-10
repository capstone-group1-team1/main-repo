/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 'standalone' output makes the Docker runner image small (Module 10).
  output: "standalone",
};
module.exports = nextConfig;
