import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/payment/", "/api/"],
      },
    ],
    sitemap: "https://vacancy-mirror.com/sitemap.xml",
    host: "https://vacancy-mirror.com",
  };
}

