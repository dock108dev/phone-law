export interface WebConfiguration {
  profile: "test" | "demo";
  allowRealCallData: false;
}

interface WebEnvironment {
  readonly VITE_APP_PROFILE?: string;
  readonly VITE_ALLOW_REAL_CALL_DATA?: string;
}

export function loadWebConfiguration(
  source: WebEnvironment = import.meta.env,
): WebConfiguration {
  const profile = source.VITE_APP_PROFILE ?? "demo";
  const allowRealCallData = source.VITE_ALLOW_REAL_CALL_DATA ?? "false";

  if (profile !== "test" && profile !== "demo") {
    throw new Error("The local review workspace supports only test or demo profiles.");
  }
  if (allowRealCallData !== "false") {
    throw new Error("The local review workspace refuses real call data.");
  }

  return { profile, allowRealCallData: false };
}
