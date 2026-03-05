/** Extract a short summary from tool args JSON for display in collapsed header. */
export function summarizeArgs(args: unknown): string {
  if (typeof args !== "string") {
    if (args && typeof args === "object") return summarizeArgs(JSON.stringify(args));
    return "";
  }
  try {
    const obj = JSON.parse(args);
    const val =
      obj.file_path ?? obj.path ?? obj.command ?? obj.query ?? obj.pattern ?? obj.url;
    if (typeof val === "string") {
      // For paths, show last 2 segments to keep it short
      if (val.includes("/")) {
        const parts = val.split("/").filter(Boolean);
        const short = parts.length > 2 ? "…/" + parts.slice(-2).join("/") : val;
        return short.length > 60 ? "…" + short.slice(-57) : short;
      }
      return val.length > 60 ? val.slice(0, 57) + "…" : val;
    }
  } catch {
    /* not JSON, fall through */
  }
  if (!args || args === "{}") return "";
  return args.length > 60 ? args.slice(0, 57) + "…" : args;
}
