import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const exampleValues = ["your-project.supabase.co", "your-publishable-key", "your-anon-key"];
  if (!url || !key || exampleValues.some((value) => url.includes(value) || key.includes(value))) {
    throw new Error("Supabase is not configured yet. Replace the example URL and publishable key in apps/web/.env.local with your Supabase project settings, then restart the web app.");
  }
  return createBrowserClient(url, key);
}
