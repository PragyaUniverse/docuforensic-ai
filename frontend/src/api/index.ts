import type { Api } from "./client";
import { realApi } from "./real";

// The mock is imported only in mock mode, so it is absent from the default bundle.
let impl: Api = realApi;
if (import.meta.env.VITE_USE_MOCK === "1") {
  impl = (await import("./mock")).mockApi;
}

export const api: Api = impl;
export { ApiError, MOCK_MODE } from "./client";
