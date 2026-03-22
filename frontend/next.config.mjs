/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
