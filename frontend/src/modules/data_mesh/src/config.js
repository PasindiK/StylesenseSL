/** Data Mesh API origin (no trailing slash). Override on Vercel: VITE_DATA_MESH_API_URL */
export const API_BASE =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_DATA_MESH_API_URL) ||
  "http://localhost:8001";
